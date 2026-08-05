from __future__ import annotations

from io import BytesIO
from pathlib import Path
import html

import pandas as pd
import plotly.express as px
import streamlit as st


st.set_page_config(
    page_title="Fechamento do SAC",
    page_icon="🎧",
    layout="wide",
    initial_sidebar_state="collapsed",
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
RA_NOTA = 8.7
RA_NOTA_MES_ANTERIOR = 8.5
RA_RECLAMACOES = 14
RA_RECLAMACOES_MES_ANTERIOR = 7
RA_RESPONDIDAS_PCT = 100.0
RA_VOLTARIAM_PCT = 77.8
RA_INDICE_SOLUCAO_PCT = 91.1
RA_NOTA_CONSUMIDOR = 7.22
RA_TEMPO_MEDIO_RESPOSTA = "8 dias e 21 horas"

# Quantidade de reclamações por motivo.
RA_MOTIVOS = {
    "Problemas de qualidade": 7,
    "Questões logísticas": 6,
    "Experiência de compra e atendimento": 1,
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


def filter_reference_month(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    start = pd.Timestamp(ANO_REFERENCIA, MES_REFERENCIA, 1)
    end = start + pd.offsets.MonthBegin(1)
    created = frame[frame["Created at"].ge(start) & frame["Created at"].lt(end)].copy()
    solved = frame[frame["Solved at"].ge(start) & frame["Solved at"].lt(end)].copy()
    return created, solved


def metric_card(label: str, value: str, detail: str, tone: str = "blue") -> str:
    safe_label = html.escape(label)
    safe_value = html.escape(value)
    safe_detail = html.escape(detail)
    return f"""
      <div class="metric-card metric-{tone}">
        <div class="metric-label">{safe_label}</div>
        <div class="metric-value">{safe_value}</div>
        <div class="metric-detail">{safe_detail}</div>
      </div>
    """


def performance_row(label: str, target: float, actual: float) -> str:
    delta = actual - target
    variation = delta / target if target else 0
    achieved = actual <= target
    status_class = "good" if achieved else "bad"
    status_text = "Dentro da meta" if achieved else "Acima da meta"
    sign = "+" if delta > 0 else ""
    return f"""
      <div class="performance-row">
        <div class="performance-name">{html.escape(label)}</div>
        <div><span class="cell-label">Objetivo</span><strong>{format_decimal(target)} h</strong></div>
        <div><span class="cell-label">Realizado</span><strong>{format_decimal(actual)} h</strong></div>
        <div><span class="cell-label">Diferença</span><strong>{sign}{format_decimal(delta)} h</strong></div>
        <div><span class="cell-label">Variação</span><strong>{sign}{format_percent(variation)}</strong></div>
        <div><span class="status-pill {status_class}">{status_text}</span></div>
      </div>
    """


def source_from_repository_or_upload() -> tuple[str | bytes | None, str, float | int]:
    repository_zip = find_zip()
    if repository_zip:
        return str(repository_zip), repository_zip.name, repository_zip.stat().st_mtime

    uploaded = st.file_uploader(
        "A ZIP ainda não está no repositório. Selecione-a para testar:",
        type=["zip"],
        accept_multiple_files=False,
    )
    if uploaded:
        payload = uploaded.getvalue()
        return payload, uploaded.name, len(payload)
    return None, "", 0


st.markdown(
    """
    <style>
      :root {
        --navy: #173B5E;
        --blue: #4F91CF;
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

      @media (max-width: 900px) {
        .metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        .performance-row { grid-template-columns: 1fr 1fr; gap: 12px; }
        .performance-name, .performance-row > div:last-child { grid-column: 1 / -1; }
      }
      @media (max-width: 560px) {
        .block-container { padding-left: .8rem; padding-right: .8rem; }
        .hero { padding: 23px 20px; border-radius: 18px; }
        .metric-grid { grid-template-columns: 1fr; }
        .mini-grid { grid-template-columns: 1fr; }
      }
    </style>
    """,
    unsafe_allow_html=True,
)


source, source_name, source_signature = source_from_repository_or_upload()
if source is None:
    st.info("Envie para o GitHub um arquivo com nome `export-*.csv.zip`. O dashboard fará a leitura automaticamente.")
    st.stop()

try:
    raw = read_zip(source, source_signature)
    created, solved = filter_reference_month(raw)
except Exception as error:
    st.error("Não foi possível ler a ZIP do Zendesk.")
    st.exception(error)
    st.stop()

if created.empty and solved.empty:
    st.error(
        f"A ZIP não possui tickets em {NOME_MES_REFERENCIA}. "
        "Atualize ANO_REFERENCIA e MES_REFERENCIA no bloco manual do início do código."
    )
    st.stop()


# Indicadores calculados exclusivamente a partir da ZIP.
response_hours = solved["First reply time in minutes"].median() / 60
resolution_hours = solved["Full resolution time in minutes"].median() / 60

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
    f"""
    <div class="hero">
      <div class="hero-eyebrow">GESTÃO DE ATENDIMENTO</div>
      <h1>Fechamento do SAC • {html.escape(NOME_MES_REFERENCIA)}</h1>
      <p>Tempo de atendimento, satisfação do cliente e reputação da marca em uma leitura executiva.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

cards = "".join(
    [
        metric_card(
            "Tempo de resposta",
            f"{format_decimal(response_hours)} h",
            f"Meta: {format_decimal(META_TEMPO_RESPOSTA_H)} h • {response_status}",
            "teal" if response_hours <= META_TEMPO_RESPOSTA_H else "red",
        ),
        metric_card(
            "Tempo de resolução",
            f"{format_decimal(resolution_hours)} h",
            f"Meta: {format_decimal(META_TEMPO_RESOLUCAO_H)} h • {resolution_status}",
            "teal" if resolution_hours <= META_TEMPO_RESOLUCAO_H else "red",
        ),
        metric_card(
            "CSAT",
            format_percent(csat_rate),
            f"{format_number(rated_count)} avaliações respondidas",
            "blue",
        ),
        metric_card(
            "Tickets resolvidos",
            format_number(len(solved)),
            f"{format_number(len(created))} criados no mês",
            "gold",
        ),
    ]
)
st.markdown(f'<div class="metric-grid">{cards}</div>', unsafe_allow_html=True)


st.markdown(
    '<div class="section-heading"><div class="section-title">Meta x realizado</div>'
    '<div class="section-caption">Comparação direta dos dois indicadores de velocidade. Quanto menor, melhor.</div></div>',
    unsafe_allow_html=True,
)
performance_html = (
    performance_row("Tempo de resposta", META_TEMPO_RESPOSTA_H, response_hours)
    + performance_row("Tempo de resolução", META_TEMPO_RESOLUCAO_H, resolution_hours)
)
st.markdown(f'<div class="performance-table">{performance_html}</div>', unsafe_allow_html=True)


ra_column, csat_column = st.columns(2, gap="large")

with ra_column:
    st.markdown(
        '<div class="info-card"><div class="card-heading">♥ Reclame Aqui</div>'
        '<div class="card-caption">Indicadores atualizados manualmente no início do código.</div>'
        f'<div class="ra-score">{format_decimal(RA_NOTA)}</div>'
        '<div class="ra-score-label">Nota geral no período</div>'
        '<div class="mini-grid">'
        f'<div class="mini-item"><div class="mini-value">{format_number(RA_RECLAMACOES)}</div><div class="mini-label">Reclamações</div></div>'
        f'<div class="mini-item"><div class="mini-value">{format_decimal(RA_RESPONDIDAS_PCT)}%</div><div class="mini-label">Respondidas</div></div>'
        f'<div class="mini-item"><div class="mini-value">{format_decimal(RA_INDICE_SOLUCAO_PCT)}%</div><div class="mini-label">Índice de solução</div></div>'
        f'<div class="mini-item"><div class="mini-value">{format_decimal(RA_VOLTARIAM_PCT)}%</div><div class="mini-label">Voltariam a comprar</div></div>'
        f'<div class="mini-item"><div class="mini-value">{format_decimal(RA_NOTA_CONSUMIDOR, 2)}</div><div class="mini-label">Nota consumidor</div></div>'
        f'<div class="mini-item"><div class="mini-value" style="font-size:13px">{html.escape(RA_TEMPO_MEDIO_RESPOSTA)}</div><div class="mini-label">Tempo de resposta</div></div>'
        '</div></div>',
        unsafe_allow_html=True,
    )

    if RA_NOTA > RA_NOTA_MES_ANTERIOR:
        st.markdown(
            f'<div class="insight">↗ A nota aumentou de <b>{format_decimal(RA_NOTA_MES_ANTERIOR)}</b> para <b>{format_decimal(RA_NOTA)}</b>.</div>',
            unsafe_allow_html=True,
        )
    elif RA_NOTA < RA_NOTA_MES_ANTERIOR:
        st.markdown(
            f'<div class="insight">↘ A nota passou de <b>{format_decimal(RA_NOTA_MES_ANTERIOR)}</b> para <b>{format_decimal(RA_NOTA)}</b>.</div>',
            unsafe_allow_html=True,
        )

    complaints_change = RA_RECLAMACOES - RA_RECLAMACOES_MES_ANTERIOR
    change_word = "mais" if complaints_change >= 0 else "menos"
    st.markdown(
        f'<div class="insight">• Recebemos <b>{format_number(RA_RECLAMACOES)}</b> reclamações, '
        f'<b>{format_number(abs(complaints_change))} {change_word}</b> que no mês anterior.</div>',
        unsafe_allow_html=True,
    )

    ra_reasons = (
        pd.DataFrame({"Motivo": list(RA_MOTIVOS), "Reclamações": list(RA_MOTIVOS.values())})
        .sort_values("Reclamações")
    )
    ra_figure = px.bar(
        ra_reasons,
        x="Reclamações",
        y="Motivo",
        orientation="h",
        text_auto=True,
        color_discrete_sequence=[COLORS["blue"]],
    )
    ra_figure.update_traces(marker_line_width=0, textposition="outside", cliponaxis=False)
    ra_figure.update_layout(
        title=dict(text="Reclamações por motivo", font=dict(size=15, color=COLORS["navy"])),
        height=285,
        margin=dict(l=10, r=45, t=48, b=30),
        xaxis=dict(title="", showgrid=False, zeroline=False),
        yaxis=dict(title="", tickfont=dict(size=12)),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
    )
    st.plotly_chart(ra_figure, width="stretch", config={"displayModeBar": False})


with csat_column:
    st.markdown(
        '<div class="info-card"><div class="card-heading">Resultados CSAT</div>'
        '<div class="card-caption">Calculado diretamente a partir das avaliações da ZIP do Zendesk.</div>'
        '<div class="mini-grid">'
        f'<div class="mini-item"><div class="mini-value">{format_percent(csat_rate)}</div><div class="mini-label">Índice de satisfação</div></div>'
        f'<div class="mini-item"><div class="mini-value">{format_percent(survey_response_rate)}</div><div class="mini-label">Taxa de resposta</div></div>'
        f'<div class="mini-item"><div class="mini-value">{format_number(rated_count)}</div><div class="mini-label">Avaliações</div></div>'
        '</div></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="insight">• Recebemos <b style="color:#16886A">{format_number(good_count)} avaliações positivas</b> '
        f'e <b style="color:#C83C4D">{format_number(bad_count)} negativas</b>.</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="insight">• Das <b>{format_number(surveyed_count)}</b> pesquisas oferecidas, '
        f'<b>{format_number(rated_count)}</b> foram respondidas.</div>',
        unsafe_allow_html=True,
    )

    csat_frame = pd.DataFrame(
        {"Avaliação": ["Positiva", "Negativa"], "Tickets": [good_count, bad_count]}
    )
    csat_figure = px.pie(
        csat_frame,
        names="Avaliação",
        values="Tickets",
        hole=.66,
        color="Avaliação",
        color_discrete_map={"Positiva": COLORS["teal"], "Negativa": COLORS["red"]},
    )
    csat_figure.update_traces(
        textposition="outside",
        textinfo="value+percent",
        marker=dict(line=dict(color="white", width=3)),
        pull=[0, .025],
    )
    csat_figure.update_layout(
        title=dict(text="Composição das avaliações", font=dict(size=15, color=COLORS["navy"])),
        height=365,
        margin=dict(l=25, r=25, t=48, b=25),
        legend=dict(orientation="h", y=-.02, x=.5, xanchor="center", title=""),
        paper_bgcolor="rgba(0,0,0,0)",
        annotations=[
            dict(
                text=f"<b>{format_percent(csat_rate)}</b><br><span style='font-size:11px'>CSAT</span>",
                x=.5,
                y=.5,
                font=dict(size=20, color=COLORS["navy"]),
                showarrow=False,
            )
        ],
    )
    st.plotly_chart(csat_figure, width="stretch", config={"displayModeBar": False})


st.markdown(
    '<div class="section-heading"><div class="section-title">O que mais gerou contato</div>'
    '<div class="section-caption">Principais motivos registrados nos tickets criados no mês.</div></div>',
    unsafe_allow_html=True,
)

reason_counts = (
    created["Motivo do Contato [list]"]
    .value_counts()
    .rename_axis("Motivo")
    .reset_index(name="Tickets")
    .head(10)
    .sort_values("Tickets")
)
reason_figure = px.bar(
    reason_counts,
    x="Tickets",
    y="Motivo",
    orientation="h",
    text_auto=True,
    color="Tickets",
    color_continuous_scale=[[0, "#CFE2F5"], [1, COLORS["navy"]]],
)
reason_figure.update_traces(textposition="outside", cliponaxis=False)
reason_figure.update_layout(
    height=390,
    margin=dict(l=10, r=55, t=15, b=35),
    xaxis=dict(title="Tickets", showgrid=False, zeroline=False),
    yaxis=dict(title="", tickfont=dict(size=12)),
    coloraxis_showscale=False,
    paper_bgcolor="white",
    plot_bgcolor="white",
)
st.plotly_chart(reason_figure, width="stretch", config={"displayModeBar": False})

st.markdown(
    f'<div class="source-note">Fonte automática: {html.escape(source_name)} • '
    f'{format_number(len(raw))} tickets no arquivo • indicadores filtrados para {html.escape(NOME_MES_REFERENCIA)}</div>',
    unsafe_allow_html=True,
)
