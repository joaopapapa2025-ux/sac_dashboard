from __future__ import annotations

from io import BytesIO
from pathlib import Path
from datetime import datetime, timezone
import html
import subprocess

import pandas as pd
import plotly.express as px
import streamlit as st


st.set_page_config(
    page_title="Fechamento do SAC",
    page_icon="🎧",
    layout="wide",
    initial_sidebar_state="expanded",
)

BASE_DIR = Path(__file__).resolve().parent


# =============================================================================
# ✏️ ATUALIZAÇÃO MANUAL — ALTERE SOMENTE ESTE BLOCO A CADA FECHAMENTO
# =============================================================================

ANO_REFERENCIA = 2026
MES_REFERENCIA = 7
NOME_MES_REFERENCIA = "Julho de 2026"

# Metas do SAC em horas. Quanto menor o resultado, melhor.
META_TEMPO_RESPOSTA_H = 28.0
META_TEMPO_RESOLUCAO_H = 55.0

# Reclame Aqui
RA_NOTA = 8.8
RA_NOTA_MES_ANTERIOR = 8.3
RA_RECLAMACOES = 19
RA_RECLAMACOES_MES_ANTERIOR = 7
RA_RESPONDIDAS_PCT = 100.0
RA_VOLTARIAM_PCT = 80.8
RA_INDICE_SOLUCAO_PCT = 94.2
RA_NOTA_CONSUMIDOR = 7.77
RA_TEMPO_MEDIO_RESPOSTA = "8 dias e 12 horas"

# Categorias das reclamações no Reclame Aqui.
RA_CATEGORIAS_RECLAMACOES = {
    "Problemas de qualidade": 11,
    "Questões logísticas": 4,
    "Experiência de compra e atendimento": 4,
}

# Categorias das avaliações no Reclame Aqui. Preencha as quantidades manualmente.
# Se todas estiverem zeradas, o dashboard mostrará um aviso no lugar do gráfico.
RA_CATEGORIAS_AVALIACOES = {
    "Positivas": 7,
    "Neutras": 2,
    "Negativas": 2,
}

# =============================================================================
# FIM DO BLOCO DE ATUALIZAÇÃO MANUAL
# =============================================================================


COLORS = {
    "navy": "#173B5E",
    "blue": "#4F91CF",
    "blue_light": "#DCEBFA",
    "teal": "#16886A",
    "teal_light": "#DDF3EC",
    "red": "#C83C4D",
    "red_light": "#FBE5E8",
    "gold": "#D99A2B",
    "text": "#172B3A",
    "muted": "#667085",
    "line": "#E3E9EF",
    "surface": "#FFFFFF",
    "background": "#F4F7FA",
}

REQUIRED_COLUMNS = {
    "Id",
    "Assignee",
    "Group",
    "Status",
    "Via",
    "Created at",
    "Solved at",
    "Satisfaction Score",
    "First reply time in minutes",
    "Full resolution time in minutes",
    "Motivo do Contato [list]",
}


def format_number(value: float | int) -> str:
    return f"{value:,.0f}".replace(",", ".")


def format_decimal(value: float, digits: int = 1) -> str:
    if pd.isna(value):
        return "—"
    return f"{value:.{digits}f}".replace(".", ",")


def format_percent(value: float, digits: int = 1) -> str:
    if pd.isna(value):
        return "—"
    return f"{value * 100:.{digits}f}%".replace(".", ",")


def find_zip() -> Path | None:
    files = sorted(BASE_DIR.glob("export-*.csv.zip"), key=lambda path: path.name, reverse=True)
    return files[0] if files else None


@st.cache_data(show_spinner="Lendo a base detalhada do Zendesk...")
def read_zip(source: str | bytes, signature: float | int) -> pd.DataFrame:
    del signature
    target = BytesIO(source) if isinstance(source, bytes) else source
    frame = pd.read_csv(target, compression="zip", dtype=str, low_memory=False)

    missing = REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError("A base não contém as colunas esperadas: " + ", ".join(sorted(missing)))

    frame = frame[list(REQUIRED_COLUMNS)].copy()
    frame["Created at"] = pd.to_datetime(frame["Created at"], errors="coerce")
    frame["Solved at"] = pd.to_datetime(frame["Solved at"], errors="coerce")
    frame["First reply time in minutes"] = pd.to_numeric(
        frame["First reply time in minutes"], errors="coerce"
    )
    frame["Full resolution time in minutes"] = pd.to_numeric(
        frame["Full resolution time in minutes"], errors="coerce"
    )
    # Horas corridas: diferença real entre criação e solução, sem calendário comercial.
    frame["Resolution elapsed hours"] = (
        frame["Solved at"] - frame["Created at"]
    ).dt.total_seconds() / 3600
    frame["Motivo do Contato [list]"] = (
        frame["Motivo do Contato [list]"]
        .replace({"-": "Não informado", "": "Não informado"})
        .fillna("Não informado")
    )
    frame["Via"] = frame["Via"].replace(
        {
            "Mail": "E-mail",
            "Instagram DM": "Instagram Direct",
            "Native Messaging": "Messaging",
            "Web form": "Formulário web",
            "Closed Ticket": "Ticket fechado",
        }
    )
    return frame


