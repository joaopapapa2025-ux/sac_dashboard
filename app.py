from __future__ import annotations

from io import BytesIO
from pathlib import Path
from datetime import datetime, timezone
import html
import subprocess

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st


st.set_page_config(
    page_title="Dashboard SAC",
    page_icon="🎧",
    layout="wide",
    initial_sidebar_state="expanded",
)

BASE_DIR = Path(__file__).resolve().parent


# =============================================================================
# ✏️ ATUALIZAÇÃO MANUAL — ALTERE SOMENTE ESTE BLOCO A CADA FECHAMENTO
# =============================================================================

ANO_REFERENCIA = 2026
MES_REFERENCIA = 8
NOME_MES_REFERENCIA = "Agosto de 2026"
 
# Metas do SAC em horas. Quanto menor o resultado, melhor.
META_TEMPO_RESPOSTA_H = 28.0
META_TEMPO_RESOLUCAO_H = 55.0
 
# Reclame Aqui
RA_NOTA = 8.7
RA_NOTA_MES_ANTERIOR = 8.8
RA_RECLAMACOES = 9
RA_RECLAMACOES_MES_ANTERIOR = 19
RA_RESPONDIDAS_PCT = 95.3
RA_VOLTARIAM_PCT = 81.6
RA_INDICE_SOLUCAO_PCT = 91.8
RA_NOTA_CONSUMIDOR = 8.08
RA_TEMPO_MEDIO_RESPOSTA = "7 dias e 12 horas"
 
# Categorias das reclamações no Reclame Aqui.
RA_CATEGORIAS_RECLAMACOES = {
    "Problemas de qualidade": 4,
    "Questões logísticas": 3,
    "Experiência de compra e atendimento": 2,
}
 
# Categorias das avaliações no Reclame Aqui. Preencha as quantidades manualmente.
# Se todas estiverem zeradas, o dashboard mostrará um aviso no lugar do gráfico.
RA_CATEGORIAS_AVALIACOES = {
    "Positivas": 2,
    "Neutras": 0,
    "Negativas": 1,
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
    "Tags",
    "Status",
    "Via",
    "Created at",
    "Initially assigned at",
    "Solved at",
    "Replies",
    "Satisfaction Score",
    "Full resolution time in minutes",
    "Full resolution time in minutes within business hours",
    "Motivo do Contato [list]",
}

# Mesmas exceções selecionadas manualmente no filtro da antiga planilha.
# Elas ficam explícitas aqui para que o dashboard seja reproduzível e auditável.
TAGS_EXCLUIDAS_PLANILHA = {
    "06042026_expirado informação_pedido system_email_notification_failure",
    "06042026_expirado interação system_email_notification_failure",
    "06042026_expirado sem_resposta",
    "06042026_expirado system_email_notification_failure",
    "180626_reenvio cancelamento_pedido",
    "180626_reenvio informação_pedido",
    "180626_reenvio reclamação_sobre_pedido",
    "20251222_expirados alteração_sensorial qualidade",
    "20251229_expirados closed_by_merge reclamação_sobre_pedido",
    "20260413_expirados cancelamento_assinatura",
    "20260413_expirados problema_com_o_cadastro",
    "20260415_ra avaria reclame_aqui",
    "20260415_ra closed_by_merge",
    "20260415_ra informação_pedido",
    "20260415_ra informações_sobre_produtos",
    "20260420_expirado devolução_de_produtos",
    "20260423_expirado cancelamento_assinatura",
    "20260423_expirado closed_by_merge",
    "20260423_expirado informação_pedido",
    "20260423_expirado interação",
    "20260423_expirado sem_resposta",
    "20260428_expirado canal_especial informação_pedido",
    "20260512_expirado closed_by_merge informação_pedido",
    "20260626_expirados closed_by_merge",
    "20260706_expirado onde_encontrar",
    "20260722_expirado informação_pedido",
    "22062026 sem_resposta",
    "22062026_reativação cancelamento_assinatura",
    "22062026_reativação informação_pedido",
    "24042026 cancelamento_assinatura",
    "27042026 cupom_de_desconto",
    "alteração qualidade sensorial",
    "alteração_assinatura informações_sobre_produtos",
    "alteração_sensorial closed_by_merge qualidade",
    "alteração_sensorial closed_by_merge qualidade system_email_notification_failure",
    "alteração_sensorial devolução_de_produtos",
    "alteração_sensorial feedback",
    "alteração_sensorial qualidade",
    "alteração_sensorial qualidade system_email_notification_failure",
    "alteração_sensorial reclame_aqui",
    "alteração_sensorial reclame_aqui system_email_notification_failure",
    "avaria reclame_aqui",
    "cadastro_",
    "canal_de_atendimento_para_nutricionistas",
    "canal_especial qualidade",
    "cancelamento_assinatura closed_by_merge",
    "cancelamento_pedido closed_by_merge",
    "cancelamento_pedido reclamacao_pedidos_ecom",
    "closed_by_merge dúvida_sobre_visitação",
    "closed_by_merge dúvidas_no_processo_de_compra",
    "closed_by_merge marketing_de_influência",
    "closed_by_merge uso_interno",
    "duvida_acao_promocional reclamação_sobre_pedido",
    "elogio feedback",
    "feedback returning_visitor",
}

