"""Streamlit UI — CRM de seguimiento de procesos SECOP II para FEAB.

Flujo único tipo CRM:

1.  Banner institucional (paleta Fiscalía, sin emojis, sin look "demo IA")
2.  Barra de acciones: botón grande "Actualizar todos los procesos",
    contador de procesos, fecha de la última actualización global.
3.  Aviso de banderas rojas (solo si existen).
4.  Tabla CRM principal con una fila por proceso y columnas curadas —
    proceso, objeto, proveedor, valor, estado, fecha firma, modificatorio,
    última actualización, link SECOP. Filtros tipo Excel (AgGrid).
5.  Detalle del proceso seleccionado — todos los campos bajo la tabla.
6.  Sidebar con archivo actual, configuración y botón de auditoría.

Se mantiene la lógica de config + upload + pipeline intacta; es un
rediseño de la capa visual, no de la de datos.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from secop_ii.audit import audit_workbook, render_markdown
from secop_ii.changelog import (
    diff_snapshots,
    load_latest_snapshot,
    snapshot_from_excel,
    summarize_changelog,
)
from secop_ii.excel_io import (
    append_process_url,
    delete_row,
    load_workbook,
    preview_as_dicts,
)
from secop_ii.excel_pro import build_audit_workbook
from secop_ii.feab_dashboard import fetch_feab_snapshot
from secop_ii.feab_changelog import (
    compute_changelog,
    load_previous_snapshot,
    save_snapshot as save_feab_snapshot,
)
from secop_ii.orchestrator import LAST_UPDATE_COLUMN, STATUS_COLUMN, process_workbook
from secop_ii.secop_client import SecopClient

APP_TITLE = "Dra Cami Contractual"
APP_SUBTITLE = "Espejo automático del SECOP II · Subdirección de Gestión Contractual · FEAB · Fiscalía General de la Nación"
USER_NAME = "Dra. María Camila Mendoza Zubiría"
USER_ROLE = "Jefe de Gestión Contractual del FEAB"

# Paleta NY law-firm (Cravath / Skadden / S&C) modernizada: blanco puro,
# negro profundo, acentos institucionales FGN muy controlados. Sin cream,
# sin gradientes, sin sombras pesadas. El espacio habla.
FGN_RED = "#6E1E2F"    # burgundy profundo — acento único destacado
FGN_GOLD = "#8A6A1E"   # dorado muy apagado, solo para detalles
FGN_NAVY = "#0E1A3A"   # navy muy profundo
BG_CREAM = "#FFFFFF"   # blanco puro
BG_WHITE = "#FFFFFF"
BG_SURFACE = "#FAFAF8" # superficie muy sutil para cards
INK = "#0A0A0A"        # negro definitivo
INK_SOFT = "#6B6560"
RULE = "#E5E1D8"       # hairline beige casi imperceptible
BG_LIGHT = BG_SURFACE

# Columnas curadas para la vista CRM (en orden). Mezcla campos originales
# de la Dra. (prefijo numérico tipo "2. NÚMERO…") con campos enriquecidos
# por SECOP. Los substrings se matchean case-insensitive contra los
# encabezados reales — así sobrevivimos a espacios/acentos extra que la
# Dra. dejó en sus nombres de columna.
_CRM_COLUMN_PATTERNS = [
    # Identificación del contrato (sus columnas originales)
    "2. ",                       # 2. NÚMERO DE CONTRATO
    "3.VIGENCIA",
    "4. OBJETO",
    # Fechas
    "5. FECHA SUSCRIPCI",
    "8. FECHA INICIO",
    "9. FECHA TERMINACI",
    # Estado
    "10.ESTADO DEL CONTRATO",
    # Modalidad + clase
    "12. MODALIDAD",
    "13. CLASE DE CONTRATO",
    # Valores
    "28.VALOR INICIAL",
    "36. VALOR TOTAL",
    # Contratista
    "41. CONTRATISTA",
    "43. CONTRATISTA : NOMBRE",
    # Supervisor
    "53. SUPERVISOR : NOMBRE",
    # Liquidación
    "67.REQUIERE LIQUIDACI",
    # Nota humana y link
    "72. OBSERVACIONES",
    "LINK",
    # Campos que agregamos nosotros (SECOP)
    "ID identificado",
    "Fase en SECOP",
    "Contrato: Proveedor adjudicado",
    "Contrato: Valor",
    "Contrato: Fecha firma",
    "¿Hubo modificatorio?",
    "# modificatorios",
    "Docs: # Modificatorios",
    "Garantías: # pólizas",
    "Pagos: Total pagado",
    STATUS_COLUMN,
    LAST_UPDATE_COLUMN,
    "Link verificación API",
]


def _resolve_crm_columns(all_cols: list[str]) -> list[str]:
    """Match the CRM patterns against the real headers — preserves order, dedups."""
    used: set[str] = set()
    out: list[str] = []
    for pat in _CRM_COLUMN_PATTERNS:
        pat_norm = pat.upper().strip()
        for col in all_cols:
            if col in used:
                continue
            if pat_norm in str(col).upper():
                used.add(col)
                out.append(col)
                break
    return out


# ---------------------------------------------------------------------------
# Config persistence
# ---------------------------------------------------------------------------
def _config_dir() -> Path:
    base = os.environ.get("APPDATA") or os.environ.get("HOME") or tempfile.gettempdir()
    path = Path(base) / "SecopII"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _load_config() -> dict:
    cfg_path = _config_dir() / "config.json"
    if cfg_path.is_file():
        try:
            return json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_config(cfg: dict) -> None:
    cfg_path = _config_dir() / "config.json"
    cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def _persist_upload(uploaded_file, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / uploaded_file.name
    dest.write_bytes(uploaded_file.getbuffer())
    return dest


def _open_in_explorer(path: Path) -> None:
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            os.system(f'open "{path}"')
        else:
            os.system(f'xdg-open "{path}"')
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------
_CSS = f"""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600;9..144,700&family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>

    /* =================================================================
       SECTION — Foundation (reset + typography)
       ================================================================= */
    html, body {{ background: {BG_CREAM}; }}
    html, body, [class*="css"] {{
        font-family: 'Inter', 'Söhne', 'Segoe UI', -apple-system, sans-serif;
        color: {INK};
        -webkit-font-smoothing: antialiased;
        -moz-osx-font-smoothing: grayscale;
    }}
    .main, .main .block-container {{ background: {BG_CREAM}; }}
    .main .block-container {{
        padding-top: 2.5rem; padding-bottom: 4rem;
        max-width: 1320px;
    }}
    header[data-testid="stHeader"] {{
        background: {BG_CREAM} !important;
        box-shadow: none !important;
    }}
    ::selection {{ background: {FGN_RED}; color: white; }}

    /* =================================================================
       SECTION — Banner (editorial masthead)
       ================================================================= */
    .sec-banner {{
        background: {BG_WHITE};
        color: {INK};
        padding: 56px 56px 44px 56px;
        border-top: 3px solid {FGN_NAVY};
        border-bottom: 1px solid {RULE};
        margin: -2.5rem -1rem 2.5rem -1rem;
        position: relative;
    }}
    .sec-banner::before {{
        content: "Auditoría · Gestión Contractual";
        display: block;
        font-size: 0.7rem;
        letter-spacing: 0.28em;
        text-transform: uppercase;
        color: {FGN_RED};
        font-weight: 600;
        margin-bottom: 24px;
    }}
    .sec-banner h1 {{
        font-family: 'Fraunces', 'Tiempos Headline', Georgia, serif;
        margin: 0; font-size: 2.8rem; font-weight: 500;
        letter-spacing: -0.028em; line-height: 1.05;
        color: {INK}; font-variation-settings: "opsz" 96;
    }}
    .sec-banner p {{
        margin: 18px 0 0 0; font-size: 0.8rem; font-weight: 400;
        letter-spacing: 0.26em; text-transform: uppercase;
        color: {INK_SOFT};
    }}

    /* =================================================================
       SECTION — Typography rhythm
       ================================================================= */
    h1, h2, h3, h4 {{
        font-family: 'Fraunces', Georgia, serif !important;
        font-weight: 500 !important;
        letter-spacing: -0.018em;
        color: {INK} !important;
    }}
    h2 {{ font-size: 1.55rem !important; margin-top: 2.5rem !important; }}
    h3 {{ font-size: 1.2rem !important; }}
    p, li, span, div {{ line-height: 1.55; }}

    /* =================================================================
       SECTION — KPI / movement cards
       ================================================================= */
    .kpi-card {{
        background: {BG_WHITE};
        border: 1px solid {RULE};
        padding: 22px 26px;
        border-radius: 0;
        position: relative;
    }}
    .kpi-card::before {{
        content: ""; position: absolute;
        left: 0; top: 0; bottom: 0; width: 3px;
        background: {FGN_NAVY};
    }}
    .kpi-card.alert::before {{ background: {FGN_RED}; }}
    .kpi-card.gold::before {{ background: {FGN_GOLD}; }}
    .kpi-label {{
        color: {INK_SOFT}; font-size: 0.68rem;
        text-transform: uppercase; letter-spacing: 0.18em;
        font-weight: 500; margin-bottom: 10px;
    }}
    .kpi-value {{
        font-family: 'Fraunces', Georgia, serif;
        color: {INK}; font-size: 2.1rem; font-weight: 500;
        line-height: 1; letter-spacing: -0.02em;
        font-variation-settings: "opsz" 72;
    }}
    .kpi-card.alert .kpi-value {{ color: {FGN_RED}; }}

    /* =================================================================
       SECTION — Action / stats / flags bars
       ================================================================= */
    .action-bar {{
        background: {BG_WHITE}; border: 1px solid {RULE};
        padding: 20px 26px; border-radius: 0; margin-bottom: 14px;
    }}
    .crm-stats {{ color: {INK}; font-size: 0.92rem; line-height: 1.6; }}
    .crm-stats strong {{ font-weight: 600; }}
    .last-update {{
        color: {FGN_NAVY};
        font-family: 'Fraunces', Georgia, serif;
        font-size: 1.15rem; font-weight: 500;
        letter-spacing: -0.01em;
    }}

    .flag-banner {{
        background: {BG_WHITE}; border: 1px solid {RULE};
        border-left: 3px solid {FGN_RED};
        padding: 20px 26px; border-radius: 0; margin-bottom: 18px;
    }}
    .flag-banner strong {{
        color: {FGN_RED}; letter-spacing: 0.16em;
        text-transform: uppercase; font-size: 0.7rem; font-weight: 600;
    }}
    .flag-banner ul {{ margin-top: 14px; margin-left: 0; padding-left: 22px; }}
    .flag-banner li {{ font-size: 0.92rem; margin-bottom: 7px; }}

    /* =================================================================
       SECTION — Buttons (restrained, tracked, hairline)
       ================================================================= */
    .stButton>button {{
        border-radius: 0 !important;
        font-weight: 500 !important;
        letter-spacing: 0.08em;
        transition: all 0.18s ease;
        border: 1px solid {INK} !important;
        background: transparent !important;
        color: {INK} !important;
        text-transform: uppercase;
        font-size: 0.75rem !important;
        padding: 11px 22px !important;
        font-family: 'Inter', sans-serif;
    }}
    .stButton>button:hover {{
        background: {INK} !important;
        color: {BG_CREAM} !important;
        border-color: {INK} !important;
    }}
    .stButton>button[kind="primary"] {{
        background: {FGN_RED} !important;
        border-color: {FGN_RED} !important;
        color: #FFFFFF !important;
        padding: 13px 30px !important;
        font-weight: 600 !important;
        letter-spacing: 0.14em;
    }}
    .stButton>button[kind="primary"]:hover {{
        background: {INK} !important; border-color: {INK} !important;
    }}
    .stDownloadButton>button {{
        border-radius: 0 !important;
        font-weight: 500 !important;
        letter-spacing: 0.08em;
        border: 1px solid {INK} !important;
        background: transparent !important;
        color: {INK} !important;
        text-transform: uppercase;
        font-size: 0.75rem !important;
        padding: 11px 22px !important;
        transition: all 0.18s ease;
    }}
    .stDownloadButton>button:hover {{
        background: {INK} !important;
        color: {BG_CREAM} !important;
    }}

    /* =================================================================
       SECTION — Pills / slicers (st.pills)
       ================================================================= */
    div[data-testid="stPills"] {{
        gap: 8px !important;
        padding: 4px 0;
    }}
    div[data-testid="stPills"] label, div[data-testid="stPills"] button {{
        background: {BG_WHITE} !important;
        border: 1px solid {RULE} !important;
        border-radius: 0 !important;
        color: {INK} !important;
        padding: 9px 18px !important;
        font-size: 0.78rem !important;
        font-weight: 500 !important;
        letter-spacing: 0.05em;
        transition: all 0.15s ease;
        cursor: pointer;
    }}
    div[data-testid="stPills"] label:hover, div[data-testid="stPills"] button:hover {{
        border-color: {INK} !important;
        background: {BG_CREAM} !important;
    }}
    /* Selected pill */
    div[data-testid="stPills"] label[data-checked="true"],
    div[data-testid="stPills"] button[aria-pressed="true"],
    div[data-testid="stPills"] button[aria-selected="true"] {{
        background: {INK} !important;
        border-color: {INK} !important;
        color: {BG_CREAM} !important;
        font-weight: 600 !important;
    }}

    /* =================================================================
       SECTION — Sidebar
       ================================================================= */
    section[data-testid="stSidebar"] {{
        border-right: 1px solid {RULE};
        background: #F2EBDB;
    }}
    section[data-testid="stSidebar"] h3 {{
        font-family: 'Inter', sans-serif !important;
        font-size: 0.7rem !important;
        text-transform: uppercase;
        letter-spacing: 0.22em;
        font-weight: 600 !important;
        color: {FGN_NAVY} !important;
        border-bottom: 1px solid {RULE};
        padding-bottom: 12px;
        margin-top: 22px !important;
    }}

    /* =================================================================
       SECTION — DataFrame (inventory grid)
       ================================================================= */
    [data-testid="stDataFrame"] {{
        border: 1px solid {RULE};
        border-radius: 0;
        font-family: 'Inter', sans-serif;
    }}
    [data-testid="stDataFrame"] [role="columnheader"] {{
        background: {BG_SURFACE} !important;
        text-transform: uppercase;
        letter-spacing: 0.14em;
        font-size: 0.7rem !important;
        font-weight: 600 !important;
        color: {INK} !important;
        border-bottom: 1px solid {INK} !important;
        padding: 14px 12px !important;
        font-family: 'Inter', sans-serif !important;
    }}
    [data-testid="stDataFrame"] [role="row"] > [role="gridcell"] {{
        font-size: 0.85rem !important;
        padding: 12px !important;
        color: {INK};
        border-bottom: 1px solid {RULE} !important;
    }}
    [data-testid="stDataFrame"] [role="row"]:hover {{
        background: {BG_SURFACE} !important;
    }}

    /* =================================================================
       SECTION — Inputs (text, select, number)
       ================================================================= */
    .stTextInput input, .stNumberInput input,
    .stSelectbox div[data-baseweb="select"] > div,
    .stDateInput input {{
        border-radius: 0 !important;
        border: 1px solid {RULE} !important;
        background: {BG_WHITE} !important;
        font-size: 0.92rem !important;
        padding: 12px 16px !important;
        font-family: 'Inter', sans-serif;
    }}
    .stTextInput input::placeholder {{
        color: {INK_SOFT}; font-style: italic;
    }}
    .stTextInput input:focus, .stNumberInput input:focus {{
        border-color: {INK} !important;
        box-shadow: none !important;
    }}
    /* Large, editorial search box */
    .stTextInput input {{
        font-size: 0.98rem !important;
        padding: 14px 18px !important;
    }}

    /* =================================================================
       SECTION — Radio (mode selector)
       ================================================================= */
    div[role="radiogroup"] {{
        gap: 36px;
        padding: 14px 0 18px 0;
        border-bottom: 1px solid {RULE};
        margin-bottom: 22px;
    }}
    div[role="radiogroup"] label {{
        font-weight: 500;
        letter-spacing: 0.05em;
        font-size: 0.92rem;
        text-transform: none;
    }}

    /* =================================================================
       SECTION — Tabs
       ================================================================= */
    button[data-baseweb="tab"] {{
        font-weight: 600 !important;
        letter-spacing: 0.16em;
        text-transform: uppercase;
        font-size: 0.72rem !important;
        padding: 16px 18px !important;
    }}
    button[data-baseweb="tab"][aria-selected="true"] {{
        color: {FGN_RED} !important;
    }}
    div[data-baseweb="tab-highlight"] {{
        background-color: {FGN_RED} !important;
        height: 2px !important;
    }}
    div[data-baseweb="tab-list"] {{
        border-bottom: 1px solid {RULE} !important;
        margin-bottom: 18px;
    }}

    /* =================================================================
       SECTION — Expanders
       ================================================================= */
    div[data-testid="stExpander"] {{
        border: 1px solid {RULE};
        border-radius: 0;
        background: {BG_WHITE};
    }}
    div[data-testid="stExpander"] summary {{
        padding: 14px 20px !important;
        font-weight: 500 !important;
        font-size: 0.88rem !important;
        letter-spacing: 0.02em;
    }}

    /* =================================================================
       SECTION — Toggle (auto-refresh switch)
       ================================================================= */
    .stCheckbox label, .stToggle label {{
        font-size: 0.88rem !important;
        letter-spacing: 0.02em;
        color: {INK};
    }}

    /* =================================================================
       SECTION — Captions
       ================================================================= */
    [data-testid="stCaptionContainer"] {{
        color: {INK_SOFT}; font-style: italic;
        letter-spacing: 0.02em; font-size: 0.82rem;
    }}

    /* =================================================================
       SECTION — Footer
       ================================================================= */
    .sec-footer {{
        color: {INK_SOFT}; font-size: 0.72rem;
        text-align: center; padding: 36px 0 18px 0;
        margin-top: 72px; border-top: 1px solid {RULE};
        letter-spacing: 0.12em;
    }}
    .sec-footer code {{
        background: transparent; color: {FGN_NAVY};
        padding: 0; font-size: 0.72rem;
        font-family: 'Inter', sans-serif;
    }}
    /* Base — warm cream background, editorial typography ------------- */
    html, body {{
        background: {BG_CREAM};
    }}
    html, body, [class*="css"] {{
        font-family: 'Inter', 'Söhne', 'Segoe UI', -apple-system, sans-serif;
        color: {INK};
    }}
    .main, .main .block-container {{
        background: {BG_CREAM};
    }}
    .main .block-container {{
        padding-top: 2rem;
        padding-bottom: 3rem;
        max-width: 1440px;
    }}
    header[data-testid="stHeader"] {{
        background: {BG_CREAM} !important;
        box-shadow: none !important;
    }}

    /* Banner — editorial masthead, not a "hero section" -------------- */
    .sec-banner {{
        background: {BG_WHITE};
        color: {INK};
        padding: 42px 48px 36px 48px;
        border-top: 4px solid {FGN_NAVY};
        border-bottom: 1px solid {RULE};
        margin: -2rem -1rem 2.25rem -1rem;
        position: relative;
    }}
    .sec-banner::before {{
        content: "Auditoría · Gestión Contractual";
        display: block;
        font-size: 0.72rem;
        letter-spacing: 0.24em;
        text-transform: uppercase;
        color: {FGN_RED};
        font-weight: 600;
        margin-bottom: 18px;
    }}
    .sec-banner h1 {{
        font-family: 'Fraunces', 'Tiempos Headline', Georgia, serif;
        margin: 0;
        font-size: 2.45rem;
        font-weight: 500;
        letter-spacing: -0.025em;
        line-height: 1.08;
        color: {INK};
        font-variation-settings: "opsz" 48;
    }}
    .sec-banner p {{
        margin: 14px 0 0 0;
        font-size: 0.82rem;
        font-weight: 400;
        letter-spacing: 0.22em;
        text-transform: uppercase;
        color: {INK_SOFT};
    }}

    /* Section headings ------------------------------------------------ */
    h1, h2, h3 {{
        font-family: 'Fraunces', Georgia, serif !important;
        font-weight: 500 !important;
        letter-spacing: -0.015em;
        color: {INK} !important;
    }}
    h2 {{ font-size: 1.5rem !important; }}
    h3 {{ font-size: 1.15rem !important; }}

    /* KPI cards — print-style, numbers in serif --------------------- */
    .kpi-card {{
        background: {BG_WHITE};
        border: 1px solid {RULE};
        padding: 20px 24px;
        border-radius: 0;
        position: relative;
    }}
    .kpi-card::before {{
        content: "";
        position: absolute;
        left: 0; top: 0; bottom: 0;
        width: 3px;
        background: {FGN_NAVY};
    }}
    .kpi-card.alert::before {{ background: {FGN_RED}; }}
    .kpi-card.gold::before {{ background: {FGN_GOLD}; }}
    .kpi-label {{
        color: {INK_SOFT};
        font-size: 0.68rem;
        text-transform: uppercase;
        letter-spacing: 0.18em;
        font-weight: 500;
        margin-bottom: 10px;
    }}
    .kpi-value {{
        font-family: 'Fraunces', Georgia, serif;
        color: {INK};
        font-size: 2.1rem;
        font-weight: 500;
        line-height: 1;
        letter-spacing: -0.02em;
        font-variation-settings: "opsz" 72;
    }}
    .kpi-card.alert .kpi-value {{ color: {FGN_RED}; }}

    /* Bars — action and stat panels --------------------------------- */
    .action-bar {{
        background: {BG_WHITE};
        border: 1px solid {RULE};
        padding: 18px 22px;
        border-radius: 0;
        margin-bottom: 14px;
    }}
    .crm-stats {{
        color: {INK};
        font-size: 0.92rem;
        line-height: 1.55;
    }}
    .crm-stats strong {{ color: {INK}; font-weight: 600; }}
    .last-update {{
        color: {FGN_NAVY};
        font-family: 'Fraunces', Georgia, serif;
        font-size: 1.1rem;
        font-weight: 500;
        letter-spacing: -0.01em;
    }}

    /* Red-flag banner ----------------------------------------------- */
    .flag-banner {{
        background: {BG_WHITE};
        border: 1px solid {RULE};
        border-left: 3px solid {FGN_RED};
        padding: 18px 24px;
        border-radius: 0;
        margin-bottom: 16px;
    }}
    .flag-banner strong {{
        color: {FGN_RED};
        letter-spacing: 0.14em;
        text-transform: uppercase;
        font-size: 0.72rem;
        font-weight: 600;
    }}
    .flag-banner ul {{ margin-top: 12px; margin-left: 0; padding-left: 20px; }}
    .flag-banner li {{ font-size: 0.92rem; margin-bottom: 6px; line-height: 1.5; }}

    /* Buttons — reserved, uppercase hairline ------------------------ */
    .stButton>button {{
        border-radius: 0 !important;
        font-weight: 500 !important;
        letter-spacing: 0.08em;
        transition: all 0.15s ease;
        border: 1px solid {RULE} !important;
        background: {BG_WHITE} !important;
        color: {INK} !important;
        text-transform: uppercase;
        font-size: 0.78rem !important;
        padding: 10px 20px !important;
    }}
    .stButton>button:hover {{
        background: {BG_CREAM} !important;
        border-color: {INK_SOFT} !important;
    }}
    .stButton>button[kind="primary"] {{
        background: {FGN_RED} !important;
        border-color: {FGN_RED} !important;
        color: #FFFFFF !important;
        padding: 12px 28px !important;
        font-weight: 600 !important;
        letter-spacing: 0.12em;
    }}
    .stButton>button[kind="primary"]:hover {{
        background: #6E1E2F !important;
        border-color: #6E1E2F !important;
    }}

    /* Sidebar — beige leaf, rule separators ------------------------- */
    section[data-testid="stSidebar"] {{
        border-right: 1px solid {RULE};
        background: #F2EBDB;
    }}
    section[data-testid="stSidebar"] h3 {{
        font-family: 'Inter', sans-serif !important;
        font-size: 0.72rem !important;
        text-transform: uppercase;
        letter-spacing: 0.18em;
        font-weight: 600 !important;
        color: {FGN_NAVY} !important;
        border-bottom: 1px solid {RULE};
        padding-bottom: 10px;
        margin-top: 18px;
    }}

    /* DataFrame — editorial grid --------------------------------- */
    [data-testid="stDataFrame"] {{
        border: 1px solid {RULE};
        border-radius: 0;
    }}
    [data-testid="stDataFrame"] [role="columnheader"] {{
        background: {BG_CREAM} !important;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        font-size: 0.72rem !important;
        font-weight: 600 !important;
        color: {FGN_NAVY} !important;
    }}

    /* Inputs -------------------------------------------------------- */
    .stTextInput input, .stNumberInput input,
    .stSelectbox div[data-baseweb="select"] > div,
    .stDateInput input {{
        border-radius: 0 !important;
        border-color: {RULE} !important;
        background: {BG_WHITE} !important;
    }}
    .stTextInput input:focus, .stNumberInput input:focus {{
        border-color: {FGN_NAVY} !important;
        box-shadow: none !important;
    }}

    /* Radio ---------------------------------------------------- */
    div[role="radiogroup"] {{
        gap: 32px;
        padding: 8px 0;
        border-bottom: 1px solid {RULE};
        margin-bottom: 12px;
    }}
    div[role="radiogroup"] label {{
        font-weight: 500;
        letter-spacing: 0.04em;
        font-size: 0.9rem;
    }}

    /* Tabs ---------------------------------------------------- */
    button[data-baseweb="tab"] {{
        font-weight: 500 !important;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        font-size: 0.74rem !important;
    }}
    button[data-baseweb="tab"][aria-selected="true"] {{
        color: {FGN_RED} !important;
    }}
    div[data-baseweb="tab-highlight"] {{ background-color: {FGN_RED} !important; }}

    /* Expanders ---------------------------------------------- */
    div[data-testid="stExpander"] {{
        border: 1px solid {RULE};
        border-radius: 0;
        background: {BG_WHITE};
    }}

    /* Footer -------------------------------------------------- */
    .sec-footer {{
        color: {INK_SOFT};
        font-size: 0.74rem;
        text-align: center;
        padding: 28px 0 14px 0;
        margin-top: 52px;
        border-top: 1px solid {RULE};
        letter-spacing: 0.08em;
    }}
    .sec-footer code {{
        background: transparent;
        color: {FGN_NAVY};
        padding: 0;
        font-size: 0.74rem;
        font-family: 'Inter', sans-serif;
    }}

    /* Captions --------------------------------------------------- */
    [data-testid="stCaptionContainer"] {{
        color: {INK_SOFT};
        font-style: italic;
        letter-spacing: 0.02em;
    }}