def resolved_tickets(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[
        frame["Solved at"].notna()
        & frame["Status"].fillna("").str.casefold().isin({"solved", "closed"})
    ].copy()


def metric_card(label: str, value: str, detail: str, tone: str = "blue") -> str:
    safe_label = html.escape(label)
    safe_value = html.escape(value)
    safe_detail = html.escape(detail)
    return (
        f'<div class="metric-card metric-{tone}">'
        f'<div class="metric-label">{safe_label}</div>'
        f'<div class="metric-value">{safe_value}</div>'
        f'<div class="metric-detail">{safe_detail}</div>'
        '</div>'
    )


def performance_row(label: str, target: float, actual: float) -> str:
    delta = actual - target
    variation = delta / target if target else 0
    achieved = actual <= target
    status_class = "good" if achieved else "bad"
    status_text = "Dentro da meta" if achieved else "Acima da meta"
    sign = "+" if delta > 0 else ""
    return (
        '<div class="performance-row">'
        f'<div class="performance-name">{html.escape(label)}</div>'
        f'<div><span class="cell-label">Objetivo</span><strong>{format_decimal(target)} h</strong></div>'
        f'<div><span class="cell-label">Realizado</span><strong>{format_decimal(actual)} h</strong></div>'
        f'<div><span class="cell-label">Diferença</span><strong>{sign}{format_decimal(delta)} h</strong></div>'
        f'<div><span class="cell-label">Variação</span><strong>{sign}{format_percent(variation)}</strong></div>'
        f'<div><span class="status-pill {status_class}">{status_text}</span></div>'
        '</div>'
    )


def finish_figure(figure):
    """Mantém os gráficos idênticos em tema claro, escuro e extensões do navegador."""
    figure.update_layout(
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Arial, sans-serif", color=COLORS["text"], size=12),
        title_font=dict(color=COLORS["navy"], size=16),
        legend_font=dict(color=COLORS["text"], size=11),
        hoverlabel=dict(bgcolor="white", font_color=COLORS["text"]),
    )
    figure.update_xaxes(
        color=COLORS["muted"],
        gridcolor="#E9EEF3",
        zerolinecolor="#D7E0E8",
    )
    figure.update_yaxes(color=COLORS["muted"], gridcolor="rgba(0,0,0,0)")
    return figure


def repository_file_datetime(path: Path) -> datetime:
    """Data do último commit que alterou a ZIP; fallback para modificação do arquivo."""
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%cI", "--", path.name],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        if result.stdout.strip():
            return datetime.fromisoformat(result.stdout.strip())
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def source_from_repository_or_upload() -> tuple[
    str | bytes | None, str, float | int, datetime | None
]:
    repository_zip = find_zip()
    if repository_zip:
        return (
            str(repository_zip),
            repository_zip.name,
            repository_zip.stat().st_mtime,
            repository_file_datetime(repository_zip),
        )

    uploaded = st.file_uploader(
        "A ZIP ainda não está no repositório. Selecione-a para testar:",
        type=["zip"],
        accept_multiple_files=False,
    )
    if uploaded:
        payload = uploaded.getvalue()
        return payload, uploaded.name, len(payload), datetime.now().astimezone()
    return None, "", 0, None


st.markdown(
    """
    <style>
      :root {
        --navy: #173B5E;
        --blue: #4F91CF;
        --teal: #16886A;
        --red: #C83C4D;
        --text: #172B3A;
        --muted: #667085;
        --line: #E3E9EF;
        --background: #F4F7FA;
      }
      .stApp { background: var(--background); }
      .block-container { max-width: 1380px; padding-top: 1.5rem; padding-bottom: 4rem; }
      #MainMenu, footer { visibility: hidden; }
      header[data-testid="stHeader"] { background: transparent; }

      .hero {
        background: linear-gradient(120deg, #173B5E 0%, #2D6F9F 58%, #5AA0D6 100%);
        border-radius: 24px;
        padding: 28px 32px;
        color: white;
        box-shadow: 0 16px 38px rgba(23, 59, 94, .16);
        margin-bottom: 22px;
      }
      .hero-eyebrow { font-size: 12px; font-weight: 700; letter-spacing: .14em; opacity: .72; }
      .hero h1 { margin: 7px 0 5px; font-size: clamp(26px, 3vw, 38px); line-height: 1.15; }
      .hero p { margin: 0; opacity: .86; font-size: 15px; }

      .metric-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 14px;
        margin-bottom: 26px;
      }
      .metric-card {
        min-width: 0;
        background: white;
        border: 1px solid var(--line);
        border-radius: 18px;
        padding: 18px 20px;
        box-shadow: 0 8px 26px rgba(23, 59, 94, .055);
        border-top: 4px solid #4F91CF;
      }
      .metric-teal { border-top-color: #16886A; }
      .metric-gold { border-top-color: #D99A2B; }
      .metric-red { border-top-color: #C83C4D; }
      .metric-label { color: var(--muted); font-size: 13px; font-weight: 650; }
      .metric-value {
        color: var(--navy); font-size: clamp(27px, 3vw, 39px); font-weight: 780;
        letter-spacing: -.04em; line-height: 1.1; margin: 8px 0 6px;
      }
      .metric-detail { color: var(--muted); font-size: 12px; min-height: 18px; }

      .section-heading { margin: 8px 0 13px; }
      .section-title { color: var(--navy); font-size: 21px; font-weight: 780; }
      .section-caption { color: var(--muted); font-size: 13px; margin-top: 2px; }

      .performance-table {
        background: white;
        border: 1px solid var(--line);
        border-radius: 18px;
        overflow: hidden;
        box-shadow: 0 8px 26px rgba(23, 59, 94, .05);
        margin-bottom: 28px;
      }
      .performance-row {
        display: grid;
        grid-template-columns: 1.55fr repeat(3, .8fr) .9fr 1fr;
        align-items: center;
        gap: 16px;
        padding: 18px 20px;
        border-bottom: 1px solid var(--line);
      }
      .performance-row:last-child { border-bottom: 0; }
      .performance-name { color: var(--navy); font-weight: 760; font-size: 15px; }
      .cell-label { display: block; color: var(--muted); font-size: 10px; text-transform: uppercase; letter-spacing: .07em; }
      .performance-row strong { color: var(--text); font-size: 15px; }
      .status-pill { display: inline-block; border-radius: 999px; padding: 7px 11px; font-size: 12px; font-weight: 750; text-align: center; }
      .status-pill.good { color: #087557; background: #DDF3EC; }
      .status-pill.bad { color: #B12D3D; background: #FBE5E8; }

      .info-card {
        background: white;
        border: 1px solid var(--line);
        border-radius: 20px;
        padding: 21px 23px;
        box-shadow: 0 8px 26px rgba(23, 59, 94, .05);
        margin-bottom: 12px;
      }
      .card-heading { color: var(--navy); font-size: 22px; font-weight: 780; margin-bottom: 4px; }
      .card-caption { color: var(--muted); font-size: 13px; margin-bottom: 18px; }
      .ra-score { color: #16886A; font-size: 48px; font-weight: 800; line-height: 1; letter-spacing: -.04em; }
      .ra-score-label { color: var(--muted); font-size: 12px; margin: 5px 0 17px; }
      .mini-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
      .mini-item { background: #F7F9FB; border-radius: 13px; padding: 11px 12px; }
      .mini-value { color: var(--navy); font-size: 18px; font-weight: 780; }
      .mini-label { color: var(--muted); font-size: 10px; margin-top: 2px; }
      .insight { color: var(--text); font-size: 14px; padding: 7px 0; }
      .source-note { color: var(--muted); font-size: 11px; text-align: right; margin-top: 16px; }

      .filter-period {
        background: white; border: 1px solid var(--line); border-radius: 12px;
        padding: 11px 13px; color: var(--navy); font-size: 14px; font-weight: 720;
        margin: -3px 0 17px;
      }
      .filter-period span { display: block; color: var(--muted); font-size: 10px; font-weight: 500; margin-top: 2px; }

      .agent-grid {
        display: grid; grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 14px; margin-bottom: 30px;
      }
      .agent-card {
        min-width: 0; background: white; border: 1px solid var(--line); border-radius: 18px;
        padding: 18px; box-shadow: 0 8px 26px rgba(23, 59, 94, .05);
      }
      .agent-head { display: flex; justify-content: space-between; align-items: center; gap: 10px; margin-bottom: 16px; }
      .agent-name { color: var(--navy); font-size: 17px; font-weight: 780; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .agent-volume { color: var(--blue); font-size: 25px; line-height: 1; font-weight: 800; letter-spacing: -.03em; }
      .agent-volume-label { color: var(--muted); font-size: 9px; text-align: right; margin-top: 3px; }
      .agent-stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 7px; }
      .agent-stat { background: #F7F9FB; border-radius: 11px; padding: 10px 8px; min-width: 0; }
      .agent-stat strong { display: block; color: var(--navy); font-size: 15px; white-space: nowrap; }
      .agent-stat span { display: block; color: var(--muted); font-size: 9px; line-height: 1.25; margin-top: 3px; }
      .agent-csat-good strong { color: var(--teal); }
      .agent-csat-low strong { color: var(--red); }

      @media (max-width: 900px) {
        .metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        .agent-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        .performance-row { grid-template-columns: 1fr 1fr; gap: 12px; }
        .performance-name, .performance-row > div:last-child { grid-column: 1 / -1; }
      }
      @media (max-width: 560px) {
        .block-container { padding-left: .8rem; padding-right: .8rem; }
        .hero { padding: 23px 20px; border-radius: 18px; }
        .metric-grid { grid-template-columns: 1fr; }
        .agent-grid { grid-template-columns: 1fr; }
        .mini-grid { grid-template-columns: 1fr; }
      }
    </style>
    """,
    unsafe_allow_html=True,
)


source, source_name, source_signature, source_updated_at = source_from_repository_or_upload()
if source is None:
    st.info("Envie para o GitHub um arquivo com nome `export-*.csv.zip`. O dashboard fará a leitura automaticamente.")
    st.stop()

try:
    raw = read_zip(source, source_signature)
    solved_all = resolved_tickets(raw)
except Exception as error:
    st.error("Não foi possível ler a ZIP do Zendesk.")
    st.exception(error)
    st.stop()

if solved_all.empty:
    st.error("A ZIP não possui tickets resolvidos.")
    st.stop()

solved_all["Assignee"] = solved_all["Assignee"].fillna("Não atribuído").replace("", "Não atribuído")
month_counts = solved_all["Solved at"].dropna().dt.to_period("M").value_counts()
# Descarta meses residuais de tickets históricos. Mantém meses com ao menos 5%
# do volume do principal mês (e no mínimo 5 tickets).
relevant_month_minimum = max(5, int(month_counts.max() * .05))
relevant_month_counts = month_counts[month_counts.ge(relevant_month_minimum)]
available_months = sorted(relevant_month_counts.index.tolist(), reverse=True)
default_period = pd.Period(year=ANO_REFERENCIA, month=MES_REFERENCIA, freq="M")
if default_period in month_counts.index and default_period not in available_months:
    available_months.append(default_period)
    available_months.sort(reverse=True)
default_index = available_months.index(default_period) if default_period in available_months else 0

st.sidebar.header("Filtros")
if len(available_months) == 1:
    selected_period = available_months[0]
    period_ticket_count = int(month_counts.get(selected_period, 0))
    st.sidebar.markdown(
        f'<div style="font-size:14px;margin-bottom:7px">Mês de resolução</div>'
        f'<div class="filter-period">{selected_period.strftime("%m/%Y")}'
        f'<span>{format_number(period_ticket_count)} tickets resolvidos</span></div>',
        unsafe_allow_html=True,
    )
else:
    selected_period = st.sidebar.selectbox(
        "Mês de resolução",
        available_months,
        index=default_index,
        format_func=lambda value: f'{value.strftime("%m/%Y")} · {format_number(int(month_counts.get(value, 0)))} resolvidos',
    )
month_start = selected_period.start_time
month_end = selected_period.end_time
month_solved = solved_all[
    solved_all["Solved at"].between(month_start, month_end, inclusive="both")
].copy()

first_day = month_solved["Solved at"].min().date()
last_day = month_solved["Solved at"].max().date()
selected_dates = st.sidebar.date_input(
    "Dias considerados",
    value=(first_day, last_day),
    min_value=first_day,
    max_value=last_day,
    format="DD/MM/YYYY",
)
if isinstance(selected_dates, tuple) and len(selected_dates) == 2:
    selected_start, selected_end = selected_dates
else:
    selected_start = selected_end = selected_dates[0] if isinstance(selected_dates, tuple) else selected_dates

agent_options = sorted(month_solved["Assignee"].dropna().unique().tolist())
selected_agents = st.sidebar.multiselect("Agentes", agent_options, placeholder="Todos os agentes")

start_datetime = pd.Timestamp(selected_start)
end_datetime = pd.Timestamp(selected_end) + pd.Timedelta(days=1)
solved = month_solved[
    month_solved["Solved at"].ge(start_datetime) & month_solved["Solved at"].lt(end_datetime)
].copy()
if selected_agents:
    solved = solved[solved["Assignee"].isin(selected_agents)].copy()

if solved.empty:
    st.warning("Nenhum ticket resolvido corresponde aos filtros selecionados.")
    st.stop()

MONTH_NAMES = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio", 6: "Junho",
    7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro",
}
period_name = f"{MONTH_NAMES[selected_period.month]} de {selected_period.year}"
if source_updated_at:
    updated_stamp = pd.Timestamp(source_updated_at)
    if updated_stamp.tzinfo is None:
        updated_stamp = updated_stamp.tz_localize("UTC")
    updated_stamp = updated_stamp.tz_convert("America/Sao_Paulo")
    updated_text = updated_stamp.strftime("%d/%m/%Y às %H:%M")
