from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import json
import os
from pathlib import Path
import re
import unicodedata

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


st.set_page_config(page_title="SAC | Fechamento mensal", page_icon="🎧", layout="wide")

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("ZENDESK_DATA_DIR", BASE_DIR))
MANUAL_CONFIG_PATH = DATA_DIR / "config_manual.json"
EXPECTED_FILES = {
    "tickets": "Zendesk-Support_Tickets_",
    "efficiency": "Zendesk-Support_Efficiency_",
    "assignee": "Zendesk-Support_Assignee-activity_",
    "updates": "Zendesk-Support_Agent-updates_",
    "unsolved": "Zendesk-Support_Unsolved-tickets_",
    "backlog": "Zendesk-Support_Backlog_",
    "sla": "Zendesk-Support_SLAs_",
    "satisfaction": "Zendesk-Support_Satisfaction_",
}
DETAIL_PREFIX = "export-"
DETAIL_COLUMNS = [
    "Id", "Assignee", "Group", "Status", "Priority", "Via", "Ticket type", "Created at", "Updated at",
    "Assigned at", "Solved at", "Satisfaction Score", "Reopens", "Replies",
    "First reply time in minutes", "First reply time in minutes within business hours",
    "Full resolution time in minutes", "Full resolution time in minutes within business hours",
    "Requester wait time in minutes", "Requester wait time in minutes within business hours",
    "Motivo do Contato [list]", "Tipo de resolução [list]", "Grupo do canal [list]", "Nível de resolução [list]",
]

MONTHS = {
    "jan": 1, "janeiro": 1, "fev": 2, "fevereiro": 2, "mar": 3, "marco": 3,
    "abr": 4, "abril": 4, "mai": 5, "maio": 5, "jun": 6, "junho": 6,
    "jul": 7, "julho": 7, "ago": 8, "agosto": 8, "set": 9, "setembro": 9,
    "out": 10, "outubro": 10, "nov": 11, "novembro": 11, "dez": 12, "dezembro": 12,
}

COLORS = {
    "coral": "#E9785D", "navy": "#183B56", "blue": "#3E7CB1", "teal": "#2A9D8F",
    "gold": "#E9C46A", "red": "#D9534F", "green": "#5AA469", "muted": "#6B7280",
}


def clean_name(value: object) -> str:
    text = "" if value is None else str(value).strip()
    return " ".join(text.replace("\xa0", " ").split())