</style>
"""



# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def _load_preview(path_str: str, mtime: float) -> pd.DataFrame:
    _ = mtime  # cache key
    _, ws = load_workbook(path_str)
    rows = preview_as_dicts(ws)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    if "__row__" in df.columns:
        df = df.drop(columns=["__row__"])
    return df


def _compute_audit(path: Path):
    audits = audit_workbook(path)
    counts: dict[str, int] = {}
    for a in audits:
        counts[a.verdict] = counts.get(a.verdict, 0) + 1
    flagged = [a for a in audits if a.needs_review]
    return audits, counts, flagged


@st.cache_data(show_spinner="Consultando SECOP II…", ttl=300)
def _fetch_feab_snapshot_cached(token: str | None, rate: float, cache_key: int):
    """Pull all FEAB processes + contracts. Cached 5 min; cache_key busts on click."""
    _ = cache_key  # part of cache key, allows manual refresh
    client = SecopClient(app_token=token, rate_per_second=rate)
    return fetch_feab_snapshot(client)


def _last_update_global(df: pd.DataFrame) -> str:
    """Return the most recent value of the 'Última actualización' column, or empty."""
    if LAST_UPDATE_COLUMN not in df.columns:
        return ""
    col = df[LAST_UPDATE_COLUMN].dropna().astype(str).str.strip()
    col = col[col != ""]
    if col.empty:
        return ""
    try:
        # The orchestrator writes ISO-like timestamps; max() on strings is chronologically
        # correct for "YYYY-MM-DD HH:MM" format.
        return str(col.max())
    except Exception:
        return str(col.iloc[-1])


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------
def _kpi(col, label: str, value, *, variant: str = "") -> None:
    klass = f"kpi-card {variant}".strip()
    col.markdown(
        f"""
        <div class="{klass}">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_banner() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
    today_es = _format_spanish_date(datetime.now())
    st.markdown(
        f"""
        <div class="sec-banner">
            <h1>Bienvenida, {USER_NAME}</h1>
            <p>{USER_ROLE} · {today_es}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


_MESES_ES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)
_DIAS_ES = (
    "lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo",
)


def _format_spanish_date(dt: datetime) -> str:
    dia = _DIAS_ES[dt.weekday()]
    mes = _MESES_ES[dt.month - 1]
    return f"{dia.capitalize()}, {dt.day} de {mes} de {dt.year}"


def _render_changelog_card(excel_path: Path) -> None:
    """Show a 'what changed since last run' summary card."""
    try:
        current = snapshot_from_excel(excel_path)
    except Exception:
        return
    if not current:
        return

    latest = load_latest_snapshot()
    if latest is None:
        # First run ever — no baseline to compare against
        st.markdown(
            f"""
            <div class="action-bar">
                <div class="crm-stats">
                    <strong>Primera corrida</strong> — al terminar la próxima actualización
                    veré los cambios desde hoy.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    prev_date, prev_snap = latest
    cl = diff_snapshots(prev_snap, current, prev_date=prev_date)
    summary = summarize_changelog(cl)

    badge = (
        f"<span style='color:{FGN_RED};font-weight:700'>{cl.total} novedad(es)</span>"
        if cl.total else
        f"<span style='color:#2A7A38'>sin novedades</span>"
    )
    st.markdown(
        f"""
        <div class="action-bar">
            <div class="crm-stats">
                Desde la última corrida ({prev_date}): {badge}<br>
                <span style="color:#555">{summary}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if cl.total:
        with st.expander("Ver detalle de los cambios", expanded=False):
            if cl.added:
                st.markdown(f"**{len(cl.added)} proceso(s) nuevo(s):**")
                for pid in cl.added[:20]:
                    st.markdown(f"- `{pid}`")
                if len(cl.added) > 20:
                    st.caption(f"… y {len(cl.added) - 20} más")
            if cl.removed:
                st.markdown(f"**{len(cl.removed)} eliminado(s):**")
                for pid in cl.removed[:20]:
                    st.markdown(f"- `{pid}`")
            if cl.changed:
                st.markdown(f"**{len(cl.changed)} con cambios:**")
                for pc in cl.changed[:20]:
                    lines = [
                        f"  - *{c.field}*: `{c.old or '—'}` → `{c.new or '—'}`"
                        for c in pc.changes
                    ]
                    st.markdown(f"- `{pc.process_id}`\n" + "\n".join(lines))
                if len(cl.changed) > 20:
                    st.caption(f"… y {len(cl.changed) - 20} más")


def _render_action_bar(df: pd.DataFrame, flagged_count: int, last_update: str) -> bool:
    """Render the "big button + last-update + stats" bar. Returns True iff button clicked."""
    c1, c2, c3 = st.columns([2, 2, 2])
    with c1:
        clicked = st.button(
            "ACTUALIZAR TODOS LOS PROCESOS",
            type="primary",
            use_container_width=True,
            help="Consulta datos.gov.co para cada fila del Excel y actualiza las columnas.",
        )
    with c2:
        flag_text = (
            f"<span style='color:{FGN_RED};font-weight:600'>{flagged_count} bandera(s) roja(s)</span>"
            if flagged_count
            else "<span style='color:#2A7A38'>sin banderas rojas</span>"
        )
        st.markdown(
            f"""
            <div class="action-bar">
                <div class="crm-stats">
                    <strong>{len(df)}</strong> procesos cargados ·
                    {flag_text}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            f"""
            <div class="action-bar">
                <div class="crm-stats">
                    Última actualización:<br>
                    <span class="last-update">{last_update or '(nunca)'}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    return clicked


def _render_flags(flagged: list) -> None:
    if not flagged:
        return
    rows = "".join(
        f"<li><strong>Fila {a.fila}</strong> · {a.process_id or '(sin id)'} — {(a.objeto or '')[:120]}</li>"
        for a in flagged[:8]
    )
    extra = (
        f"<li><em>… y {len(flagged) - 8} más</em></li>" if len(flagged) > 8 else ""
    )
    st.markdown(
        f"""
        <div class="flag-banner">
            <strong>Requieren revisión humana:</strong> la nota OBSERVACIONES afirma
            algo que SECOP II no respalda. Verificar contra archivo físico.
            <ul style="margin:6px 0 0 0">{rows}{extra}</ul>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_row_actions(path: Path) -> bool:
    """Add / delete process rows. Returns True if the workbook changed."""
    changed = False
    with st.expander("Agregar o eliminar procesos del CRM", expanded=False):
        c1, c2 = st.columns([4, 1])
        new_url = c1.text_input(
            "Pegar la URL del proceso SECOP II",
            key="add_url_input",
            placeholder="https://community.secop.gov.co/Public/Tendering/...",
            label_visibility="collapsed",
        )
        if c2.button("Agregar", use_container_width=True, type="primary"):
            if not new_url.strip():
                st.warning("Pega una URL primero.")
            else:
                try:
                    added_row = append_process_url(path, new_url.strip())
                    st.success(
                        f"Proceso agregado en la fila {added_row}. "
                        "Corre 'ACTUALIZAR TODOS LOS PROCESOS' arriba para llenar los campos."
                    )
                    changed = True
                except Exception as exc:
                    st.error(f"No pude agregar el proceso: {exc}")

        # Delete controls
        st.markdown(
            f"<div style='color:#666;font-size:0.85rem;margin-top:8px'>"
            f"Para eliminar, escribe el número de fila del Excel (columna izquierda de la tabla).</div>",
            unsafe_allow_html=True,
        )
        d1, d2, d3 = st.columns([2, 2, 1])
        del_row_num = d1.number_input(
            "Fila a eliminar",
            min_value=2,
            step=1,
            value=2,
            label_visibility="collapsed",
        )
        confirm = d2.checkbox(
            f"Confirmar borrado de la fila {int(del_row_num)}",
            key=f"confirm_del_{int(del_row_num)}",
        )
        if d3.button("Eliminar", use_container_width=True, disabled=not confirm):
            try:
                delete_row(path, int(del_row_num))
                st.success(f"Fila {int(del_row_num)} eliminada.")
                changed = True
            except Exception as exc:
                st.error(f"No pude eliminar: {exc}")

    if changed:
        _load_preview.clear()
    return changed


def _render_crm_table(df: pd.DataFrame) -> pd.DataFrame | None:
    """Render the main CRM table. Returns the row selected, or None."""
    if df.empty:
        st.warning(
            "El Excel no tiene procesos todavía. Usa el panel de arriba para "
            "agregar una URL del SECOP II."
        )
        return None

    # Pick the CRM columns that actually exist in this workbook; prefer
    # the Dra.'s original curated headers and fall back to the SECOP-enriched
    # ones. _resolve_crm_columns does case-insensitive substring matching
    # so odd trailing whitespace/accents in the original headers don't hide them.
    cols_present = _resolve_crm_columns(list(df.columns))
    if not cols_present:
        cols_present = list(df.columns)[:12]
    display_df = df[cols_present].copy()

    # Global quick search
    c1, c2 = st.columns([3, 1])
    with c1:
        search = st.text_input(
            "Buscar en la tabla (objeto, proveedor, proceso…)",
            "",
            label_visibility="collapsed",
            placeholder="Buscar en la tabla (objeto, proveedor, proceso…)",
        )
    with c2:
        show_all = st.toggle("Mostrar todas las columnas", value=False, help="Ver todos los campos, no solo los principales.")

    if show_all:
        display_df = df.copy()

    if search:
        mask = display_df.apply(
            lambda row: row.astype(str).str.contains(search, case=False, na=False).any(),
            axis=1,
        )
        display_df = display_df[mask]

    st.caption(f"{len(display_df)} procesos mostrados de {len(df)} totales.")
    return _render_interactive_table(display_df)


def _render_interactive_table(df: pd.DataFrame, *, kind: str = "contrato") -> pd.Series | None:
    """Excel-style table with native row selection.

    Per-column slicer pills are shown as additional filter rows above
    the table — gives the same effect as Excel's filter dropdown but
    without depending on AgGrid (which has Arrow LargeUtf8 issues).
    Click any row → detail panel below.
    """
    if df.empty:
        st.info("Sin resultados para los filtros actuales.")
        return None

    full_df = df.copy().reset_index(drop=True)
    for col in full_df.columns:
        if full_df[col].dtype == object:
            full_df[col] = full_df[col].apply(_stringify)

    compact_df, column_config = _build_compact_view(full_df, kind=kind)

    # Per-column slicers (chip-style). Show only for low-cardinality cols
    # where pills make sense; long-tail columns get the search bar instead.
    slicer_targets = [
        ("Estado", "estado_contrato" if kind == "contrato" else "fase"),
        ("Proveedor", "proveedor_adjudicado" if kind == "contrato" else "nombre_del_proveedor"),
    ]
    active_filters: dict[str, list[str]] = {}
    for label, source in slicer_targets:
        if source not in full_df.columns:
            continue
        unique_vals = sorted({
            str(v) for v in full_df[source].dropna()
            if str(v).strip() and str(v).lower() != "nan"
        })
        if not unique_vals or len(unique_vals) > 30:
            continue
        picked = _pills_filter(label, unique_vals, key=f"slicer_{kind}_{source}")
        if picked:
            active_filters[source] = picked

    # Apply slicer filters
    if active_filters:
        mask = pd.Series([True] * len(full_df), index=full_df.index)
        for source, picked in active_filters.items():
            mask &= full_df[source].astype(str).isin(picked)
        full_df = full_df[mask].reset_index(drop=True)
        compact_df = compact_df.loc[mask.values].reset_index(drop=True)
        st.caption(f"Filtrado: {len(full_df)} registros")

    if compact_df.empty:
        st.info("Sin resultados con los filtros actuales.")
        return None

    st.caption(
        "Haz click en cualquier fila para ver el detalle completo del proceso."
    )

    event = st.dataframe(
        compact_df,
        use_container_width=True,
        hide_index=True,
        height=520,
        column_config=column_config,
        on_select="rerun",
        selection_mode="single-row",
        key=f"crm_table_{kind}",
    )

    sel = getattr(event, "selection", None) or {}
    rows = sel.get("rows", []) if isinstance(sel, dict) else []
    if not rows:
        return None
    idx = rows[0]
    if idx >= len(full_df):
        return None
    return full_df.iloc[idx]


# ---------------------------------------------------------------------------
# Compact inventory view — NY legal-firm style
# ---------------------------------------------------------------------------
#  Widths chosen so the SUM fits comfortably in 1280px without horizontal
#  scroll on a normal monitor. Less is more — the SECOP link column was
#  removed; the URL lives in the per-process detail expander below.
#  8 columnas que caben sin scroll horizontal en monitor 1280px+.
#  Click en cualquier fila abre el detalle abajo (selection_mode nativo).
_CONTRACT_VIEW = [
    ("id_contrato",              "Código",         "text",   "small"),
    ("objeto_del_contrato",      "Objeto",         "text",   "large"),
    ("proveedor_adjudicado",     "Proveedor",      "text",   "medium"),
    ("valor_del_contrato",       "Valor (COP)",    "money",  "small"),
    ("fecha_de_firma",           "Firma",          "date",   "small"),
    ("estado_contrato",          "Estado",         "text",   "small"),
    # Nota auto-generada: si SECOP dice Modificado y/o hay días adicionados,
    # esto sintetiza el equivalente de la "OBSERVACIONES manual" de la Dra.
    ("_obs_modif",               "Notas",          "text",   "medium"),
    ("urlproceso",               "SECOP",          "link",   "small"),
]

_PROCESS_VIEW = [
    ("id_del_proceso",            "Código",         "text",   "small"),
    ("nombre_del_procedimiento",  "Objeto",         "text",   "large"),
    ("modalidad_de_contratacion", "Modalidad",      "text",   "medium"),
    ("valor_total_adjudicacion",  "Adjudicación",   "money",  "small"),
    ("fecha_de_publicacion_del",  "Publicación",    "date",   "small"),
    ("fase",                      "Fase",           "text",   "small"),
    ("urlproceso",                "SECOP",          "link",   "small"),
]


def _build_compact_view(df: pd.DataFrame, *, kind: str) -> tuple[pd.DataFrame, dict]:
    spec = _CONTRACT_VIEW if kind == "contrato" else _PROCESS_VIEW
    df = df.copy()

    # Derive the two highlights the Dra. cares about most (contratos):
    #   - _tiene_modificatorio: estado_contrato == "Modificado" | días adicionados > 0
    #   - _es_no_leg:           contrato firmado sin rastro de legalización
    if kind == "contrato":
        estado = df.get("estado_contrato", pd.Series(index=df.index, dtype=object)).astype(str)
        dias = pd.to_numeric(df.get("dias_adicionados", pd.Series(index=df.index, dtype=object)),
                             errors="coerce").fillna(0)
        df["_tiene_modificatorio"] = (
            estado.str.contains("Modificad", case=False, na=False) | (dias > 0)
        )
        # "NO LEG" proxy: contrato sin fecha de liquidación Y estado distinto de
        # cerrado/terminado. No es la verdad absoluta, pero es el marcador
        # que la Dra. escribe a mano cuando nota que falta la legalización.
        liquidacion = df.get("liquidaci_n", pd.Series(index=df.index, dtype=object)).astype(str)
        df["_es_no_leg"] = (
            ~estado.str.contains("Cerrado|Terminado|Liquidad", case=False, na=False)
            & (liquidacion.str.lower() != "si")
            & df.get("fecha_de_firma", pd.Series(index=df.index)).notna()
        )

        # "Notas" auto-generadas — equivalente al campo OBSERVACIONES manual
        # de la Dra., pero derivado de SECOP. Combina señales de modificatorios
        # y prórrogas en una sola línea legible.
        def _make_note(row) -> str:
            parts: list[str] = []
            est = str(row.get("estado_contrato") or "")
            if "Modificad" in est:
                parts.append("Modificado")
            d = pd.to_numeric(row.get("dias_adicionados"), errors="coerce")
            if d and d > 0:
                parts.append(f"+{int(d)} días")
            if row.get("_es_no_leg"):
                parts.append("Sin legalización")
            liq = str(row.get("liquidaci_n") or "").strip().lower()
            if liq == "si":
                parts.append("Liquidado")
            return " · ".join(parts) if parts else ""
        df["_obs_modif"] = df.apply(_make_note, axis=1)

    cols_present = [(s, lbl, t, w) for s, lbl, t, w in spec if s in df.columns]
    if not cols_present:
        return df, {}

    compact = df[[s for s, *_ in cols_present]].copy()
    compact.columns = [lbl for _, lbl, *_ in cols_present]

    column_config: dict = {}
    for source, label, kind_, width in cols_present:
        if kind_ == "money":
            compact[label] = pd.to_numeric(compact[label], errors="coerce")
            column_config[label] = st.column_config.NumberColumn(
                label, format="$ %,.0f", width=width,
            )
        elif kind_ == "date":
            compact[label] = compact[label].astype(str).str.slice(0, 10)
            column_config[label] = st.column_config.TextColumn(label, width=width)
        elif kind_ == "link":
            column_config[label] = st.column_config.LinkColumn(
                label, display_text="Abrir ↗", width=width,
            )
        elif kind_ == "flag":
            # Boolean badge — CheckboxColumn renders a tick/cross that the Dra.
            # can scan visually.
            compact[label] = compact[label].astype(bool)
            column_config[label] = st.column_config.CheckboxColumn(
                label, width=width, disabled=True,
            )
        else:
            column_config[label] = st.column_config.TextColumn(label, width=width)
    return compact, column_config


def _stringify(v):
    """Convert dict/list to a display string; leave other types alone."""
    if isinstance(v, dict):
        return v.get("url") or json.dumps(v, ensure_ascii=False)[:200]
    if isinstance(v, list):
        return " | ".join(str(x) for x in v)[:300]
    return v


def _render_detail(full_df: pd.DataFrame, selected_row) -> None:
    if selected_row is None:
        st.info("Haz clic en una fila de la tabla para ver todos los campos del proceso.")
        return

    pid = selected_row.get("ID identificado") if hasattr(selected_row, "get") else None
    title = pid or str(selected_row.iloc[0] if hasattr(selected_row, "iloc") else "Proceso")

    # Re-locate the full row in full_df so we have every column (AgGrid sometimes
    # drops columns that weren't visible in the view).
    source = selected_row
    if pid and "ID identificado" in full_df.columns:
        match = full_df[full_df["ID identificado"] == pid]
        if not match.empty:
            source = match.iloc[0]

    def _get(key: str, default=""):
        try:
            v = source.get(key) if hasattr(source, "get") else source[key]
        except Exception:
            v = default
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return default
        return v

    with st.expander(f"Detalle del proceso — {title}", expanded=True):
        # ---- Summary cards ----
        c1, c2, c3, c4 = st.columns(4)
        _kpi(c1, "Proveedor",
             str(_get("Contrato: Proveedor adjudicado") or _get("Proceso: Nombre proveedor adjudicado") or "—"))
        _kpi(c2, "Valor contrato", _fmt_money(_get("Contrato: Valor") or _get("Proceso: Valor adjudicación")))
        _kpi(c3, "Estado", str(_get("Contrato: Estado") or _get("Fase en SECOP") or "—"))
        _kpi(c4, "Fecha firma", str(_get("Contrato: Fecha firma") or "—"))

        # ---- Link back to SECOP ----
        link = _get("Link verificación API")
        if link:
            st.markdown(f"[Ver en datos.gov.co (verificación API)]({link})")

        # ---- Fields grouped by prefix ----
        keys = list(source.index) if hasattr(source, "index") else list(source.keys())
        groups = _group_by_prefix(keys)

        # Render groups in a fixed, reader-friendly order; unknown groups at the end
        order = ["Proceso", "Contrato", "Modificatorios", "Mods proceso",
                 "Garantías", "Pagos", "Seguimiento", "Docs", "Portal", "Audit", "Otros"]
        ordered_groups = [g for g in order if g in groups] + [g for g in groups if g not in order]

        for g in ordered_groups:
            fields = groups[g]
            non_empty = [
                (k, _get(k)) for k in fields
                if str(_get(k)).strip() and str(_get(k)).strip().lower() != "nan"
            ]
            if not non_empty:
                continue
            with st.expander(f"{g} ({len(non_empty)})", expanded=(g in ("Contrato", "Proceso"))):
                ca, cb = st.columns(2)
                for i, (k, v) in enumerate(non_empty):
                    col = ca if i % 2 == 0 else cb
                    col.markdown(f"**{_strip_prefix(k)}**")
                    col.write(_fmt_cell(v))

        # ---- Documents (clickable links) ----
        _render_documents(source)


def _group_by_prefix(keys):
    """Group column names by their "Prefix:" prefix. Columns without one go to 'Otros'."""
    groups: dict[str, list[str]] = {}
    for k in keys:
        if ":" in k and len(k.split(":", 1)[0]) <= 20:
            pfx = k.split(":", 1)[0].strip()
        else:
            pfx = "Otros"
        groups.setdefault(pfx, []).append(k)
    return groups


def _strip_prefix(k: str) -> str:
    if ":" in k and len(k.split(":", 1)[0]) <= 20:
        return k.split(":", 1)[1].strip()
    return k


def _fmt_money(v) -> str:
    if v in (None, "", "nan"):
        return "—"
    try:
        n = float(str(v).replace(",", ""))
        return f"${n:,.0f}"
    except (ValueError, TypeError):
        return str(v)


def _render_documents(source) -> None:
    """Render clickable document links and a lista-modificatorios block."""
    try:
        docs_mods = str(source.get("Docs: Lista modificatorios") or "")
        docs_legs = str(source.get("Docs: Lista legalizaciones") or "")
    except Exception:
        docs_mods = docs_legs = ""

    if not (docs_mods.strip() or docs_legs.strip()):
        return

    with st.expander("Documentos publicados en SECOP", expanded=False):
        if docs_mods.strip():
            st.markdown("**Modificatorios**")
            st.caption(docs_mods[:2000])
        if docs_legs.strip():
            st.markdown("**Legalizaciones**")
            st.caption(docs_legs[:2000])


def _fmt_cell(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M")
    s = str(v).strip()
    if not s or s.lower() == "nan":
        return "—"
    if s.startswith("http"):
        return f"[{s[:80]}…]({s})" if len(s) > 80 else f"[{s}]({s})"
    return s


def _render_sidebar(cfg: dict) -> tuple[Path | None, dict]:
    """No sidebar for the daily user. Everything lives on the main canvas.

    The Dra. opens this every day — the sidebar was pure noise. All the
    technical knobs (App Token, rate, URL column, portal flag) keep sane
    defaults and persist in ``%APPDATA%/SecopII/config.json``; someone
    from IT can tune the JSON directly if the need ever arises.
    """
    settings = {
        "app_token": (cfg.get("app_token") or "").strip() or None,
        "rate": float(cfg.get("rate", 2.0)),
        "url_column": (cfg.get("url_column") or "").strip() or None,
        "no_portal": bool(cfg.get("no_portal", True)),
    }
    return None, settings


def _generate_audit_report(path: Path) -> None:
    try:
        audits = audit_workbook(path)
    except Exception as exc:
        st.sidebar.error(f"No pude correr auditoría: {exc}")
        return
    stamp = datetime.now().strftime("AUDITORIA_%Y-%m-%d_%H%M.xlsx")
    out = path.parent / stamp
    info = build_audit_workbook(audits, out, excel_source=path.name)
    md_path = out.with_suffix(".md")
    md_path.write_text(render_markdown(audits), encoding="utf-8")
    st.sidebar.success(
        f"Reporte listo: {out.name} — {info.total_rows} filas, {info.needs_review} bandera(s) roja(s)."
    )
    try:
        st.sidebar.download_button(
            "Descargar .xlsx",
            data=out.read_bytes(),
            file_name=out.name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Update runner
# ---------------------------------------------------------------------------
def _run_update(path: Path, settings: dict) -> None:
    log_area = st.empty()
    progress_bar = st.progress(0.0, text="Iniciando…")
    log_lines: list[str] = []

    def on_progress(done: int, total: int, row) -> None:
        pct = done / max(total, 1)
        progress_bar.progress(
            min(pct, 1.0),
            text=f"{done} de {total} — fila {row.row}",
        )
        mark = "ok" if row.ok else "!!"
        detail = f"{row.process_id or row.url[:60]} -> {row.status}"
        log_lines.append(f"[{mark}] fila {row.row}: {detail}")
        log_area.code("\n".join(log_lines[-25:]))

    try:
        report = process_workbook(
            path,
            url_column=settings.get("url_column"),
            app_token=settings.get("app_token"),
            rate_per_second=settings.get("rate"),
            do_backup=True,
            progress=on_progress,
            mirror_portal=not settings.get("no_portal", True),
            generate_detalles=True,  # HTML drill-down por proceso
            apply_view=True,  # Vista Dra. (ocultar aux + freeze panes)
        )
    except Exception as exc:
        progress_bar.empty()
        st.error(f"Error durante la actualización: {exc}")
        return

    progress_bar.progress(1.0, text="Completado.")
    st.success(
        f"Excel actualizado. {report.total} procesos, "
        f"{report.with_modificatorio} con modificatorio, {report.errors} errores. "
        f"Backup: {report.backup_path.name if report.backup_path else 'no creado'}."
    )
    st.session_state["last_report"] = report.as_dict()
    _load_preview.clear()


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
def main() -> None:
    st.set_page_config(
        page_title=APP_TITLE,
        page_icon=None,
        layout="wide",
        initial_sidebar_state="collapsed",  # no sidebar visible by default
    )
    _render_banner()

    cfg = _load_config()
    _, settings = _render_sidebar(cfg)

    # The Dra. opens this every day. Single canvas, zero friction, all
    # data straight from SECOP II. No Excel, no sidebar, no config.
    _render_feab_full_view(settings, None)
    _render_footer()
    return

    # ---- Load data ----
    try:
        mtime = current_path.stat().st_mtime
        df = _load_preview(str(current_path), mtime)
    except Exception as exc:
        st.error(f"No pude leer el Excel: {exc}")
        _render_footer()
        return

    # ---- Audit (for flagged count and banner) ----
    try:
        _, _, flagged = _compute_audit(current_path)
    except Exception:
        flagged = []

    last_update = _last_update_global(df)

    # ---- Action bar ----
    clicked = _render_action_bar(df, len(flagged), last_update)
    if clicked:
        _run_update(current_path, settings)
        st.rerun()

    # ---- Changelog card (qué se movió desde la última corrida) ----
    _render_changelog_card(current_path)

    # ---- Red-flag banner ----
    _render_flags(flagged)

    # ---- Add / delete process rows ----
    if _render_row_actions(current_path):
        st.rerun()

    # ---- Main CRM table ----
    selected_row = _render_crm_table(df)

    # ---- Descarga Excel de la vista actual ----
    _render_download_excel(df, filename_base="mis_procesos")

    # ---- Detail for the selected row ----
    _render_detail(df, selected_row)

    # ---- Chat/pregunta rápida ----
    _render_process_chat(df)

    _render_footer()


def _render_feab_full_view(settings: dict, excel_path: Path | None) -> None:
    """Live dashboard of every FEAB process/contract published on SECOP II."""
    refresh_key = int(st.session_state.get("feab_refresh_key", 0))

    # One-row meta strip: refresh action + auto-refresh toggle + timestamp.
    # Intentionally understated — the real "news" is the movements section.
    meta_c1, meta_c2 = st.columns([1, 2])
    with meta_c1:
        if st.button("Refrescar desde SECOP", use_container_width=True):
            st.session_state["feab_refresh_key"] = refresh_key + 1
            _fetch_feab_snapshot_cached.clear()
            st.rerun()
    with meta_c2:
        auto = st.toggle(
            "Actualizar cada 10 minutos de forma automática",
            value=bool(st.session_state.get("feab_auto", False)),
        )
        st.session_state["feab_auto"] = auto

    if auto:
        try:
            from streamlit_autorefresh import st_autorefresh  # type: ignore[import-not-found]
            st_autorefresh(interval=10 * 60 * 1000, key="feab_auto_refresh")
        except Exception:
            pass

    try:
        snap = _fetch_feab_snapshot_cached(
            settings.get("app_token"), settings.get("rate") or 2.0, refresh_key
        )
    except Exception as exc:
        st.error(f"No pude consultar SECOP II: {exc}")
        return

    # ---- Movimientos desde la última revisión ---------------------------
    # That's the real pitch: not totals, change since last time.
    previous = load_previous_snapshot()
    changelog = compute_changelog(snap, previous)
    try:
        save_feab_snapshot(snap)  # save AFTER comparing, so next time has a baseline
    except Exception:
        pass

    _render_feab_movements(snap, changelog)

    # ---- Inventario completo (pestañas) --------------------------------
    st.markdown(
        f"<div style='margin-top:40px;padding-top:24px;border-top:1px solid {RULE};"
        f"font-family:\"Fraunces\",Georgia,serif;font-size:1.25rem;color:{INK};"
        f"letter-spacing:-0.01em;font-weight:500'>"
        f"Inventario completo</div>",
        unsafe_allow_html=True,
    )
    st.caption(f"Todos los registros del FEAB publicados en SECOP II — actualizado {snap.fetched_at}")

    tab_ctr, tab_proc = st.tabs(["Contratos", "Procesos"])
    with tab_ctr:
        _render_feab_contracts_table(snap.contracts, excel_path)
    with tab_proc:
        _render_feab_processes_table(snap.processes, excel_path)


def _render_feab_movements(snap, changelog) -> None:
    """Editorial 'movements since last time' card — the signal the Dra. wants."""
    if changelog.prev_at:
        sub = f"Desde tu última revisión · {changelog.prev_at}"
    else:
        sub = "Primera revisión. A partir de la próxima, verás qué cambió desde la anterior."

    st.markdown(
        f"""
        <div style="margin-top:8px;padding:32px 36px 28px 36px;background:{BG_WHITE};
                    border:1px solid {RULE};">
            <div style="font-size:0.7rem;letter-spacing:0.24em;text-transform:uppercase;
                        color:{FGN_RED};font-weight:600;margin-bottom:10px">
                Movimientos
            </div>
            <div style="font-family:'Fraunces',Georgia,serif;font-size:1.75rem;
                        color:{INK};letter-spacing:-0.015em;font-weight:500;line-height:1.2">
                {_movements_headline(changelog)}
            </div>
            <div style="color:{INK_SOFT};font-size:0.85rem;margin-top:10px;
                        letter-spacing:0.04em">{sub}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Breakdown items as a horizontal list — only those with data
    items: list[tuple[str, int]] = []
    if changelog.new_processes:
        items.append(("Procesos nuevos", len(changelog.new_processes)))
    if changelog.new_contracts:
        items.append(("Contratos firmados", len(changelog.new_contracts)))
    if changelog.adjudicated_now:
        items.append(("Adjudicaciones", len(changelog.adjudicated_now)))
    if changelog.phase_changes:
        items.append(("Cambios de fase", len(changelog.phase_changes)))
    if changelog.contract_state_changes:
        items.append(("Cambios de estado", len(changelog.contract_state_changes)))

    if items:
        cols = st.columns(len(items))
        for col, (label, count) in zip(cols, items):
            col.markdown(
                f"""
                <div style="padding:18px 4px;border-top:2px solid {FGN_RED};
                            margin-top:4px">
                    <div style="font-family:'Fraunces',Georgia,serif;font-size:2rem;
                                color:{INK};font-weight:500;line-height:1">{count}</div>
                    <div style="color:{INK_SOFT};font-size:0.72rem;
                                letter-spacing:0.12em;text-transform:uppercase;
                                margin-top:8px;font-weight:500">{label}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        if changelog.total > 0:
            with st.expander("Ver el detalle de cada movimiento", expanded=False):
                if changelog.new_processes:
                    st.markdown(f"**{len(changelog.new_processes)} procesos nuevos**")
                    for pid in changelog.new_processes[:20]:
                        st.markdown(f"- `{pid}`")
                if changelog.new_contracts:
                    st.markdown(f"**{len(changelog.new_contracts)} contratos firmados**")
                    for cid in changelog.new_contracts[:20]:
                        st.markdown(f"- `{cid}`")
                if changelog.phase_changes:
                    st.markdown(f"**{len(changelog.phase_changes)} cambios de fase**")
                    for pid, old, new in changelog.phase_changes[:20]:
                        st.markdown(f"- `{pid}`: *{old}* → *{new}*")
                if changelog.contract_state_changes:
                    st.markdown(f"**{len(changelog.contract_state_changes)} cambios de estado**")
                    for cid, old, new in changelog.contract_state_changes[:20]:
                        st.markdown(f"- `{cid}`: *{old}* → *{new}*")


def _movements_headline(cl) -> str:
    if not cl.prev_at:
        return "Bienvenida. Abajo está el inventario completo del FEAB en SECOP II."
    if cl.total == 0:
        return "Sin novedades desde la última vez."
    parts = []
    if cl.new_processes:
        parts.append(f"{len(cl.new_processes)} proceso{'s' if len(cl.new_processes) != 1 else ''} nuevo{'s' if len(cl.new_processes) != 1 else ''}")
    if cl.new_contracts:
        parts.append(f"{len(cl.new_contracts)} contrato{'s' if len(cl.new_contracts) != 1 else ''} firmado{'s' if len(cl.new_contracts) != 1 else ''}")
    if cl.phase_changes:
        parts.append(f"{len(cl.phase_changes)} cambio{'s' if len(cl.phase_changes) != 1 else ''} de fase")
    if cl.contract_state_changes:
        parts.append(f"{len(cl.contract_state_changes)} cambio{'s' if len(cl.contract_state_changes) != 1 else ''} de estado")
    if not parts:
        return "Movimientos registrados."
    if len(parts) == 1:
        return parts[0] + "."
    if len(parts) == 2:
        return " y ".join(parts) + "."
    return ", ".join(parts[:-1]) + " y " + parts[-1] + "."


def _render_feab_contracts_table(df: pd.DataFrame, excel_path: Path | None) -> None:
    if df.empty:
        st.info("No se encontraron contratos FEAB en SECOP II.")
        return

    anios = _extract_years(df, "fecha_de_firma")
    estados = sorted({str(x) for x in df.get("estado_contrato", []).dropna() if str(x).strip()})
    modalidades = sorted({str(x) for x in df.get("modalidad_de_contratacion", []).dropna() if str(x).strip()})

    search = st.text_input(
        "Buscar contrato",
        "",
        label_visibility="collapsed",
        placeholder="Buscar — proveedor, objeto, identificador…",
    )

    # Quick highlights — what the Dra. destaca a mano en OBSERVACIONES
    q1, q2, q3 = st.columns([1, 1, 4])
    only_mod = q1.toggle("Solo modificados", value=False, key="ctr_only_mod")
    only_noleg = q2.toggle("Solo sin legalización", value=False, key="ctr_only_noleg")

    sel_anio = _pills_filter("Año de firma", anios, key="ctr_anio")
    sel_estado = _pills_filter("Estado del contrato", estados, key="ctr_estado")
    sel_modalidad = _pills_filter("Modalidad de contratación", modalidades, key="ctr_modalidad")

    filtered = df
    if search:
        mask = filtered.apply(
            lambda row: row.astype(str).str.contains(search, case=False, na=False).any(),
            axis=1,
        )
        filtered = filtered[mask]
    if sel_anio and "fecha_de_firma" in filtered.columns:
        year_str = filtered["fecha_de_firma"].astype(str).str[:4]
        filtered = filtered[year_str.isin(sel_anio)]
    if sel_estado and "estado_contrato" in filtered.columns:
        filtered = filtered[filtered["estado_contrato"].isin(sel_estado)]
    if sel_modalidad and "modalidad_de_contratacion" in filtered.columns:
        filtered = filtered[filtered["modalidad_de_contratacion"].isin(sel_modalidad)]

    # Quick highlights — aplicar las mismas derivaciones que la vista de
    # tabla para poder filtrar por estos dos conceptos antes de renderizar.
    if only_mod:
        estado = filtered.get("estado_contrato", pd.Series(index=filtered.index, dtype=object)).astype(str)
        dias = pd.to_numeric(filtered.get("dias_adicionados", 0), errors="coerce").fillna(0)
        filtered = filtered[estado.str.contains("Modificad", case=False, na=False) | (dias > 0)]
    if only_noleg:
        estado = filtered.get("estado_contrato", pd.Series(index=filtered.index, dtype=object)).astype(str)
        liq = filtered.get("liquidaci_n", pd.Series(index=filtered.index, dtype=object)).astype(str)
        firmed = filtered.get("fecha_de_firma", pd.Series(index=filtered.index)).notna()
        filtered = filtered[
            ~estado.str.contains("Cerrado|Terminado|Liquidad", case=False, na=False)
            & (liq.str.lower() != "si") & firmed
        ]

    st.caption(f"{len(filtered)} contratos · {len(df)} totales")
    _render_download_excel(filtered, filename_base="contratos_feab")

    selected = _render_interactive_table(filtered, kind="contrato")
    if selected is not None:
        _render_feab_detail(selected, excel_path, kind="contrato")


def _render_feab_processes_table(df: pd.DataFrame, excel_path: Path | None) -> None:
    if df.empty:
        st.info("No se encontraron procesos FEAB en SECOP II.")
        return

    anios = _extract_years(df, "fecha_de_publicacion_del")
    fases = sorted({str(x) for x in df.get("fase", []).dropna() if str(x).strip()})

    search = st.text_input(
        "Buscar proceso",
        "",
        label_visibility="collapsed",
        placeholder="Buscar — objeto, identificador, proveedor…",
    )

    sel_anio = _pills_filter("Año de publicación", anios, key="proc_anio")
    sel_fase = _pills_filter("Fase", fases, key="proc_fase")
    sel_adj = _pills_filter("Adjudicado", ["Si", "No"], key="proc_adj")

    filtered = df
    if search:
        mask = filtered.apply(
            lambda row: row.astype(str).str.contains(search, case=False, na=False).any(),
            axis=1,
        )
        filtered = filtered[mask]
    if sel_anio and "fecha_de_publicacion_del" in filtered.columns:
        year_str = filtered["fecha_de_publicacion_del"].astype(str).str[:4]
        filtered = filtered[year_str.isin(sel_anio)]
    if sel_fase and "fase" in filtered.columns:
        filtered = filtered[filtered["fase"].isin(sel_fase)]
    if sel_adj and "adjudicado" in filtered.columns:
        filtered = filtered[filtered["adjudicado"].isin(sel_adj)]

    st.caption(f"{len(filtered)} procesos · {len(df)} totales")
    _render_download_excel(filtered, filename_base="procesos_feab")

    selected = _render_interactive_table(filtered, kind="proceso")
    if selected is not None:
        _render_feab_detail(selected, excel_path, kind="proceso")


def _pills_filter(label: str, options: list[str], *, key: str) -> list[str]:
    """Excel-slicer-style filter: all options visible as clickable pills.

    Multi-select mode — click pills to toggle. Empty selection means "all".
    Falls back to st.multiselect for older Streamlit versions.
    """
    if not options:
        return []
    st.markdown(
        f"<div style='font-size:0.7rem;letter-spacing:0.2em;text-transform:uppercase;"
        f"color:{INK_SOFT};font-weight:600;margin:14px 0 6px 0'>{label}</div>",
        unsafe_allow_html=True,
    )
    pills_fn = getattr(st, "pills", None)
    if pills_fn is not None:
        result = pills_fn(
            label, options=options,
            selection_mode="multi", default=None,
            label_visibility="collapsed", key=key,
        )
        return list(result) if result else []
    return st.multiselect(
        label, options=options, default=[],
        label_visibility="collapsed",
        placeholder="Todos — selecciona uno o varios",
        key=key,
    )


def _extract_years(df: pd.DataFrame, column: str) -> list[str]:
    """Return distinct 4-digit years found in ``column``, sorted desc."""
    if column not in df.columns:
        return []
    years: set[str] = set()
    for v in df[column].dropna():
        s = str(v)
        if len(s) >= 4 and s[:4].isdigit():
            years.add(s[:4])
    return sorted(years, reverse=True)


def _render_feab_detail(row, excel_path: Path | None, *, kind: str) -> None:
    """Show full fields for a FEAB row in Excel-style tables, by section.

    Replaces the prior 2-column key/value list (which exposed raw SECOP
    field names like 'objeto_del_contrato'). Each section becomes a
    real st.dataframe so the user gets Excel features: sort, filter,
    select, autosize, copy.
    """
    url = ""
    for key in ("urlproceso", "url"):
        try:
            u = row.get(key) if hasattr(row, "get") else row[key]
        except Exception:
            u = None
        if u:
            url = str(u)
            break
    title = str(
        (row.get("id_contrato") if hasattr(row, "get") else None)
        or (row.get("id_del_proceso") if hasattr(row, "get") else None)
        or f"{kind} sin ID"
    )

    with st.expander(f"Detalle: {title}", expanded=True):
        c1, c2 = st.columns([3, 1])
        if url and c1:
            c1.markdown(f"[Abrir en datos.gov.co]({url})")
        if url and excel_path and c2.button(
            f"Agregar al CRM", key=f"add_{title}", use_container_width=True
        ):
            try:
                added = append_process_url(excel_path, url)
                st.success(f"Agregado al Excel en la fila {added}.")
                _load_preview.clear()
            except Exception as exc:
                st.error(f"No pude agregar: {exc}")

        # Render each section as its own Excel-style table.
        for section_label, section_fields in _DETAIL_SECTIONS:
            section_rows = []
            for raw_key, friendly_label in section_fields:
                try:
                    v = row[raw_key] if hasattr(row, "__getitem__") else row.get(raw_key)
                except Exception:
                    v = None
                if v is None or str(v).strip() == "" or str(v).lower() == "nan":
                    continue
                section_rows.append({"Campo": friendly_label, "Valor": _fmt_cell(v)})
            if not section_rows:
                continue
            st.markdown(
                f"<div style='font-size:0.7rem;letter-spacing:0.2em;"
                f"text-transform:uppercase;color:{INK_SOFT};font-weight:600;"
                f"margin:18px 0 6px 0'>{section_label}</div>",
                unsafe_allow_html=True,
            )
            sec_df = pd.DataFrame(section_rows)
            st.dataframe(
                sec_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Campo": st.column_config.TextColumn("Campo", width="medium"),
                    "Valor": st.column_config.TextColumn("Valor", width="large"),
                },
                row_height=32,
            )


# Friendly labels for the per-process detail panel. Grouped by section
# so the user sees a natural reading order: identity → dates → money →
# contractor → guarantees → modificatorios. Raw SECOP field names stay
# in the code; the user sees only Spanish labels.
_DETAIL_SECTIONS: list[tuple[str, list[tuple[str, str]]]] = [
    ("Identificación", [
        ("id_contrato", "Código del contrato"),
        ("referencia_del_contrato", "Referencia FEAB"),
        ("id_del_proceso", "Código del proceso"),
        ("proceso_de_compra", "Portafolio de compra"),
        ("nombre_entidad", "Entidad contratante"),
        ("nit_entidad", "NIT entidad"),
        ("objeto_del_contrato", "Objeto del contrato"),
        ("descripcion_del_proceso", "Descripción del proceso"),
        ("tipo_de_contrato", "Tipo de contrato"),
        ("modalidad_de_contratacion", "Modalidad"),
        ("justificacion_modalidad_de", "Justificación modalidad"),
    ]),
    ("Estado y fechas", [
        ("estado_contrato", "Estado del contrato"),
        ("fase", "Fase"),
        ("fecha_de_firma", "Fecha de firma"),
        ("fecha_de_inicio_del_contrato", "Fecha de inicio"),
        ("fecha_de_fin_del_contrato", "Fecha de terminación"),
        ("fecha_inicio_liquidacion", "Inicio liquidación"),
        ("fecha_fin_liquidacion", "Fin liquidación"),
        ("liquidaci_n", "¿Requiere liquidación?"),
        ("duraci_n_del_contrato", "Duración"),
        ("dias_adicionados", "Días adicionados (prórrogas)"),
    ]),
    ("Valores", [
        ("valor_del_contrato", "Valor inicial"),
        ("valor_facturado", "Valor facturado"),
        ("valor_pagado", "Valor pagado"),
        ("valor_pendiente_de_pago", "Valor pendiente de pago"),
        ("valor_pendiente_de_ejecucion", "Pendiente de ejecución"),
        ("valor_de_pago_adelantado", "Valor anticipo"),
        ("origen_de_los_recursos", "Origen recursos"),
        ("destino_gasto", "Destino del gasto"),
    ]),
    ("Contratista", [
        ("proveedor_adjudicado", "Nombre / Razón social"),
        ("tipodocproveedor", "Tipo identificación"),
        ("documento_proveedor", "Número identificación"),
        ("nombre_representante_legal", "Representante legal"),
        ("identificaci_n_representante_legal", "ID representante"),
        ("domicilio_representante_legal", "Domicilio"),
        ("departamento", "Departamento"),
        ("ciudad", "Ciudad"),
        ("es_pyme", "¿Es PYME?"),
        ("es_grupo", "¿Es grupo?"),
    ]),
    ("Supervisión y orden", [
        ("nombre_supervisor", "Supervisor"),
        ("n_mero_de_documento_supervisor", "ID supervisor"),
        ("nombre_ordenador_del_gasto", "Ordenador del gasto"),
        ("n_mero_de_documento_ordenador_del_gasto", "ID ordenador"),
        ("nombre_ordenador_de_pago", "Ordenador de pago"),
    ]),
    ("Modificatorios y prórrogas", [
        ("estado_contrato", "Estado actual"),
        ("dias_adicionados", "Días adicionados"),
        ("el_contrato_puede_ser_prorrogado", "¿Puede prorrogarse?"),
        ("fecha_de_notificaci_n_de_prorrogaci_n", "Fecha notificación prórroga"),
    ]),
    ("Otros", [
        ("rama", "Rama"),
        ("orden", "Orden"),
        ("sector", "Sector"),
        ("entidad_centralizada", "Entidad centralizada"),
        ("habilita_pago_adelantado", "¿Anticipo habilitado?"),
        ("reversion", "¿Reversión?"),
        ("obligaci_n_ambiental", "Obligación ambiental"),
        ("obligaciones_postconsumo", "Obligaciones post-consumo"),
        ("espostconflicto", "Post-conflicto"),
        ("documentos_tipo", "Documentos tipo"),
        ("ultima_actualizacion", "Última actualización SECOP"),
    ]),
]


def _render_download_excel(df: pd.DataFrame, *, filename_base: str) -> None:
    """Button to download the current DataFrame as Excel (all columns)."""
    if df.empty:
        return
    try:
        import io
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
            df.to_excel(writer, index=False, sheet_name="Procesos")
        buf.seek(0)
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
        st.download_button(
            "Descargar esta vista en Excel",
            data=buf.getvalue(),
            file_name=f"{filename_base}_{stamp}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception as exc:
        st.caption(f"(No pude generar el Excel: {exc})")


def _render_process_chat(df: pd.DataFrame) -> None:
    """Lightweight chat. The Dra. writes '¿cómo va CO1.PPI.X?' or a free-text query
    and the app answers from the loaded Excel — no LLM, deterministic lookup."""
    if df.empty:
        return
    with st.expander("Preguntar por un proceso", expanded=False):
        st.caption(
            "Escribe un ID (CO1.PPI.*, CO1.NTC.*, CO1.PCCNTR.*), el nombre del proveedor, "
            "el número de contrato o palabras del objeto. Respondo con los datos del Excel."
        )
        q = st.chat_input("¿Cómo va este proceso?") if hasattr(st, "chat_input") else st.text_input(
            "Pregunta", key="chat_q"
        )
        if not q:
            return

        with st.chat_message("user") if hasattr(st, "chat_message") else st.container():
            st.markdown(q)

        answer = _answer_about_processes(q, df)

        with st.chat_message("assistant") if hasattr(st, "chat_message") else st.container():
            st.markdown(answer, unsafe_allow_html=True)


def _answer_about_processes(query: str, df: pd.DataFrame) -> str:
    """Deterministic lookup: substring match across every text column."""
    q = query.strip()
    if not q:
        return "Escribe un ID o unas palabras clave."

    # Build a searchable representation: each row as lowercase concatenated string.
    searchable = df.astype(str).apply(lambda r: " | ".join(r.values).lower(), axis=1)
    mask = searchable.str.contains(q.lower(), regex=False, na=False)
    matches = df[mask]
    if matches.empty:
        return f"No encontré nada que coincida con **{q}** en los {len(df)} procesos cargados."

    if len(matches) > 5:
        return (
            f"Encontré **{len(matches)} procesos** que coinciden con *{q}*. "
            "Afina la búsqueda (prueba con el ID completo o una frase más específica)."
        )

    parts: list[str] = [f"Encontré **{len(matches)} coincidencia(s)** para *{q}*:"]
    for _, row in matches.iterrows():
        parts.append("")
        pid = row.get("ID identificado") or row.get("2. N�MERO DE CONTRATO") or "(sin id)"
        objeto = (
            row.get("Objeto en SECOP")
            or row.get("4. OBJETO                                                                                              ")
            or ""
        )
        estado = row.get("Contrato: Estado") or row.get("Fase en SECOP") or "—"
        valor = row.get("Contrato: Valor") or row.get("Proceso: Valor adjudicación") or "—"
        mod = row.get("¿Hubo modificatorio?") or "—"
        last_upd = row.get(LAST_UPDATE_COLUMN) or "—"
        parts.append(f"**{pid}**")
        parts.append(f"- Objeto: {str(objeto)[:200]}")
        parts.append(f"- Estado / fase: {estado}")
        parts.append(f"- Valor: {valor}")
        parts.append(f"- Modificatorio: {mod}")
        parts.append(f"- Última actualización: {last_upd}")
    return "\n".join(parts)


def _render_empty_state() -> None:
    """Large, warm empty state — no jargon, directs to the sidebar upload."""
    st.markdown(
        f"""
        <div style="padding:60px 48px;background:{BG_SURFACE};border:1px solid {RULE};text-align:center;">
            <div style="font-size:0.72rem;letter-spacing:0.22em;text-transform:uppercase;color:{FGN_RED};font-weight:600;margin-bottom:16px;">
                Paso 1 de 1
            </div>
            <div style="font-family:'Fraunces',Georgia,serif;font-size:1.65rem;color:{INK};margin-bottom:14px;font-weight:500;letter-spacing:-0.015em;">
                Sube tu Excel de procesos para comenzar
            </div>
            <div style="color:{INK_SOFT};font-size:0.95rem;max-width:540px;margin:0 auto;line-height:1.55;">
                Arrástralo al panel izquierdo (botón <em>Upload</em>). La primera vez se demora unos segundos;
                la próxima vez que abras esta aplicación, te recordará el archivo que usaste.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_footer() -> None:
    st.markdown(
        f"""
        <div class="sec-footer">
            {APP_TITLE} &nbsp;·&nbsp;
            Datos oficiales: <code>datos.gov.co / SECOP II</code> &nbsp;·&nbsp;
            {datetime.now().strftime("%Y-%m-%d")}
        </div>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":  # pragma: no cover
    main()