else:
    updated_text = "não disponível"

# Indicadores: somente tickets resolvidos no período filtrado.
response_hours = solved["First reply time in minutes"].median() / 60
resolution_hours = solved["Resolution elapsed hours"].median()
satisfaction = solved["Satisfaction Score"].fillna("Not Offered")
good_count = int(satisfaction.eq("Good").sum())
bad_count = int(satisfaction.eq("Bad").sum())
offered_count = int(satisfaction.eq("Offered").sum())
rated_count = good_count + bad_count
surveyed_count = rated_count + offered_count
csat_rate = good_count / rated_count if rated_count else float("nan")
survey_response_rate = rated_count / surveyed_count if surveyed_count else float("nan")
response_status = "Dentro da meta" if response_hours <= META_TEMPO_RESPOSTA_H else "Acima da meta"
resolution_status = "Dentro da meta" if resolution_hours <= META_TEMPO_RESOLUCAO_H else "Acima da meta"

st.markdown(
    '<div class="hero">'
    '<div class="hero-eyebrow">GESTÃO DE ATENDIMENTO</div>'
    '<h1>Dashboard SAC</h1>'
    '<p>Visão executiva da operação, experiência do cliente e desempenho do time.</p>'
    f'<p style="margin-top:10px;font-size:12px;opacity:.72">Período selecionado: {html.escape(period_name)} • Base atualizada no GitHub em {html.escape(updated_text)}</p>'
    '</div>',
    unsafe_allow_html=True,
)