def header_parts(value: object) -> list[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    return [clean_name(part) for part in str(value).splitlines() if clean_name(part)]


def normalized(value: object) -> str:
    text = clean_name(value)
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").casefold()


def numeric(value: object, default: float = 0.0) -> float:
    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return default if pd.isna(parsed) else float(parsed)


def parse_pt_date(value: object) -> pd.Timestamp:
    text = normalized(value).replace(".0", "")
    match = re.search(r"(\d{1,2})\s+([a-z]+)\s+(\d{2,4})", text)
    if not match:
        return pd.NaT
    day, month_text, year = match.groups()
    month = MONTHS.get(month_text) or MONTHS.get(month_text[:3])
    if not month:
        return pd.NaT
    year_number = int(year)
    if year_number < 100:
        year_number += 2000
    return pd.Timestamp(year_number, month, int(day))


def parse_period(parts: list[str]) -> pd.Timestamp:
    if len(parts) < 2:
        return pd.NaT
    year = next((int(part) for part in parts if part.isdigit() and len(part) == 4), None)
    month = next((MONTHS.get(normalized(part)) for part in parts if MONTHS.get(normalized(part))), None)
    return pd.Timestamp(year, month, 1) if year and month else pd.NaT


def format_hours(value: float) -> str:
    if pd.isna(value):
        return "—"
    if value < 1:
        return f"{value * 60:.0f} min"
    return f"{value:.1f} h"


def format_minutes(value: float) -> str:
    if pd.isna(value):
        return "—"
    hours, minutes = divmod(int(round(value)), 60)
    return f"{hours}h {minutes:02d}min" if hours else f"{minutes} min"


def pct(value: float) -> str:
    return "—" if pd.isna(value) else f"{value:.1%}"


@dataclass
class Source:
    name: str
    payload: bytes | Path


class ZendeskBook:
    def __init__(self, source: Source):
        self.source = source
        target = BytesIO(source.payload) if isinstance(source.payload, bytes) else source.payload
        self.excel = pd.ExcelFile(target, engine="openpyxl")

    def sheet_name(self, query: str) -> str:
        query_key = normalized(query)
        exact = [name for name in self.excel.sheet_names if normalized(name) == query_key]
        if exact:
            return exact[0]
        matches = [name for name in self.excel.sheet_names if query_key in normalized(name)]
        if not matches:
            raise KeyError(f"Aba não encontrada: {query}")
        return matches[0]

    def matrix(self, query: str) -> pd.DataFrame:
        return pd.read_excel(self.excel, sheet_name=self.sheet_name(query), header=None)

    def table(self, query: str) -> pd.DataFrame:
        frame = pd.read_excel(self.excel, sheet_name=self.sheet_name(query))
        frame.columns = [clean_name(column) for column in frame.columns]
        return frame.dropna(how="all")

    def scalar(self, query: str) -> float:
        frame = self.matrix(query)
        return numeric(frame.iloc[1, 0], np.nan)


def discover_repository_sources() -> dict[str, Source]:
    sources: dict[str, Source] = {}
    for key, prefix in EXPECTED_FILES.items():
        matches = sorted(DATA_DIR.glob(f"{prefix}*.xlsx"), key=lambda path: path.stat().st_mtime, reverse=True)
        if matches:
            sources[key] = Source(matches[0].name, matches[0])
    detail_matches = sorted(DATA_DIR.glob("export-*.csv.zip"), key=lambda path: path.stat().st_mtime, reverse=True)
    if detail_matches:
        sources["detail"] = Source(detail_matches[0].name, detail_matches[0])
    return sources


def uploaded_sources(files: list) -> dict[str, Source]:
    sources: dict[str, Source] = {}
    for uploaded in files:
        if uploaded.name.casefold().startswith(DETAIL_PREFIX) and uploaded.name.casefold().endswith(".csv.zip"):
            sources["detail"] = Source(uploaded.name, uploaded.getvalue())
            continue
        for key, prefix in EXPECTED_FILES.items():
            if uploaded.name.casefold().startswith(prefix.casefold()):
                sources[key] = Source(uploaded.name, uploaded.getvalue())
                break
    return sources


def one_row_series(book: ZendeskBook, query: str) -> list[tuple[str, float]]:
    frame = book.matrix(query)
    return [(str(frame.iloc[0, column]), numeric(frame.iloc[1, column], np.nan)) for column in range(frame.shape[1])]


def dated_metrics(book: ZendeskBook, query: str) -> pd.DataFrame:
    records = []
    for header, value in one_row_series(book, query):
        parts = header_parts(header)
        date = parse_pt_date(parts[0] if parts else "")
        if pd.isna(date) or len(parts) < 2:
            continue
        records.append({"Data": date, "Métrica": parts[-1], "Valor": value})
    return pd.DataFrame(records)


def period_metrics(book: ZendeskBook, query: str) -> pd.DataFrame:
    records = []
    for header, value in one_row_series(book, query):
        parts = header_parts(header)
        period = parse_period(parts)
        if pd.isna(period) or len(parts) < 3:
            continue
        records.append({"Período": period, "Métrica": parts[-1], "Valor": value})
    return pd.DataFrame(records)


def category_metrics(book: ZendeskBook, query: str) -> pd.DataFrame:
    records = []
    for header, value in one_row_series(book, query):
        parts = header_parts(header)
        if len(parts) < 2:
            continue
        records.append({"Categoria": parts[0], "Métrica": parts[-1], "Valor": value})
    return pd.DataFrame(records)


def category_dates(book: ZendeskBook, query: str) -> pd.DataFrame:
    frame = book.matrix(query)
    records = []
    for row in range(1, frame.shape[0]):
        category = clean_name(frame.iloc[row, 0]) or "Não informado"
        for column in range(1, frame.shape[1]):
            parts = header_parts(frame.iloc[0, column])
            date = parse_pt_date(parts[0] if parts else "")
            if not pd.isna(date):
                records.append({"Categoria": category, "Data": date, "Valor": numeric(frame.iloc[row, column], 0)})
    return pd.DataFrame(records)


def status_group_backlog(book: ZendeskBook) -> pd.DataFrame:
    frame = book.matrix("Unsolved tickets by selec")
    records = []
    for row in range(1, frame.shape[0]):
        status = clean_name(frame.iloc[row, 0])
        for column in range(1, frame.shape[1]):
            parts = header_parts(frame.iloc[0, column])
            if not parts or "Tickets não resolvidos" not in parts[-1]:
                continue
            group = parts[0] or "Sem grupo"
            records.append({"Status": status, "Grupo": group, "Tickets": numeric(frame.iloc[row, column], 0)})
    return pd.DataFrame(records)


def load_detail(source: Source, period_start: pd.Timestamp, period_end: pd.Timestamp) -> dict:
    target = BytesIO(source.payload) if isinstance(source.payload, bytes) else source.payload
    frame = pd.read_csv(
        target,
        compression="zip",
        dtype=str,
        usecols=lambda column: column in DETAIL_COLUMNS,
        low_memory=False,
    )
    for column in ["Created at", "Updated at", "Assigned at", "Solved at"]:
        frame[column] = pd.to_datetime(frame[column], errors="coerce")
    number_columns = [
        "Reopens", "Replies", "First reply time in minutes", "First reply time in minutes within business hours",
        "Full resolution time in minutes", "Full resolution time in minutes within business hours",
        "Requester wait time in minutes", "Requester wait time in minutes within business hours",
    ]
    for column in number_columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    end_of_period = period_end + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    created = frame[frame["Created at"].between(period_start, end_of_period)].copy()
    solved = frame[frame["Solved at"].between(period_start, end_of_period)].copy()
    channel_names = {
        "Mail": "Email", "Instagram DM": "Instagram Direct", "Native Messaging": "Messaging",
        "Web form": "Web", "Closed Ticket": "Ticket fechado",
    }
    created["Canal"] = created["Via"].replace(channel_names)
    created["Motivo"] = created["Motivo do Contato [list]"].replace({"-": "Não informado"}).fillna("Não informado")
    solved["Canal"] = solved["Via"].replace(channel_names)
    return {
        "filename": source.name,
        "all_rows": len(frame),
        "duplicate_ids": int(frame["Id"].duplicated().sum()),
        "created": created,
        "solved": solved,
    }


@st.cache_data(show_spinner=False)
def load_dashboard(source_signature: tuple) -> dict:
    sources = {key: Source(name, payload) for key, name, payload in source_signature}
    books = {key: ZendeskBook(source) for key, source in sources.items() if key in EXPECTED_FILES}
    tickets, efficiency = books["tickets"], books["efficiency"]
    assignee, updates = books["assignee"], books["updates"]
    unsolved, backlog = books["unsolved"], books["backlog"]
    sla, satisfaction = books["sla"], books["satisfaction"]

    daily_volume = dated_metrics(tickets, "Tickets created by date")
    daily_volume["Métrica"] = daily_volume["Métrica"].replace({"Tickets": "Criados", "Tickets resolvidos": "Resolvidos"})

    team = assignee.table("Assignee activity")
    team_updates = updates.table("Agent updates")
    team_updates = team_updates.rename(columns={"Tickets resolvidos": "Tickets resolvidos (atualizações)"})
    team["chave"] = team["Nome do atribuído"].map(normalized)
    team_updates["chave"] = team_updates["Nome do atualizador"].map(normalized)
    team = team.merge(team_updates, on="chave", how="outer")
    team["Agente"] = team["Nome do atribuído"].combine_first(team["Nome do atualizador"])
    team = team.drop(columns=["chave", "Nome do atribuído", "Nome do atualizador"], errors="ignore")

    funnel = dict(one_row_series(satisfaction, "Rated tickets funnel"))
    backlog_status = category_metrics(unsolved, "Unsolved tickets by status")
    backlog_status["Categoria"] = backlog_status["Categoria"].replace({"New": "Novo", "Open": "Aberto", "Pending": "Pendente"})

    result = {
        "files": [source.name for source in sources.values()],
        "kpis": {
            "created": tickets.scalar("Created tickets"),
            "solved": tickets.scalar("Solved tickets"),
            "one_touch": tickets.scalar("One-touch tickets"),
            "reopened": tickets.scalar("Reopened tickets"),
            "first_reply_min": efficiency.scalar("First reply time median"),
            "resolution_h": efficiency.scalar("Full resolution time median"),
            "requester_wait_h": assignee.scalar("Requester wait time median"),
            "unsolved": unsolved.scalar("Unsolved tickets 1"),
            "unreplied": unsolved.scalar("Unreplied unsolved tickets"),
            "age_days": unsolved.scalar("Tickets age median"),
            "sla_rate": sla.scalar("SLA achievement rate"),
            "sla_achieved": sla.scalar("SLA achieved tickets"),
            "sla_breached": sla.scalar("SLA breached tickets"),
            "csat": satisfaction.scalar("Satisfaction score"),
            "survey_rate": satisfaction.scalar("Satisfaction rated"),
            "rated": numeric(funnel.get("Rated tickets"), np.nan),
            "surveyed": numeric(funnel.get("Surveyed tickets"), np.nan),
        },
        "daily_volume": daily_volume,
        "daily_channels": category_dates(tickets, "Tickets created by date a"),
        "channels": category_metrics(tickets, "Tickets by selected attri"),
        "hourly": category_metrics(tickets, "Tickets created by hour"),
        "reply_buckets": category_metrics(efficiency, "Tickets by first reply ti"),
        "resolution_buckets": category_metrics(efficiency, "Tickets by full resolutio"),
        "wait_buckets": category_metrics(assignee, "Tickets by requester wait"),
        "team": team,
        "backlog_status": backlog_status,
        "backlog_agents": unsolved.table("Unsolved tickets 2"),
        "backlog_groups": status_group_backlog(unsolved),
        "weekly_backlog_status": category_dates(backlog, "Weekly historical backlog... 2"),
        "weekly_backlog_group": category_dates(backlog, "Weekly historical backlog... 1"),
        "csat_channel": category_metrics(satisfaction, "Satisfaction score by sel"),
        "csat_breakdown": pd.DataFrame(
            one_row_series(satisfaction, "Good vs bad satisfaction"),
            columns=["Categoria", "Tickets"],
        ),
        "csat_daily": dated_metrics(satisfaction, "Satisfaction score and ra... 1"),
        "csat_monthly": period_metrics(satisfaction, "Satisfaction score and ra... 2"),
        "sla_daily": dated_metrics(sla, "Achieved vs breached comp"),
        "sla_monthly": period_metrics(sla, "SLA target achievement ra"),
    }
    period_start = daily_volume["Data"].min()
    period_end = daily_volume["Data"].max()
    result["detail"] = load_detail(sources["detail"], period_start, period_end) if "detail" in sources else None
    return result


def make_signature(sources: dict[str, Source]) -> tuple:
    signature = []
    for key in EXPECTED_FILES:
        source = sources[key]
        if isinstance(source.payload, Path):
            signature.append((key, source.name, source.payload))
        else:
            signature.append((key, source.name, source.payload))
    if "detail" in sources:
        source = sources["detail"]
        signature.append(("detail", source.name, source.payload))
    return tuple(signature)


def metric_chart(frame: pd.DataFrame, metric_contains: str, category_col: str = "Categoria") -> pd.DataFrame:
    return frame[frame["Métrica"].str.contains(metric_contains, case=False, na=False)][[category_col, "Valor"]].copy()


def section_title(title: str, caption: str | None = None) -> None:
    st.subheader(title)
    if caption:
        st.caption(caption)


def load_manual_config() -> dict:
    defaults = {
        "mes_referencia": "Julho de 2026",
        "meta_resolucao_h": 55.0,
        "meta_resposta_h": 28.0,
        "reclame_aqui": {
            "nota": 8.5,
            "reclamacoes": 14,
            "respondidas_pct": 100.0,
            "voltariam_pct": 77.8,
            "solucao_pct": 91.1,
            "nota_consumidor": 7.22,
            "tempo_resposta": "8 dias e 21 horas",
            "motivos": {
                "Problemas de qualidade": 7,
                "Questões logísticas": 6,
                "Experiência de compra e atendimento": 1,
            },
        },
    }
    if not MANUAL_CONFIG_PATH.exists():
        return defaults
    try:
        saved = json.loads(MANUAL_CONFIG_PATH.read_text(encoding="utf-8"))
        return defaults | saved | {"reclame_aqui": defaults["reclame_aqui"] | saved.get("reclame_aqui", {})}
    except Exception:
        return defaults


def hours_from_detail(detail: dict | None, column: str, fallback: float) -> float:
    if not detail or detail["solved"].empty or column not in detail["solved"]:
        return fallback
    value = detail["solved"][column].median()
    return fallback if pd.isna(value) else float(value) / 60


def target_gauge(title: str, actual: float, target: float) -> go.Figure:
    within_target = actual <= target
    upper = max(target * 1.45, actual * 1.2, 1)
    figure = go.Figure(go.Indicator(
        mode="number+delta+gauge",
        value=actual,
        number={"suffix": " h", "font": {"size": 34, "color": COLORS["navy"]}},
        delta={
            "reference": target,
            "relative": False,
            "valueformat": ".1f",
            "increasing": {"color": COLORS["red"]},
            "decreasing": {"color": COLORS["green"]},
            "suffix": " h",
        },
        title={"text": f"<b>{title}</b><br><span style='font-size:13px;color:#667085'>Meta: até {target:.1f} h</span>"},
        gauge={
            "shape": "bullet",
            "axis": {"range": [0, upper], "tickfont": {"size": 10}},
            "bar": {"color": COLORS["green"] if within_target else COLORS["red"]},
            "bgcolor": "#EDF1F5",
            "borderwidth": 0,
            "threshold": {"line": {"color": COLORS["navy"], "width": 3}, "value": target},
        },
    ))
    figure.update_layout(height=190, margin=dict(l=35, r=35, t=55, b=25), paper_bgcolor="white")
    return figure


st.markdown(
    """
    <style>
      :root { --navy:#163B5C; --blue:#4F8FCF; --ice:#F4F7FA; --line:#E4EAF0; }
      .stApp { background: #F4F7FA; }
      .block-container { padding-top: 1.7rem; padding-bottom: 4rem; max-width: 1440px; }
      [data-testid="stSidebar"] { background: #FFFFFF; border-right: 1px solid #E4EAF0; }
      [data-testid="stMetric"] {
        background: white; border: 1px solid #E4EAF0; border-radius: 18px;
        padding: 18px 18px 16px; box-shadow: 0 8px 24px rgba(22,59,92,.05);
      }
      [data-testid="stMetricLabel"] { color: #667085; font-weight: 600; }
      [data-testid="stMetricValue"] { color: #163B5C; }
      div[data-testid="stTabs"] [role="tablist"] { gap: 10px; }
      div[data-testid="stTabs"] button {
        font-weight: 700; background: white; border-radius: 12px 12px 0 0; padding: 12px 18px;
      }
      .hero {
        padding: 22px 26px; border-radius: 22px; color: white; margin-bottom: 18px;
        background: linear-gradient(120deg,#143A5A 0%,#205D8F 60%,#5A9DD6 100%);
        box-shadow: 0 12px 30px rgba(20,58,90,.16);
      }
      .hero h1 { margin:0; font-size:31px; line-height:1.15; }
      .hero p { margin:8px 0 0; opacity:.86; font-size:15px; }
      .panel-title { font-size:20px; font-weight:750; color:#163B5C; margin:6px 0 2px; }
      .panel-caption { color:#667085; font-size:13px; margin-bottom:10px; }
      .manual-card {
        background:white; border:1px solid #E4EAF0; border-radius:18px; padding:20px 22px;
        box-shadow:0 8px 24px rgba(22,59,92,.05); margin-bottom:12px;
      }
      .score { font-size:44px; font-weight:800; color:#2A9D8F; line-height:1; }
      .muted { color:#667085; font-size:13px; }
    </style>
    """,
    unsafe_allow_html=True,
)

repository_sources = discover_repository_sources()
manual_defaults = load_manual_config()
with st.sidebar:
    st.markdown("### Fechamento do SAC")
    st.caption("Ajuste aqui somente as metas e os dados manuais do Reclame Aqui.")
    reference_month = st.text_input("Mês de referência", manual_defaults["mes_referencia"])
    target_reply = st.number_input("Meta • tempo de resposta (h)", min_value=0.1, value=float(manual_defaults["meta_resposta_h"]), step=0.5)
    target_resolution = st.number_input("Meta • tempo de resolução (h)", min_value=0.1, value=float(manual_defaults["meta_resolucao_h"]), step=0.5)

    ra_default = manual_defaults["reclame_aqui"]
    with st.expander("Reclame Aqui • preenchimento manual", expanded=True):
        ra_score = st.number_input("Nota geral", min_value=0.0, max_value=10.0, value=float(ra_default["nota"]), step=0.1)
        ra_complaints = st.number_input("Reclamações", min_value=0, value=int(ra_default["reclamacoes"]), step=1)
        ra_answered = st.number_input("Respondidas (%)", min_value=0.0, max_value=100.0, value=float(ra_default["respondidas_pct"]), step=0.1)
        ra_return = st.number_input("Voltariam a fazer negócio (%)", min_value=0.0, max_value=100.0, value=float(ra_default["voltariam_pct"]), step=0.1)
        ra_solution = st.number_input("Índice de solução (%)", min_value=0.0, max_value=100.0, value=float(ra_default["solucao_pct"]), step=0.1)
        ra_consumer = st.number_input("Nota do consumidor", min_value=0.0, max_value=10.0, value=float(ra_default["nota_consumidor"]), step=0.1)
        ra_response_time = st.text_input("Tempo médio de resposta", str(ra_default["tempo_resposta"]))
        st.caption("Reclamações por motivo")
        ra_quality = st.number_input("Problemas de qualidade", min_value=0, value=int(ra_default["motivos"].get("Problemas de qualidade", 0)), step=1)
        ra_logistics = st.number_input("Questões logísticas", min_value=0, value=int(ra_default["motivos"].get("Questões logísticas", 0)), step=1)
        ra_experience = st.number_input("Compra e atendimento", min_value=0, value=int(ra_default["motivos"].get("Experiência de compra e atendimento", 0)), step=1)

    with st.expander("Fontes de dados"):
        uploads = st.file_uploader("Substituir arquivos nesta sessão", type=["xlsx", "zip"], accept_multiple_files=True)
        st.caption("No uso normal, o painel lê automaticamente os arquivos publicados no GitHub.")
    sources = repository_sources | uploaded_sources(uploads or [])
    required_found = sum(key in sources for key in EXPECTED_FILES)
    if required_found == len(EXPECTED_FILES):
        st.success("Relatórios Zendesk carregados")
    else:
        st.warning(f"{required_found} de {len(EXPECTED_FILES)} relatórios encontrados")
    if "detail" in sources:
        st.success("Base detalhada ZIP carregada")
    else:
        st.info("Adicione `export-*.csv.zip` ao GitHub para completar a visão executiva.")

missing = [prefix for key, prefix in EXPECTED_FILES.items() if key not in sources]
if missing:
    st.info("Coloque as oito planilhas `.xlsx` na mesma pasta de `app.py` ou use o carregador na barra lateral.")
    st.code("\n".join(f"{prefix}*.xlsx" for prefix in missing), language=None)
    st.stop()

try:
    data = load_dashboard(make_signature(sources))
except Exception as error:
    st.error("Não consegui interpretar uma das exportações. Confirme se os arquivos vieram dos mesmos relatórios do Zendesk.")
    with st.expander("Detalhes técnicos"):
        st.exception(error)
    st.stop()

kpi = data["kpis"]
period_start = data["daily_volume"]["Data"].min()
period_end = data["daily_volume"]["Data"].max()
detail = data["detail"]
detail_created = detail["created"] if detail else pd.DataFrame()
detail_solved = detail["solved"] if detail else pd.DataFrame()
created_total = len(detail_created) if detail else int(kpi["created"])
solved_total = len(detail_solved) if detail else int(kpi["solved"])
reply_actual = hours_from_detail(detail, "First reply time in minutes", kpi["first_reply_min"] / 60)
resolution_actual = hours_from_detail(detail, "Full resolution time in minutes", kpi["resolution_h"])

st.markdown(
    f"""
    <div class="hero">
      <h1>Fechamento do SAC • {reference_month}</h1>
      <p>Visão executiva de atendimento, eficiência e voz do cliente</p>
    </div>
    """,
    unsafe_allow_html=True,
)

tabs = st.tabs(["Visão executiva", "Demanda", "Eficiência", "Equipe", "Backlog", "Satisfação & SLA", "Qualidade dos dados"])

with tabs[0]:
    columns = st.columns(6)
    columns[0].metric("Tickets criados", f"{created_total:,.0f}", "base detalhada" if detail else "relatório agregado")
    columns[1].metric("Tickets resolvidos", f"{solved_total:,.0f}")
    columns[2].metric("Resposta mediana", f"{reply_actual:.1f} h", f"meta {target_reply:.1f} h", delta_color="inverse")
    columns[3].metric("Resolução mediana", f"{resolution_actual:.1f} h", f"meta {target_resolution:.1f} h", delta_color="inverse")
    columns[4].metric("CSAT", pct(kpi["csat"]), f"{kpi['rated']:.0f} avaliações")
    columns[5].metric("Backlog", f"{kpi['unsolved']:,.0f}", f"{kpi['unreplied']:.0f} sem resposta")

    st.markdown('<div class="panel-title">Meta x realizado</div><div class="panel-caption">Quanto menor o tempo, melhor o resultado.</div>', unsafe_allow_html=True)
    gauge_left, gauge_right = st.columns(2)
    with gauge_left:
        st.plotly_chart(target_gauge("Tempo de resposta", reply_actual, target_reply), width="stretch", config={"displayModeBar": False})
    with gauge_right:
        st.plotly_chart(target_gauge("Tempo de resolução", resolution_actual, target_resolution), width="stretch", config={"displayModeBar": False})

    performance = pd.DataFrame([
        {"Indicador": "Tempo de resposta", "Objetivo (h)": target_reply, "Realizado (h)": reply_actual},
        {"Indicador": "Tempo de resolução", "Objetivo (h)": target_resolution, "Realizado (h)": resolution_actual},
    ])
    performance["Δ realizado x objetivo (h)"] = performance["Realizado (h)"] - performance["Objetivo (h)"]
    performance["Variação sobre a meta"] = performance["Δ realizado x objetivo (h)"] / performance["Objetivo (h)"]
    performance["Status"] = np.where(performance["Realizado (h)"] <= performance["Objetivo (h)"], "Dentro da meta", "Acima da meta")
    with st.expander("Ver tabela de meta x realizado"):
        st.dataframe(performance, hide_index=True, width="stretch", column_config={"Variação sobre a meta": st.column_config.NumberColumn(format="%.1f%%")})

    ra_column, csat_column = st.columns(2, gap="large")
    with ra_column:
        st.markdown('<div class="panel-title">♥ Reclame Aqui</div><div class="panel-caption">Indicadores preenchidos manualmente para o fechamento.</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="manual-card"><div class="score">{ra_score:.1f}</div><div class="muted">Nota geral • {ra_complaints} reclamações • {ra_answered:.1f}% respondidas</div></div>', unsafe_allow_html=True)
        ra_metrics = st.columns(3)
        ra_metrics[0].metric("Voltariam", f"{ra_return:.1f}%")
        ra_metrics[1].metric("Índice de solução", f"{ra_solution:.1f}%")
        ra_metrics[2].metric("Nota consumidor", f"{ra_consumer:.2f}")
        st.caption(f"Tempo médio de resposta: {ra_response_time}")
        ra_reasons = pd.DataFrame({
            "Motivo": ["Problemas de qualidade", "Questões logísticas", "Compra e atendimento"],
            "Reclamações": [ra_quality, ra_logistics, ra_experience],
        }).sort_values("Reclamações")
        ra_fig = px.bar(ra_reasons, x="Reclamações", y="Motivo", orientation="h", text_auto=True, color_discrete_sequence=[COLORS["blue"]])
        ra_fig.update_layout(height=260, margin=dict(l=0, r=15, t=10, b=25), xaxis_title="", yaxis_title="", paper_bgcolor="white", plot_bgcolor="white")
        st.plotly_chart(ra_fig, width="stretch", config={"displayModeBar": False})

    with csat_column:
        st.markdown('<div class="panel-title">Resultados CSAT</div><div class="panel-caption">Satisfação e participação na pesquisa.</div>', unsafe_allow_html=True)
        csat_breakdown = data["csat_breakdown"].copy()
        csat_breakdown["Categoria"] = csat_breakdown["Categoria"].replace({
            "Good w/ comment": "Boa com comentário", "Good w/o comment": "Boa sem comentário",
            "Bad w/ comment": "Ruim com comentário", "Bad w/o comment": "Ruim sem comentário",
        })
        positive = int(csat_breakdown.loc[csat_breakdown["Categoria"].str.startswith("Boa"), "Tickets"].sum())
        negative = int(csat_breakdown.loc[csat_breakdown["Categoria"].str.startswith("Ruim"), "Tickets"].sum())
        st.markdown(f"- Índice de satisfação: **{pct(kpi['csat'])}**")
        st.markdown(f"- Taxa de resposta: **{pct(kpi['survey_rate'])}**")
        st.markdown(f"- **:green[{positive} positivas]** e **:red[{negative} negativas]**")
        csat_fig = px.pie(
            csat_breakdown, values="Tickets", names="Categoria", hole=.63,
            color="Categoria", color_discrete_map={
                "Boa com comentário": "#11875D", "Boa sem comentário": "#39A87E",
                "Ruim com comentário": "#C93445", "Ruim sem comentário": "#ED5968",
            },
        )
        csat_fig.update_traces(textposition="outside", textinfo="value+percent")
        csat_fig.update_layout(height=390, margin=dict(l=10, r=10, t=10, b=10), legend_title="", paper_bgcolor="white")
        st.plotly_chart(csat_fig, width="stretch", config={"displayModeBar": False})

    if detail:
        st.caption(f"Base detalhada: {detail['filename']} • {detail['all_rows']:,} tickets no arquivo • período filtrado conforme o fechamento dos relatórios.")

with tabs[1]:
    left, right = st.columns([1.2, 1])
    with left:
        section_title("Tickets por canal")
        channel_counts = metric_chart(data["channels"], "Tickets")
        channel_counts = channel_counts.groupby("Categoria", as_index=False)["Valor"].max().sort_values("Valor")
        fig = px.bar(channel_counts, x="Valor", y="Categoria", orientation="h", text_auto=True,
                     color="Valor", color_continuous_scale=[[0, "#FBE7E1"], [1, COLORS["coral"]]])
        fig.update_layout(coloraxis_showscale=False, xaxis_title="Tickets", yaxis_title="")
        st.plotly_chart(fig, width="stretch")
    with right:
        section_title("Distribuição por hora", "Percentual das criações em cada hora do dia.")
        hourly = data["hourly"].copy()
        hourly["Hora"] = pd.to_numeric(hourly["Categoria"], errors="coerce")
        fig = px.area(hourly.sort_values("Hora"), x="Hora", y="Valor", markers=True, color_discrete_sequence=[COLORS["blue"]])
        fig.update_layout(yaxis_title="Participação (%)", xaxis=dict(dtick=2))
        st.plotly_chart(fig, width="stretch")

    section_title("Composição diária por canal")
    channel_daily = data["daily_channels"]
    fig = px.bar(channel_daily, x="Data", y="Valor", color="Categoria", barmode="stack")
    fig.update_layout(yaxis_title="Tickets", legend_title="Canal", hovermode="x unified")
    st.plotly_chart(fig, width="stretch")

    if data["detail"]:
        detail_created = data["detail"]["created"]
        section_title("Principais motivos de contato", "Calculado na base detalhada; dados pessoais não são carregados pelo app.")
        reason_counts = detail_created["Motivo"].value_counts().rename_axis("Motivo").reset_index(name="Tickets").head(15)
        fig = px.bar(reason_counts.sort_values("Tickets"), x="Tickets", y="Motivo", orientation="h", text_auto=True,
                     color="Tickets", color_continuous_scale=[[0, "#E7F1F8"], [1, COLORS["navy"]]])
        fig.update_layout(coloraxis_showscale=False, xaxis_title="Tickets", yaxis_title="")
        st.plotly_chart(fig, width="stretch")
        with st.expander("Cruzar canal e motivo"):
            motive_channel = detail_created.groupby(["Motivo", "Canal"], as_index=False).size().rename(columns={"size": "Tickets"})
            motive_channel = motive_channel[motive_channel["Motivo"].isin(reason_counts["Motivo"])]
            st.dataframe(motive_channel.sort_values(["Motivo", "Tickets"], ascending=[True, False]), hide_index=True, width="stretch")

with tabs[2]:
    metrics = st.columns(4)
    metrics[0].metric("1ª resposta mediana", format_minutes(kpi["first_reply_min"]))
    metrics[1].metric("Resolução total mediana", format_hours(kpi["resolution_h"]))
    metrics[2].metric("Espera do solicitante", format_hours(kpi["requester_wait_h"]))
    metrics[3].metric("Resolvidos em 1 contato", pct(kpi["one_touch"]))

    configurations = [
        ("Faixas de primeira resposta", data["reply_buckets"]),
        ("Faixas de resolução total", data["resolution_buckets"]),
        ("Faixas de espera do solicitante", data["wait_buckets"]),
    ]
    cols = st.columns(3)
    for column, (title, frame) in zip(cols, configurations):
        with column:
            section_title(title)
            counts = metric_chart(frame, "Tickets resolvidos")
            counts = counts.groupby("Categoria", as_index=False)["Valor"].max()
            fig = px.bar(counts, x="Categoria", y="Valor", color="Valor", text_auto=True,
                         color_continuous_scale=[[0, "#E7F1F8"], [1, COLORS["blue"]]])
            fig.update_layout(coloraxis_showscale=False, xaxis_title="", yaxis_title="Tickets")
            st.plotly_chart(fig, width="stretch")

with tabs[3]:
    team = data["team"].copy()
    numeric_columns = [column for column in team.columns if column != "Agente"]
    for column in numeric_columns:
        team[column] = pd.to_numeric(team[column], errors="coerce")
    team = team[team["Tickets resolvidos"].fillna(0).gt(0)].copy()

    metric_options = {
        "Tickets resolvidos": "Tickets resolvidos",
        "Tempo da primeira resposta (h)": "1ª resposta (h)",
        "Tempo total de resolução (h)": "Resolução total (h)",
        "% de score de satisfação": "CSAT",
        "% de tickets resolvidos em um contato": "One-touch",
    }
    selected_metric = st.selectbox("Comparar agentes por", list(metric_options), format_func=metric_options.get)
    chart_team = team.sort_values(selected_metric, ascending=False)
    fig = px.bar(chart_team, x="Agente", y=selected_metric, color=selected_metric, text_auto=".2s",
                 color_continuous_scale=[[0, "#FBE7E1"], [1, COLORS["coral"]]])
    if selected_metric.startswith("%"):
        fig.update_yaxes(tickformat=".0%")
    fig.update_layout(coloraxis_showscale=False, xaxis_title="", yaxis_title=metric_options[selected_metric])
    st.plotly_chart(fig, width="stretch")

    display_columns = [
        "Agente", "Tickets resolvidos", "Tempo da primeira resposta (h)", "Tempo de espera do solicitante (h)",
        "Tempo total de resolução (h)", "% de score de satisfação", "% de tickets resolvidos em um contato",
        "Atualizações", "Comentários públicos", "Comentários internos",
    ]
    st.dataframe(
        team[[column for column in display_columns if column in team.columns]].sort_values("Tickets resolvidos", ascending=False),
        hide_index=True, width="stretch",
        column_config={
            "% de score de satisfação": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=1),
            "% de tickets resolvidos em um contato": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=1),
        },
    )
    if data["detail"]:
        with st.expander("Drill-down operacional por agente (sem dados pessoais)"):
            agent = st.selectbox("Agente", sorted(data["detail"]["solved"]["Assignee"].dropna().unique()), key="detail_agent")
            agent_tickets = data["detail"]["solved"].loc[
                data["detail"]["solved"]["Assignee"].eq(agent),
                ["Id", "Group", "Canal", "Created at", "Solved at", "Replies", "Reopens", "Satisfaction Score",
                 "First reply time in minutes within business hours", "Full resolution time in minutes within business hours"],
            ].sort_values("Solved at", ascending=False)
            st.dataframe(agent_tickets, hide_index=True, width="stretch")

