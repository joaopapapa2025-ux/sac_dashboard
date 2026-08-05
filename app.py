from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
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


st.markdown(
    """
    <style>
      .stApp { background: #F7F8FA; }
      [data-testid="stMetric"] { background: white; border: 1px solid #E7EAF0; border-radius: 16px; padding: 16px; }
      [data-testid="stMetricLabel"] { color: #667085; }
      [data-testid="stMetricValue"] { color: #183B56; }
      div[data-testid="stTabs"] button { font-weight: 700; }
      .block-container { padding-top: 2rem; padding-bottom: 4rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("🎧 Central de gestão do SAC")
st.caption("Fechamento mensal do Zendesk • volume, velocidade, equipe, backlog, SLA e voz do cliente")

repository_sources = discover_repository_sources()
with st.sidebar:
    st.header("Base de dados")
    st.caption("O painel lê automaticamente as oito planilhas na pasta do app. Você também pode testá-lo enviando os arquivos aqui.")
    uploads = st.file_uploader("Carregar exportações do Zendesk", type=["xlsx", "zip"], accept_multiple_files=True)
    sources = repository_sources | uploaded_sources(uploads or [])
    required_found = sum(key in sources for key in EXPECTED_FILES)
    st.progress(required_found / len(EXPECTED_FILES), text=f"{required_found} de {len(EXPECTED_FILES)} relatórios encontrados")
    for key, prefix in EXPECTED_FILES.items():
        st.write(("✅ " if key in sources else "⬜ ") + prefix.rstrip("_"))
    st.write(("✅ " if "detail" in sources else "➕ ") + "Base detalhada CSV.ZIP (recomendada)")
    if "detail" not in sources:
        st.caption("Sem a ZIP, o fechamento funciona, mas não mostra motivos nem drill-down por ticket.")

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
if pd.notna(period_start) and pd.notna(period_end):
    st.caption(f"Período principal: {period_start:%d/%m/%Y} a {period_end:%d/%m/%Y}")

tabs = st.tabs(["Visão executiva", "Demanda", "Eficiência", "Equipe", "Backlog", "Satisfação & SLA", "Qualidade dos dados"])

with tabs[0]:
    columns = st.columns(6)
    columns[0].metric("Tickets criados", f"{kpi['created']:,.0f}")
    columns[1].metric("Tickets resolvidos", f"{kpi['solved']:,.0f}", f"{kpi['solved'] - kpi['created']:+,.0f} vs. entrada")
    columns[2].metric("1ª resposta mediana", format_minutes(kpi["first_reply_min"]))
    columns[3].metric("Resolução mediana", format_hours(kpi["resolution_h"]))
    columns[4].metric("CSAT", pct(kpi["csat"]), f"{kpi['rated']:.0f} avaliações")
    columns[5].metric("Backlog atual", f"{kpi['unsolved']:,.0f}", f"{kpi['unreplied']:.0f} sem resposta")

    left, right = st.columns([1.65, 1])
    with left:
        section_title("Ritmo diário", "Entradas e resoluções no período selecionado no Zendesk.")
        fig = px.line(data["daily_volume"], x="Data", y="Valor", color="Métrica", markers=True,
                      color_discrete_map={"Criados": COLORS["coral"], "Resolvidos": COLORS["navy"]})
        fig.update_layout(yaxis_title="Tickets", legend_title="", hovermode="x unified")
        st.plotly_chart(fig, width="stretch")
    with right:
        section_title("Backlog por status", "Foto atual do relatório de tickets não resolvidos.")
        status = data["backlog_status"]
        fig = px.bar(status, x="Categoria", y="Valor", color="Categoria",
                     color_discrete_sequence=[COLORS["blue"], COLORS["coral"], COLORS["gold"]], text_auto=True)
        fig.update_layout(showlegend=False, xaxis_title="", yaxis_title="Tickets")
        st.plotly_chart(fig, width="stretch")

    st.markdown("#### Leitura gerencial")
    daily_created = data["daily_volume"].query("Métrica == 'Criados'")
    peak = daily_created.loc[daily_created["Valor"].idxmax()] if not daily_created.empty else None
    pending = status.loc[status["Categoria"].eq("Pendente"), "Valor"].sum()
    insights = [
        f"A equipe resolveu **{kpi['solved'] - kpi['created']:.0f} tickets a mais** do que recebeu no mês.",
        f"O pico de entrada foi **{peak['Valor']:.0f} tickets em {peak['Data']:%d/%m}**." if peak is not None else "Sem série diária disponível.",
        f"**{pending:.0f} tickets** do backlog atual estão pendentes, equivalentes a {pending / kpi['unsolved']:.0%} da fila." if kpi["unsolved"] else "Backlog zerado.",
        f"O CSAT está em **{pct(kpi['csat'])}**, mas somente **{kpi['rated']:.0f} tickets** foram avaliados.",
    ]
    for insight in insights:
        st.markdown(f"- {insight}")

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