cards = "".join([
    metric_card("Tempo de resposta", f"{format_decimal(response_hours)} h", f"Meta: {format_decimal(META_TEMPO_RESPOSTA_H)} h • {response_status}", "teal" if response_hours <= META_TEMPO_RESPOSTA_H else "red"),
    metric_card("Tempo de resolução", f"{format_decimal(resolution_hours)} h", f"Horas corridas • Meta: {format_decimal(META_TEMPO_RESOLUCAO_H)} h", "teal" if resolution_hours <= META_TEMPO_RESOLUCAO_H else "red"),
    metric_card("CSAT", format_percent(csat_rate), f"{format_number(rated_count)} avaliações respondidas", "blue"),
    metric_card("Tickets resolvidos", format_number(len(solved)), f"De {selected_start.strftime('%d/%m')} a {selected_end.strftime('%d/%m')}", "gold"),
])
st.markdown(f'<div class="metric-grid">{cards}</div>', unsafe_allow_html=True)

st.markdown('<div class="section-heading"><div class="section-title">Meta x realizado</div><div class="section-caption">Quanto menor o tempo, melhor o resultado.</div></div>', unsafe_allow_html=True)
performance_html = performance_row("Tempo de resposta", META_TEMPO_RESPOSTA_H, response_hours) + performance_row("Tempo de resolução (horas corridas)", META_TEMPO_RESOLUCAO_H, resolution_hours)
st.markdown(f'<div class="performance-table">{performance_html}</div>', unsafe_allow_html=True)