# Mesma agenda de feriados usada pelo cálculo First Reply BH da planilha.
FERIADOS_SAC = np.array(
    [
        "2025-01-01", "2025-02-24", "2025-02-25", "2025-04-21",
        "2025-05-01", "2025-06-19", "2025-09-07", "2025-09-08",
        "2025-10-12", "2025-11-02", "2025-11-15", "2025-11-20",
        "2025-12-25", "2026-01-01", "2026-02-16", "2026-02-17",
        "2026-04-03", "2026-04-21", "2026-05-01", "2026-06-04",
        "2026-09-07", "2026-09-08", "2026-10-12", "2026-11-02",
        "2026-11-15", "2026-11-20", "2026-12-25",
    ],
    dtype="datetime64[D]",
)

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


def first_assignment_business_hours(created_at: pd.Timestamp, assigned_at: pd.Timestamp) -> float:
    """Replica First Reply BH: criação até primeira atribuição, de 9h às 18h."""
    if pd.isna(created_at) or pd.isna(assigned_at):
        return float("nan")

    start = pd.Timestamp(created_at)
    end = pd.Timestamp(assigned_at)
    direction = 1
    if end < start:
        start, end = end, start
        direction = -1

    start_day = np.datetime64(start.date(), "D")
    end_day = np.datetime64(end.date(), "D")
    business_days = np.busday_count(
        start_day,
        end_day + np.timedelta64(1, "D"),
        weekmask="1111100",
        holidays=FERIADOS_SAC,
    )
    start_hour = (start - start.normalize()).total_seconds() / 3600
    end_hour = (end - end.normalize()).total_seconds() / 3600
    elapsed = (
        (business_days - 2) * 9
        + (18 - max(start_hour, 9))
        + (min(end_hour, 18) - 9)
    )
    return round(direction * elapsed, 1)


def first_assignment_weekday_hours(created_at: pd.Timestamp, assigned_at: pd.Timestamp) -> float:
    """Replica First Reply H, preservando o comparativo e a mediana usados antes."""
    if pd.isna(created_at) or pd.isna(assigned_at):
        return float("nan")

    start = pd.Timestamp(created_at)
    end = pd.Timestamp(assigned_at)
    direction = 1
    if end < start:
        start, end = end, start
        direction = -1

    start_day = np.datetime64(start.date(), "D")
    end_day = np.datetime64(end.date(), "D")
    business_days = np.busday_count(
        start_day,
        end_day + np.timedelta64(1, "D"),
        weekmask="1111100",
        holidays=FERIADOS_SAC,
    )
    start_hour = (start - start.normalize()).total_seconds() / 3600
    end_hour = (end - end.normalize()).total_seconds() / 3600
    elapsed = (business_days - 1) * 24 + end_hour - start_hour
    return round(direction * elapsed, 1)