with tabs[4]:
    metrics = st.columns(4)
    metrics[0].metric("Não resolvidos", f"{kpi['unsolved']:.0f}")
    metrics[1].metric("Sem resposta", f"{kpi['unreplied']:.0f}", f"{kpi['unreplied'] / kpi['unsolved']:.1%} da fila")
    metrics[2].metric("Idade mediana", f"{kpi['age_days']:.1f} dias")
    metrics[3].metric("Pendente", f"{data['backlog_status'].loc[data['backlog_status']['Categoria'].eq('Pendente'), 'Valor'].sum():.0f}")

    left, right = st.columns(2)
    with left:
        section_title("Evolução semanal por status")
        fig = px.line(data["weekly_backlog_status"], x="Data", y="Valor", color="Categoria", markers=True)
        fig.update_layout(yaxis_title="Tickets", legend_title="Status", hovermode="x unified")
        st.plotly_chart(fig, width="stretch")
    with right:
        section_title("Evolução semanal por grupo")
        groups = data["weekly_backlog_group"]
        groups = groups[groups["Categoria"].ne("Não informado")]
        fig = px.line(groups, x="Data", y="Valor", color="Categoria", markers=True)
        fig.update_layout(yaxis_title="Tickets", legend_title="Grupo", hovermode="x unified")
        st.plotly_chart(fig, width="stretch")

    left, right = st.columns([1.1, 1])
    with left:
        section_title("Fila por responsável")
        agents = data["backlog_agents"].rename(columns={"Nome do atribuído": "Agente"}).copy()
        agents["Agente"] = agents["Agente"].map(lambda value: clean_name(value) or "Sem atribuição")
        st.dataframe(agents, hide_index=True, width="stretch")
    with right:
        section_title("Fila por grupo e status")
        group_status = data["backlog_groups"]
        fig = px.bar(group_status, x="Grupo", y="Tickets", color="Status", barmode="stack", text_auto=True)
        fig.update_layout(xaxis_title="", yaxis_title="Tickets", legend_title="Status")
        st.plotly_chart(fig, width="stretch")