st.markdown('<div class="section-heading"><div class="section-title">Tempo de resolução por motivo</div><div class="section-caption">Mediana em horas corridas, somente para tickets resolvidos.</div></div>', unsafe_allow_html=True)
resolution_reason = (
    solved.groupby("Motivo do Contato [list]", as_index=False)
    .agg(**{"Tempo mediano (h)": ("Resolution elapsed hours", "median"), "Tickets": ("Id", "count")})
    .dropna(subset=["Tempo mediano (h)"])
)
resolution_reason = resolution_reason.nlargest(12, "Tickets").sort_values("Tempo mediano (h)")
resolution_reason_figure = px.bar(
    resolution_reason, x="Tempo mediano (h)", y="Motivo do Contato [list]", orientation="h",
    text="Tempo mediano (h)", hover_data={"Tickets": True, "Tempo mediano (h)": ":.1f"},
    color="Tempo mediano (h)", color_continuous_scale=[[0, "#CFE8E0"], [1, COLORS["navy"]]],
)
resolution_reason_figure.update_traces(texttemplate="%{text:.1f} h", textposition="outside", cliponaxis=False)
resolution_reason_figure.update_layout(height=430, margin=dict(l=10, r=65, t=10, b=35), xaxis_title="Horas corridas", yaxis_title="", coloraxis_showscale=False, paper_bgcolor="white", plot_bgcolor="white")
st.plotly_chart(finish_figure(resolution_reason_figure), width="stretch", theme=None, config={"displayModeBar": False})