@st.cache_data(show_spinner="Lendo a base detalhada do Zendesk...")
def read_zip(source: str | bytes, signature: float | int) -> pd.DataFrame:
    del signature
    target = BytesIO(source) if isinstance(source, bytes) else source
    frame = pd.read_csv(target, compression="zip", dtype=str, low_memory=False)

    missing = REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError("A base não contém as colunas esperadas: " + ", ".join(sorted(missing)))

    frame = frame[list(REQUIRED_COLUMNS)].copy()
    original_rows = len(frame)
    has_id = frame["Id"].fillna("").str.strip().ne("")
    frame_with_id = frame[has_id].drop_duplicates(subset=["Id"], keep="last")
    frame = pd.concat([frame_with_id, frame[~has_id]], ignore_index=True)
    frame.attrs["duplicates_removed"] = original_rows - len(frame)

    frame["Created at"] = pd.to_datetime(frame["Created at"], errors="coerce")
    frame["Initially assigned at"] = pd.to_datetime(
        frame["Initially assigned at"], errors="coerce"
    )
    frame["Solved at"] = pd.to_datetime(frame["Solved at"], errors="coerce")
    frame["Replies"] = pd.to_numeric(frame["Replies"], errors="coerce").fillna(0)
    numeric_time_columns = [
        "Full resolution time in minutes",
        "Full resolution time in minutes within business hours",
    ]
    for column in numeric_time_columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    # Horas corridas: diferença real entre criação e solução, sem calendário comercial.
    frame["Resolution elapsed hours"] = (
        frame["Solved at"] - frame["Created at"]
    ).dt.total_seconds() / 3600
    frame["Resolution calendar hours"] = (
        frame["Full resolution time in minutes"] / 60
    ).round(1)
    frame["Resolution business hours"] = (
        frame["Full resolution time in minutes within business hours"] / 60
    )
    frame["Response weekday hours"] = [
        first_assignment_weekday_hours(created_at, assigned_at)
        for created_at, assigned_at in zip(
            frame["Created at"], frame["Initially assigned at"]
        )
    ]
    frame["Response business hours"] = [
        first_assignment_business_hours(created_at, assigned_at)
        for created_at, assigned_at in zip(
            frame["Created at"], frame["Initially assigned at"]
        )
    ]
    frame["Reason key"] = frame["Motivo do Contato [list]"].fillna("").str.strip()
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
    solved = frame[
        frame["Solved at"].notna()
        & frame["Status"].fillna("").str.casefold().isin({"solved", "closed"})
    ].copy()
    # A planilha antiga usava Has Merged = No. A tag identifica esses registros.
    merged = solved["Tags"].fillna("").str.contains(
        r"(?:^|\s)closed_by_merge(?:\s|$)", case=False, regex=True
    )
    return solved[~merged].copy()


def resolution_scope(frame: pd.DataFrame) -> pd.DataFrame:
    """Amostra do KPI de resolução conforme o antigo Tickets_Resolvidos."""
    excluded_reasons = {"encerramento", "sem resposta", "uso interno"}
    reason = frame["Reason key"].str.casefold()
    allowed_reason = reason.ne("") & ~reason.isin(excluded_reasons)
    allowed_tag = ~frame["Tags"].fillna("").isin(TAGS_EXCLUIDAS_PLANILHA)
    return frame[
        allowed_reason
        & allowed_tag
        & frame["Resolution calendar hours"].notna()
    ].copy()