with tabs[5]:
    metrics = st.columns(5)
    metrics[0].metric("CSAT", pct(kpi["csat"]))
    metrics[1].metric("Boletins respondidos", f"{kpi['rated']:.0f}")
    metrics[2].metric("Taxa de resposta", pct(kpi["survey_rate"]), f"de {kpi['surveyed']:.0f} pesquisas")
    metrics[3].metric("SLA cumprido", pct(kpi["sla_rate"]))
    metrics[4].metric("Amostra SLA", f"{kpi['sla_achieved'] + kpi['sla_breached']:.0f} tickets")

    if kpi["sla_achieved"] + kpi["sla_breached"] < 30:
        st.warning("Atenção: o SLA do mês está baseado em uma amostra pequena. Leia a taxa junto com o número de tickets elegíveis.")

    left, right = st.columns(2)
    with left:
        section_title("CSAT por canal")
        csat_channel = metric_chart(data["csat_channel"], "score de satisfação")
        fig = px.bar(csat_channel.sort_values("Valor"), x="Valor", y="Categoria", orientation="h", text_auto=".1%",
                     color="Valor", color_continuous_scale=[[0, COLORS["red"]], [0.75, COLORS["gold"]], [1, COLORS["green"]]])
        fig.update_xaxes(tickformat=".0%", range=[0, 1])
        fig.update_layout(coloraxis_showscale=False, xaxis_title="CSAT", yaxis_title="")
        st.plotly_chart(fig, width="stretch")
    with right:
        section_title("Histórico mensal do CSAT")
        csat_history = data["csat_monthly"]
        csat_history = csat_history[csat_history["Métrica"].str.contains("score", case=False, na=False)]
        fig = px.line(csat_history.sort_values("Período"), x="Período", y="Valor", markers=True, color_discrete_sequence=[COLORS["teal"]])
        fig.update_yaxes(tickformat=".0%", range=[0, 1])
        fig.update_layout(yaxis_title="CSAT", xaxis_title="")
        st.plotly_chart(fig, width="stretch")

    left, right = st.columns(2)
    with left:
        section_title("CSAT diário", "O volume de respostas varia bastante; use a curva como sinal, não como ranking isolado.")
        daily = data["csat_daily"]
        daily = daily[daily["Métrica"].str.contains("score", case=False, na=False)]
        fig = px.line(daily.sort_values("Data"), x="Data", y="Valor", markers=True, color_discrete_sequence=[COLORS["coral"]])
        fig.update_yaxes(tickformat=".0%", range=[0, 1])
        fig.update_layout(yaxis_title="CSAT", xaxis_title="")
        st.plotly_chart(fig, width="stretch")
    with right:
        section_title("SLA por mês")
        monthly = data["sla_monthly"]
        monthly = monthly[monthly["Métrica"].str.contains("%", regex=False, na=False)]
        fig = px.bar(monthly.sort_values("Período"), x="Período", y="Valor", text_auto=".1%", color_discrete_sequence=[COLORS["blue"]])
        fig.update_yaxes(tickformat=".0%", range=[0, 1])
        fig.update_layout(yaxis_title="Cumprimento", xaxis_title="")
        st.plotly_chart(fig, width="stretch")