st.markdown('<div class="section-heading"><div class="section-title">Visão por agente</div><div class="section-caption">Volume, velocidade e satisfação de cada responsável.</div></div>', unsafe_allow_html=True)
agent_rows = []
for agent_name, agent_data in solved.groupby("Assignee"):
    agent_satisfaction = agent_data["Satisfaction Score"]
    agent_good = int(agent_satisfaction.eq("Good").sum())
    agent_bad = int(agent_satisfaction.eq("Bad").sum())
    agent_rated = agent_good + agent_bad
    agent_rows.append({
        "Agente": agent_name,
        "Tickets resolvidos": len(agent_data),
        "Resposta mediana (h)": agent_data["First reply time in minutes"].median() / 60,
        "Resolução mediana (h)": agent_data["Resolution elapsed hours"].median(),
        "Avaliações": agent_rated,
        "CSAT": agent_good / agent_rated if agent_rated else float("nan"),
    })
agent_summary = pd.DataFrame(agent_rows).sort_values("Tickets resolvidos", ascending=False)
agent_cards = []
for _, agent in agent_summary.iterrows():
    agent_csat = agent["CSAT"]
    csat_class = "agent-csat-good" if pd.notna(agent_csat) and agent_csat >= .75 else "agent-csat-low"
    csat_text = format_percent(agent_csat) if pd.notna(agent_csat) else "—"
    agent_cards.append(
        '<div class="agent-card">'
        '<div class="agent-head">'
        f'<div class="agent-name">{html.escape(str(agent["Agente"]))}</div>'
        '<div>'
        f'<div class="agent-volume">{format_number(agent["Tickets resolvidos"])}</div>'
        '<div class="agent-volume-label">resolvidos</div>'
        '</div></div>'
        '<div class="agent-stats">'
        f'<div class="agent-stat"><strong>{format_decimal(agent["Resposta mediana (h)"])} h</strong><span>Resposta mediana</span></div>'
        f'<div class="agent-stat"><strong>{format_decimal(agent["Resolução mediana (h)"])} h</strong><span>Resolução mediana</span></div>'
        f'<div class="agent-stat {csat_class}"><strong>{csat_text}</strong><span>CSAT · {format_number(agent["Avaliações"])} avaliações</span></div>'
        '</div></div>'
    )
st.markdown(f'<div class="agent-grid">{"".join(agent_cards)}</div>', unsafe_allow_html=True)