def response_scope(frame: pd.DataFrame) -> pd.DataFrame:
    """Amostra do KPI de resposta conforme o antigo Tickets_Respostas."""
    reason = frame["Reason key"].str.casefold()
    return frame[
        reason.ne("")
        & reason.ne("uso interno")
        & frame["Replies"].gt(0)
        & frame["Response business hours"].notna()
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
    if pd.isna(actual):
        return (
            '<div class="performance-row">'
            f'<div class="performance-name">{html.escape(label)}</div>'
            f'<div><span class="cell-label">Objetivo</span><strong>{format_decimal(target)} h</strong></div>'
            '<div><span class="cell-label">Realizado</span><strong>—</strong></div>'
            '<div><span class="cell-label">Diferença</span><strong>—</strong></div>'
            '<div><span class="cell-label">Variação</span><strong>—</strong></div>'
            '<div><span class="status-pill neutral">Sem dados</span></div>'
            '</div>'
        )
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


def monthly_values(frame: pd.DataFrame, periods: list[pd.Period]) -> tuple[list[float], list[float]]:
    resolution_values: list[float] = []
    response_values: list[float] = []
    for period in periods:
        month_data = frame[frame["Solved at"].dt.to_period("M").eq(period)]
        month_resolution = resolution_scope(month_data)
        month_response = response_scope(month_data)
        resolution_values.append(month_resolution["Resolution calendar hours"].mean())
        response_values.append(month_response["Response business hours"].mean())
    return resolution_values, response_values


def monthly_table_section(label: str, target: float, actuals: list[float]) -> str:
    def value_cells(values: list[float], formatter, css_class: str = "") -> str:
        cells = []
        for value in values:
            shown = "—" if pd.isna(value) else formatter(value)
            cells.append(f'<td class="{css_class}">{shown}</td>')
        return "".join(cells)

    deltas = [value - target if pd.notna(value) else float("nan") for value in actuals]
    target_variations = [value / target - 1 if pd.notna(value) and target else float("nan") for value in actuals]
    month_variations = [float("nan")]
    for previous, current in zip(actuals, actuals[1:]):
        month_variations.append(
            current / previous - 1
            if pd.notna(previous) and pd.notna(current) and previous
            else float("nan")
        )

    target_values = [target] * len(actuals)
    delta_cells = []
    for value in deltas:
        if pd.isna(value):
            delta_cells.append('<td class="delta-neutral">—</td>')
        else:
            css_class = "delta-bad" if value > 0 else "delta-good"
            sign = "+" if value > 0 else ""
            delta_cells.append(
                f'<td class="{css_class}">{sign}{format_decimal(value)}</td>'
            )

    return (
        f'<tr class="kpi-objective"><th>(O) {html.escape(label)}</th>'
        f'{value_cells(target_values, lambda value: format_decimal(value))}</tr>'
        f'<tr class="kpi-actual"><th>(R) {html.escape(label)}</th>'
        f'{value_cells(actuals, lambda value: format_decimal(value))}</tr>'
        '<tr class="kpi-support"><th>MoM</th>'
        f'{value_cells(month_variations, lambda value: ("+" if value > 0 else "") + format_percent(value))}</tr>'
        '<tr class="kpi-delta"><th>Δ (O) (R)</th>'
        f'{"".join(delta_cells)}</tr>'
        '<tr class="kpi-support"><th>% (O) / (R)</th>'
        f'{value_cells(target_variations, lambda value: ("+" if value > 0 else "") + format_percent(value))}</tr>'
    )


def monthly_table(frame: pd.DataFrame, periods: list[pd.Period]) -> str:
    resolution_values, response_values = monthly_values(frame, periods)
    year_label = str(periods[0].year) if len({period.year for period in periods}) == 1 else "Período"
    header = "".join(
        f"<th>{html.escape(MONTH_NAMES[period.month].lower())}<span>{period.year}</span></th>"
        for period in periods
    )
    body = (
        monthly_table_section("Tempo de Resolução · horas corridas", META_TEMPO_RESOLUCAO_H, resolution_values)
        + '<tr class="kpi-spacer"><td colspan="99"></td></tr>'
        + monthly_table_section("Tempo de Resposta · horas úteis", META_TEMPO_RESPOSTA_H, response_values)
    )
    return (
        '<div class="monthly-table-wrap"><table class="monthly-table">'
        f'<thead><tr><th>{year_label}</th>{header}</tr>'
        f'<tr class="monthly-band"><th colspan="{len(periods) + 1}">SAC</th></tr></thead>'
        f'<tbody>{body}</tbody></table></div>'
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
      .status-pill.neutral { color: #52606D; background: #EEF2F6; }

      .monthly-table-wrap {
        overflow-x: auto; background: white; border: 1px solid var(--line);
        border-radius: 18px; box-shadow: 0 8px 26px rgba(23, 59, 94, .05);
        margin-bottom: 14px;
      }
      .monthly-table { width: 100%; min-width: 860px; border-collapse: collapse; color: var(--text); }
      .monthly-table th, .monthly-table td { padding: 8px 13px; text-align: right; white-space: nowrap; }
      .monthly-table th:first-child, .monthly-table td:first-child { text-align: left; min-width: 215px; }
      .monthly-table thead tr:first-child { background: var(--navy); color: white; }
      .monthly-table thead tr:first-child th { font-size: 13px; font-weight: 750; }
      .monthly-table thead span { display: block; font-size: 9px; opacity: .65; font-weight: 500; }
      .monthly-band th { background: var(--blue); color: white; padding-top: 6px; padding-bottom: 6px; }
      .monthly-table tbody th { font-size: 13px; font-weight: 720; color: var(--navy); }
      .monthly-table tbody td { font-size: 13px; }
      .monthly-table .kpi-actual { background: #EAF2FA; font-weight: 760; }
      .monthly-table .kpi-objective { border-top: 1px dashed #9AA8B5; }
      .monthly-table .kpi-support th, .monthly-table .kpi-support td { color: var(--muted); font-size: 12px; font-style: italic; }
      .monthly-table .kpi-delta { font-weight: 760; }
      .monthly-table .delta-good { color: var(--teal); }
      .monthly-table .delta-bad { color: var(--red); }
      .monthly-table .delta-neutral { color: var(--muted); }
      .monthly-table .kpi-spacer td { height: 9px; padding: 0; }

      .comparison-strip {
        display: grid; grid-template-columns: auto 1fr 1fr; align-items: center; gap: 16px;
        background: rgba(255,255,255,.72); border: 1px solid var(--line); border-radius: 14px;
        padding: 12px 16px; margin: 0 0 28px;
      }
      .comparison-intro strong { display: block; color: var(--navy); font-size: 13px; }
      .comparison-intro span { color: var(--muted); font-size: 10px; }
      .comparison-item { border-left: 1px solid var(--line); padding-left: 16px; }
      .comparison-item span { display: block; color: var(--muted); font-size: 10px; }
      .comparison-item strong { color: var(--navy); font-size: 17px; }

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
        .comparison-strip { grid-template-columns: 1fr 1fr; }
        .comparison-intro { grid-column: 1 / -1; }
        .comparison-item:first-of-type { border-left: 0; padding-left: 0; }
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
    duplicates_removed = int(raw.attrs.get("duplicates_removed", 0))
    solved_all = resolved_tickets(raw)
except Exception as error:
    st.error("Não foi possível ler a ZIP do Zendesk.")
    st.exception(error)
    st.stop()

if solved_all.empty:
    st.error("A ZIP não possui tickets resolvidos.")
    st.stop()

solved_all["Assignee"] = solved_all["Assignee"].fillna("Não atribuído").replace("", "Não atribuído")
MONTH_NAMES = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio", 6: "Junho",
    7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro",
}
month_counts = (
    resolution_scope(solved_all)["Solved at"].dropna().dt.to_period("M").value_counts()
)
# Descarta meses residuais de tickets históricos. Mantém meses com ao menos 5%
# do volume do principal mês (e no mínimo 5 tickets).
relevant_month_minimum = max(5, int(month_counts.max() * .05))
relevant_month_counts = month_counts[month_counts.ge(relevant_month_minimum)]
available_months = sorted(relevant_month_counts.index.tolist(), reverse=True)
reference_period = pd.Period(year=ANO_REFERENCIA, month=MES_REFERENCIA, freq="M")
if reference_period in month_counts.index and reference_period not in available_months:
    available_months.append(reference_period)
    available_months.sort(reverse=True)
current_period = pd.Period(
    pd.Timestamp.now(tz="America/Sao_Paulo").strftime("%Y-%m"), freq="M"
)
# Abre no mês atual quando ele existe na base; caso contrário, usa o mês
# mais recente disponível na exportação.
default_period = current_period if current_period in available_months else available_months[0]
default_index = available_months.index(default_period)

st.sidebar.header("Filtros")
period_mode = st.sidebar.radio(
    "Período de resolução",
    ["Mês", "Ano inteiro", "Período personalizado"],
    horizontal=False,
)

base_first_day = solved_all["Solved at"].min().date()
base_last_day = solved_all["Solved at"].max().date()
selectable_last_day = max(base_last_day, pd.Timestamp.now().date())
selected_period = None

if period_mode == "Mês":
    selected_period = st.sidebar.selectbox(
        "Mês",
        available_months,
        index=default_index,
        format_func=lambda value: f'{value.strftime("%m/%Y")} · {format_number(int(month_counts.get(value, 0)))} resolvidos',
    )
    selected_start = selected_period.start_time.date()
    selected_end = selected_period.end_time.date()
    period_name = f"{MONTH_NAMES[selected_period.month]} de {selected_period.year}"

elif period_mode == "Ano inteiro":
    available_years = sorted(solved_all["Solved at"].dropna().dt.year.unique().tolist(), reverse=True)
    default_year_index = available_years.index(ANO_REFERENCIA) if ANO_REFERENCIA in available_years else 0
    selected_year = st.sidebar.selectbox("Ano", available_years, index=default_year_index)
    selected_start = pd.Timestamp(selected_year, 1, 1).date()
    selected_end = pd.Timestamp(selected_year, 12, 31).date()
    period_name = f"Ano de {selected_year}"

else:
    default_custom_start = max(default_period.start_time.date(), base_first_day)
    default_custom_end = min(default_period.end_time.date(), base_last_day)
    selected_dates = st.sidebar.date_input(
        "Intervalo personalizado",
        value=(default_custom_start, default_custom_end),
        min_value=base_first_day,
        max_value=selectable_last_day,
        format="DD/MM/YYYY",
    )
    if isinstance(selected_dates, tuple) and len(selected_dates) == 2:
        selected_start, selected_end = selected_dates
    else:
        st.sidebar.info("Selecione também a data final do período.")
        st.stop()
    period_name = f"{selected_start.strftime('%d/%m/%Y')} a {selected_end.strftime('%d/%m/%Y')}"

start_datetime = pd.Timestamp(selected_start)
end_datetime = pd.Timestamp(selected_end) + pd.Timedelta(days=1)
period_solved = solved_all[
    solved_all["Solved at"].ge(start_datetime) & solved_all["Solved at"].lt(end_datetime)
].copy()

agent_options = sorted(period_solved["Assignee"].dropna().unique().tolist())
selected_agents = st.sidebar.multiselect("Agentes", agent_options, placeholder="Todos os agentes")

solved = period_solved.copy()
if selected_agents:
    solved = solved[solved["Assignee"].isin(selected_agents)].copy()

if solved.empty:
    st.warning("Nenhum ticket resolvido corresponde aos filtros selecionados.")
    st.stop()

# Cada KPI usa exatamente a amostra equivalente ao respectivo pivô antigo.
resolution_solved = resolution_scope(solved)
response_solved = response_scope(solved)
if resolution_solved.empty:
    st.warning("Não há tickets elegíveis para o cálculo de resolução neste período.")
    st.stop()

if source_updated_at:
    updated_stamp = pd.Timestamp(source_updated_at)
    if updated_stamp.tzinfo is None:
        updated_stamp = updated_stamp.tz_localize("UTC")
    updated_stamp = updated_stamp.tz_convert("America/Sao_Paulo")
    updated_text = updated_stamp.strftime("%d/%m/%Y às %H:%M")
else:
    updated_text = "não disponível"

# Indicadores principais: resposta em horas úteis e resolução em horas corridas.
response_hours = response_solved["Response business hours"].mean()
resolution_hours = resolution_solved["Resolution calendar hours"].mean()
response_median = response_solved["Response weekday hours"].median()
resolution_median = resolution_solved["Resolution calendar hours"].median()
# Leitura complementar com a base de tempo oposta.
response_calendar_hours = response_solved["Response weekday hours"].mean()
resolution_business_hours = resolution_solved["Resolution business hours"].mean()

# CSAT: Good / (Good + Bad). Offered entra somente na taxa de resposta.
satisfaction = solved["Satisfaction Score"].fillna("").str.strip().str.casefold()
good_count = int(satisfaction.eq("good").sum())
bad_count = int(satisfaction.eq("bad").sum())
offered_count = int(satisfaction.eq("offered").sum())
rated_count = good_count + bad_count
surveyed_count = rated_count + offered_count
csat_rate = good_count / rated_count if rated_count else float("nan")
survey_response_rate = rated_count / surveyed_count if surveyed_count else float("nan")
response_status = (
    "Sem dados"
    if pd.isna(response_hours)
    else "Dentro da meta" if response_hours <= META_TEMPO_RESPOSTA_H else "Acima da meta"
)
resolution_status = "Dentro da meta" if resolution_hours <= META_TEMPO_RESOLUCAO_H else "Acima da meta"
response_tone = (
    "blue"
    if pd.isna(response_hours)
    else "teal" if response_hours <= META_TEMPO_RESPOSTA_H else "red"
)

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
    metric_card("Tempo médio de resposta", f"{format_decimal(response_hours)} h", f"Horas úteis • {format_number(len(response_solved))} tickets • {response_status}", response_tone),
    metric_card("Tempo médio de resolução", f"{format_decimal(resolution_hours)} h", f"Horas corridas • {format_number(len(resolution_solved))} tickets", "teal" if resolution_hours <= META_TEMPO_RESOLUCAO_H else "red"),
    metric_card("CSAT", format_percent(csat_rate), f"{format_number(rated_count)} avaliações respondidas", "blue"),
    metric_card("Tickets resolvidos", format_number(len(resolution_solved)), f"IDs únicos • de {selected_start.strftime('%d/%m')} a {selected_end.strftime('%d/%m')}", "gold"),
])
st.markdown(f'<div class="metric-grid">{cards}</div>', unsafe_allow_html=True)

st.markdown('<div class="section-heading"><div class="section-title">Meta x realizado</div><div class="section-caption">Resposta: criação até a primeira atribuição, na agenda 9h–18h. Resolução: horas corridas. Quanto menor, melhor.</div></div>', unsafe_allow_html=True)
performance_html = performance_row("Tempo de resposta (horas úteis)", META_TEMPO_RESPOSTA_H, response_hours) + performance_row("Tempo de resolução (horas corridas)", META_TEMPO_RESOLUCAO_H, resolution_hours)
st.markdown(f'<div class="performance-table">{performance_html}</div>', unsafe_allow_html=True)

if period_mode in {"Mês", "Ano inteiro"}:
    history_start = pd.Timestamp(selected_start).replace(month=1, day=1)
else:
    history_start = pd.Timestamp(selected_start)
history_end = min(pd.Timestamp(selected_end), solved_all["Solved at"].max())
history_periods = list(pd.period_range(history_start, history_end, freq="M"))
history_source = solved_all.copy()
if selected_agents:
    history_source = history_source[history_source["Assignee"].isin(selected_agents)].copy()
if period_mode == "Período personalizado":
    history_source = history_source[
        history_source["Solved at"].ge(start_datetime)
        & history_source["Solved at"].lt(end_datetime)
    ].copy()

if history_periods:
    st.markdown('<div class="section-heading"><div class="section-title">Tempos de resposta e resolução — mês vs mês</div><div class="section-caption">Resposta em horas úteis; resolução em horas corridas. (O) é objetivo, (R) é realizado e os valores são médias.</div></div>', unsafe_allow_html=True)
    st.markdown(monthly_table(history_source, history_periods), unsafe_allow_html=True)

st.markdown(
    '<div class="comparison-strip">'
    '<div class="comparison-intro"><strong>Base de tempo complementar</strong><span>Os mesmos indicadores observados pela base de tempo oposta.</span></div>'
    f'<div class="comparison-item"><span>Resposta em horas corridas · criação → 1ª atribuição</span><strong>{format_decimal(response_calendar_hours)} h</strong></div>'
    f'<div class="comparison-item"><span>Resolução em horas úteis</span><strong>{format_decimal(resolution_business_hours)} h</strong></div>'
    '</div>',
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="comparison-strip">'
    '<div class="comparison-intro"><strong>Mediana, para contexto</strong><span>Mesmas bases dos indicadores principais.</span></div>'
    f'<div class="comparison-item"><span>Tempo de resposta · horas úteis</span><strong>{format_decimal(response_median)} h</strong></div>'
    f'<div class="comparison-item"><span>Tempo de resolução · horas corridas</span><strong>{format_decimal(resolution_median)} h</strong></div>'
    '</div>',
    unsafe_allow_html=True,
)

st.markdown('<div class="section-heading"><div class="section-title">Tempo médio de resolução por motivo</div><div class="section-caption">Resultado principal em horas corridas. A mediana aparece ao passar o mouse.</div></div>', unsafe_allow_html=True)
resolution_reason = (
    resolution_solved.groupby("Motivo do Contato [list]", as_index=False)
    .agg(
        **{
            "Tempo médio (h)": ("Resolution calendar hours", "mean"),
            "Mediana (h)": ("Resolution calendar hours", "median"),
            "Tickets": ("Id", "count"),
        }
    )
    .dropna(subset=["Tempo médio (h)"])
)
resolution_reason = resolution_reason.nlargest(12, "Tickets").sort_values("Tempo médio (h)")
resolution_reason_figure = px.bar(
    resolution_reason, x="Tempo médio (h)", y="Motivo do Contato [list]", orientation="h",
    text="Tempo médio (h)", hover_data={"Tickets": True, "Tempo médio (h)": ":.1f", "Mediana (h)": ":.1f"},
    color="Tempo médio (h)", color_continuous_scale=[[0, "#CFE8E0"], [1, COLORS["navy"]]],
)
resolution_reason_figure.update_traces(texttemplate="%{text:.1f} h", textposition="outside", cliponaxis=False)
resolution_reason_figure.update_layout(height=430, margin=dict(l=10, r=65, t=10, b=35), xaxis_title="Horas corridas", yaxis_title="", coloraxis_showscale=False, paper_bgcolor="white", plot_bgcolor="white")
st.plotly_chart(finish_figure(resolution_reason_figure), width="stretch", theme=None, config={"displayModeBar": False})

st.markdown('<div class="section-heading"><div class="section-title">Visão por agente</div><div class="section-caption">Volume, tempos médios e CSAT de cada responsável.</div></div>', unsafe_allow_html=True)
agent_rows = []
for agent_name, agent_data in solved.groupby("Assignee"):
    agent_resolution = resolution_scope(agent_data)
    agent_response = response_scope(agent_data)
    if agent_resolution.empty:
        continue
    agent_satisfaction = agent_data["Satisfaction Score"].fillna("").str.strip().str.casefold()
    agent_good = int(agent_satisfaction.eq("good").sum())
    agent_bad = int(agent_satisfaction.eq("bad").sum())
    agent_rated = agent_good + agent_bad
    agent_rows.append({
        "Agente": agent_name,
        "Tickets resolvidos": len(agent_resolution),
        "Resposta média (h)": agent_response["Response business hours"].mean(),
        "Resolução média (h)": agent_resolution["Resolution calendar hours"].mean(),
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
        f'<div class="agent-stat"><strong>{format_decimal(agent["Resposta média (h)"])} h</strong><span>Resposta média · úteis</span></div>'
        f'<div class="agent-stat"><strong>{format_decimal(agent["Resolução média (h)"])} h</strong><span>Resolução média · corridas</span></div>'
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
    if selected_period != reference_period:
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
    solved[
        solved["Satisfaction Score"].fillna("").str.strip().str.casefold().eq("bad")
    ]["Motivo do Contato [list]"]
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
external_solved = resolution_solved[
    ~resolution_solved["Motivo do Contato [list]"].str.contains("uso interno", case=False, na=False)
]
reason_counts = external_solved["Motivo do Contato [list]"].value_counts().rename_axis("Motivo").reset_index(name="Tickets").head(12).sort_values("Tickets")
reason_figure = px.bar(reason_counts, x="Tickets", y="Motivo", orientation="h", text_auto=True, color="Tickets", color_continuous_scale=[[0, "#CFE2F5"], [1, COLORS["navy"]]])
reason_figure.update_traces(textposition="outside", cliponaxis=False)
reason_figure.update_layout(height=430, margin=dict(l=10, r=55, t=15, b=35), xaxis_title="Tickets resolvidos", yaxis_title="", coloraxis_showscale=False, paper_bgcolor="white", plot_bgcolor="white")
st.plotly_chart(finish_figure(reason_figure), width="stretch", theme=None, config={"displayModeBar": False})

duplicate_note = (
    f"{format_number(duplicates_removed)} duplicado(s) removido(s) automaticamente"
    if duplicates_removed
    else "nenhum ID duplicado encontrado"
)
st.markdown(
    f'<div class="source-note">Fonte: {html.escape(source_name)} • atualização no GitHub: {html.escape(updated_text)} • '
    f'{html.escape(duplicate_note)} • {format_number(len(resolution_solved))} tickets no KPI de resolução</div>',
    unsafe_allow_html=True,
)