with tabs[6]:
    section_title("Cobertura e limitações", "Este painel preserva o significado das exportações agregadas do Zendesk.")
    quality = pd.DataFrame([
        {"Indicador": "Volume", "Numerador": kpi["created"], "Base": kpi["created"], "Cobertura": 1.0, "Leitura": "Período completo exportado"},
        {"Indicador": "CSAT", "Numerador": kpi["rated"], "Base": kpi["solved"], "Cobertura": kpi["rated"] / kpi["solved"], "Leitura": "Avaliações sobre tickets resolvidos"},
        {"Indicador": "Resposta à pesquisa", "Numerador": kpi["rated"], "Base": kpi["surveyed"], "Cobertura": kpi["survey_rate"], "Leitura": "Avaliações sobre pesquisas enviadas"},
        {"Indicador": "SLA", "Numerador": kpi["sla_achieved"] + kpi["sla_breached"], "Base": kpi["created"], "Cobertura": (kpi["sla_achieved"] + kpi["sla_breached"]) / kpi["created"], "Leitura": "Tickets com política de SLA sobre entradas"},
    ])
    if data["detail"]:
        detail = data["detail"]
        detail_quality = pd.DataFrame([
            {"Indicador": "Base detalhada — criados", "Numerador": len(detail["created"]), "Base": kpi["created"], "Cobertura": len(detail["created"]) / kpi["created"], "Leitura": "Tickets detalhados sobre o total oficial"},
            {"Indicador": "Base detalhada — resolvidos", "Numerador": len(detail["solved"]), "Base": kpi["solved"], "Cobertura": len(detail["solved"]) / kpi["solved"], "Leitura": "Tickets detalhados sobre o total oficial"},
        ])
        quality = pd.concat([quality, detail_quality], ignore_index=True)
    st.dataframe(quality, hide_index=True, width="stretch",
                 column_config={"Cobertura": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=1)})
    st.markdown(
        """
        - Os relatórios trazem **agregados**, portanto não permitem abrir o ticket individual nem cruzar livremente canal, agente e SLA.
        - “Backlog atual” e “histórico semanal” são fotografias de momentos diferentes; não devem ser somados.
        - Tempos são medianas quando o relatório assim define, reduzindo o efeito de casos extremos.
        - Para investigação operacional ticket a ticket, acrescente no futuro uma exportação detalhada com ID, datas, canal, grupo, agente e status.
        """
    )
    if data["detail"]:
        st.success(f"Base detalhada carregada: {data['detail']['all_rows']:,} linhas e {data['detail']['duplicate_ids']} IDs duplicados.")
        st.warning("A ZIP original contém dados pessoais. O app ignora e não exibe e-mail, CPF/CNPJ, telefone, assunto e descrição.")
    with st.expander("Arquivos carregados"):
        for filename in data["files"]:
            st.code(filename, language=None)