st.markdown('<div class="section-heading"><div class="section-title">Voz do cliente</div><div class="section-caption">Reputação da marca e satisfação com o atendimento.</div></div>', unsafe_allow_html=True)
ra_column, csat_column = st.columns(2, gap="large")
with ra_column:
    st.markdown(
        '<div class="info-card"><div class="card-heading">♥ Reclame Aqui</div>'
        f'<div class="card-caption">Preenchimento manual • referência: {html.escape(NOME_MES_REFERENCIA)}</div>'
        f'<div class="ra-score">{format_decimal(RA_NOTA)}</div><div class="ra-score-label">Nota geral no período</div>'
        '<div class="mini-grid">'
        f'<div class="mini-item"><div class="mini-value">{format_number(RA_RECLAMACOES)}</div><div class="mini-label">Reclamações</div></div>'
        f'<div class="mini-item"><div class="mini-value">{format_decimal(RA_RESPONDIDAS_PCT)}%</div><div class="mini-label">Respondidas</div></div>'
        f'<div class="mini-item"><div class="mini-value">{format_decimal(RA_INDICE_SOLUCAO_PCT)}%</div><div class="mini-label">Índice de solução</div></div>'
        f'<div class="mini-item"><div class="mini-value">{format_decimal(RA_VOLTARIAM_PCT)}%</div><div class="mini-label">Voltariam a comprar</div></div>'
        f'<div class="mini-item"><div class="mini-value">{format_decimal(RA_NOTA_CONSUMIDOR, 2)}</div><div class="mini-label">Nota consumidor</div></div>'
        f'<div class="mini-item"><div class="mini-value" style="font-size:13px">{html.escape(RA_TEMPO_MEDIO_RESPOSTA)}</div><div class="mini-label">Tempo de resposta</div></div>'
        '</div></div>', unsafe_allow_html=True,
    )
    complaints_change = RA_RECLAMACOES - RA_RECLAMACOES_MES_ANTERIOR
    change_word = "mais" if complaints_change >= 0 else "menos"
    st.markdown(f'<div class="insight">• Nota atual: <b>{format_decimal(RA_NOTA)}</b> (anterior: {format_decimal(RA_NOTA_MES_ANTERIOR)}).</div><div class="insight">• <b>{format_number(abs(complaints_change))} {change_word}</b> reclamações que no mês anterior.</div>', unsafe_allow_html=True)
    if selected_period != default_period:
        st.info(f"O Reclame Aqui está preenchido para {NOME_MES_REFERENCIA}; os filtros não alteram esses números.")

with csat_column:
    st.markdown(
        '<div class="info-card"><div class="card-heading">Resultados CSAT</div>'
        '<div class="card-caption">Somente tickets resolvidos no período filtrado.</div>'
        f'<div class="ra-score" style="color:{COLORS["navy"]}">{format_percent(csat_rate)}</div><div class="ra-score-label">Índice de satisfação</div>'
        '<div class="mini-grid">'
        f'<div class="mini-item"><div class="mini-value">{format_percent(survey_response_rate)}</div><div class="mini-label">Taxa de resposta</div></div>'
        f'<div class="mini-item"><div class="mini-value">{format_number(rated_count)}</div><div class="mini-label">Avaliações</div></div>'
        f'<div class="mini-item"><div class="mini-value" style="color:{COLORS["teal"]}">{format_number(good_count)}</div><div class="mini-label">Positivas</div></div>'
        f'<div class="mini-item"><div class="mini-value" style="color:{COLORS["red"]}">{format_number(bad_count)}</div><div class="mini-label">Negativas</div></div>'
        f'<div class="mini-item"><div class="mini-value">{format_number(offered_count)}</div><div class="mini-label">Oferecidas sem resposta</div></div>'
        f'<div class="mini-item"><div class="mini-value">{format_number(surveyed_count)}</div><div class="mini-label">Pesquisas oferecidas</div></div>'
        '</div></div>', unsafe_allow_html=True,
    )
    st.markdown(f'<div class="insight">• <b style="color:{COLORS["teal"]}">{format_number(good_count)} positivas</b> e <b style="color:{COLORS["red"]}">{format_number(bad_count)} negativas</b>.</div><div class="insight">• {format_number(rated_count)} respostas em {format_number(surveyed_count)} pesquisas oferecidas.</div>', unsafe_allow_html=True)

ra_complaints = pd.DataFrame({"Categoria": list(RA_CATEGORIAS_RECLAMACOES), "Quantidade": list(RA_CATEGORIAS_RECLAMACOES.values())}).sort_values("Quantidade")
complaint_figure = px.bar(ra_complaints, x="Quantidade", y="Categoria", orientation="h", text_auto=True, color_discrete_sequence=[COLORS["blue"]])
complaint_figure.update_traces(textposition="outside", cliponaxis=False)
complaint_figure.update_layout(title="Categorias das reclamações", height=330, margin=dict(l=10, r=45, t=52, b=30), xaxis_title="", yaxis_title="")

csat_frame = pd.DataFrame({"Avaliação": ["Positiva", "Negativa"], "Tickets": [good_count, bad_count]})
csat_figure = px.pie(csat_frame, names="Avaliação", values="Tickets", hole=.66, color="Avaliação", color_discrete_map={"Positiva": COLORS["teal"], "Negativa": COLORS["red"]})
csat_figure.update_traces(textposition="outside", textinfo="value+percent", marker=dict(line=dict(color="white", width=3)))
csat_figure.update_layout(title="Composição do CSAT", height=330, margin=dict(l=25, r=25, t=52, b=30), legend=dict(orientation="h", y=-.04, x=.5, xanchor="center", title=""), annotations=[dict(text=f"<b>{format_percent(csat_rate)}</b><br><span style='font-size:11px'>CSAT</span>", x=.5, y=.5, font=dict(size=20, color=COLORS["navy"]), showarrow=False)])

chart_left, chart_right = st.columns(2, gap="large")
with chart_left:
    st.plotly_chart(finish_figure(complaint_figure), width="stretch", theme=None, config={"displayModeBar": False})
with chart_right:
    st.plotly_chart(finish_figure(csat_figure), width="stretch", theme=None, config={"displayModeBar": False})

bad_reasons = (
    solved[solved["Satisfaction Score"].eq("Bad")]["Motivo do Contato [list]"]
    .value_counts().rename_axis("Motivo").reset_index(name="Avaliações ruins").sort_values("Avaliações ruins")
)
chart_left, chart_right = st.columns(2, gap="large")
with chart_left:
    if sum(RA_CATEGORIAS_AVALIACOES.values()) > 0:
        ra_reviews = pd.DataFrame({"Categoria": list(RA_CATEGORIAS_AVALIACOES), "Quantidade": list(RA_CATEGORIAS_AVALIACOES.values())})
        reviews_figure = px.pie(ra_reviews, names="Categoria", values="Quantidade", hole=.62, color="Categoria", color_discrete_map={"Positivas": COLORS["teal"], "Neutras": COLORS["gold"], "Negativas": COLORS["red"]})
        reviews_figure.update_traces(textposition="inside", textinfo="percent", marker=dict(line=dict(color="white", width=3)))
        reviews_figure.update_layout(title="Categorias das avaliações no Reclame Aqui", height=330, margin=dict(l=25, r=25, t=52, b=30), legend=dict(orientation="h", y=-.04, x=.5, xanchor="center", title=""))
        st.plotly_chart(finish_figure(reviews_figure), width="stretch", theme=None, config={"displayModeBar": False})
    else:
        st.info("Preencha `RA_CATEGORIAS_AVALIACOES` no início do código.")
with chart_right:
    if bad_reasons.empty:
        st.success("Nenhuma avaliação ruim no período filtrado.")
    else:
        bad_figure = px.bar(bad_reasons, x="Avaliações ruins", y="Motivo", orientation="h", text_auto=True, color_discrete_sequence=[COLORS["red"]])
        bad_figure.update_traces(textposition="outside", cliponaxis=False)
        bad_figure.update_layout(title="Motivos das avaliações ruins no CSAT", height=330, margin=dict(l=10, r=45, t=52, b=30), xaxis_title="", yaxis_title="")
        st.plotly_chart(finish_figure(bad_figure), width="stretch", theme=None, config={"displayModeBar": False})

st.markdown('<div class="section-heading"><div class="section-title">Tickets resolvidos por motivo</div><div class="section-caption">Principais motivos no período, excluindo Uso Interno.</div></div>', unsafe_allow_html=True)
external_solved = solved[~solved["Motivo do Contato [list]"].str.contains("uso interno", case=False, na=False)]
reason_counts = external_solved["Motivo do Contato [list]"].value_counts().rename_axis("Motivo").reset_index(name="Tickets").head(12).sort_values("Tickets")
reason_figure = px.bar(reason_counts, x="Tickets", y="Motivo", orientation="h", text_auto=True, color="Tickets", color_continuous_scale=[[0, "#CFE2F5"], [1, COLORS["navy"]]])
reason_figure.update_traces(textposition="outside", cliponaxis=False)
reason_figure.update_layout(height=430, margin=dict(l=10, r=55, t=15, b=35), xaxis_title="Tickets resolvidos", yaxis_title="", coloraxis_showscale=False, paper_bgcolor="white", plot_bgcolor="white")
st.plotly_chart(finish_figure(reason_figure), width="stretch", theme=None, config={"displayModeBar": False})

st.markdown(f'<div class="source-note">Fonte: {html.escape(source_name)} • atualização no GitHub: {html.escape(updated_text)} • {format_number(len(solved))} tickets resolvidos após os filtros</div>', unsafe_allow_html=True)
