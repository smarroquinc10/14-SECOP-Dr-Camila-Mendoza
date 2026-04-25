"""Build a professional-looking audit Excel using xlsxwriter.

The user (the Dra.) needs an artifact she can hand to her bosses or to
compliance — three sheets, autofilter, conditional formatting, all the
"this looks like an auditor wrote it" affordances.

Why xlsxwriter and not openpyxl: writing rich formats (banded tables +
conditional formatting + frozen panes + autofilter) from scratch is
much cleaner with xlsxwriter; openpyxl is better at *editing* a workbook
in-place but heavier when *creating* one.

Color palette mirrors the FGN house style:
    deep red   #A50034   institutional accent
    gold       #C9A227   secondary accent
    navy       #1A2B5F   header text
    bg-light   #F4F2EE   alternating rows
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import xlsxwriter

from secop_ii.audit import (
    VERDICT_AGREE_NO,
    VERDICT_AGREE_SI,
    VERDICT_API_LAG,
    VERDICT_DOCS_LIDERA,
    VERDICT_NA,
    VERDICT_NOTA_FALTA,
    VERDICT_NOTE_ONLY,
    RowAudit,
)

FGN_RED = "#A50034"
FGN_GOLD = "#C9A227"
FGN_NAVY = "#1A2B5F"
ROW_BG_ALT = "#F8F6F2"
HEADER_TEXT = "#FFFFFF"

# Mapping verdict → background tint for the verdict column. We bias toward
# the rule "the only red row is the one that needs human review" so the
# Dra. spots it immediately.
_VERDICT_TINT = {
    VERDICT_AGREE_NO: "#E5F4EA",       # green
    VERDICT_AGREE_SI: "#E5F4EA",       # green
    VERDICT_API_LAG: "#FFF7DD",        # yellow
    VERDICT_DOCS_LIDERA: "#FFF7DD",    # yellow
    VERDICT_NOTA_FALTA: "#FFE8CC",     # orange
    VERDICT_NOTE_ONLY: "#F8C9C9",      # red
    VERDICT_NA: "#EDEDED",             # gray
}


@dataclass
class ReportInfo:
    excel_source: str
    generated_at: datetime
    total_rows: int
    needs_review: int


def build_audit_workbook(
    audits: Iterable[RowAudit],
    output_path: Path | str,
    *,
    excel_source: str = "",
) -> ReportInfo:
    """Write a 3-sheet professional auditing Excel and return its metadata."""
    output_path = Path(output_path)
    audits = list(audits)
    info = ReportInfo(
        excel_source=excel_source,
        generated_at=datetime.now(),
        total_rows=len(audits),
        needs_review=sum(1 for a in audits if a.needs_review),
    )

    wb = xlsxwriter.Workbook(str(output_path))
    fmt = _build_formats(wb)
    _sheet_resumen(wb, fmt, audits, info)
    _sheet_detalle(wb, fmt, audits, info)
    _sheet_banderas_rojas(wb, fmt, audits, info)
    wb.close()
    return info


# ---------------------------------------------------------------------------
# Format library
# ---------------------------------------------------------------------------
def _build_formats(wb: xlsxwriter.Workbook) -> dict[str, object]:
    base = {"font_name": "Calibri", "font_size": 10}
    return {
        "title": wb.add_format({**base, "font_size": 18, "bold": True, "color": FGN_NAVY}),
        "subtitle": wb.add_format({**base, "italic": True, "color": "#666666"}),
        "kpi_label": wb.add_format({**base, "bold": True, "color": FGN_NAVY}),
        "kpi_value": wb.add_format({**base, "font_size": 14, "bold": True, "color": FGN_RED}),
        "header": wb.add_format({
            **base, "bold": True, "color": HEADER_TEXT, "bg_color": FGN_NAVY,
            "border": 1, "border_color": FGN_NAVY, "align": "left", "valign": "vcenter",
        }),
        "cell": wb.add_format({**base, "valign": "top", "text_wrap": True}),
        "cell_alt": wb.add_format({**base, "valign": "top", "text_wrap": True, "bg_color": ROW_BG_ALT}),
        "cell_mono": wb.add_format({**base, "font_name": "Consolas", "valign": "top"}),
        "cell_num": wb.add_format({**base, "valign": "top", "num_format": "#,##0"}),
        "cell_link": wb.add_format({**base, "color": FGN_NAVY, "underline": 1}),
        "footer": wb.add_format({**base, "italic": True, "color": "#888888", "font_size": 9}),
        "section": wb.add_format({
            **base, "bold": True, "font_size": 12, "color": HEADER_TEXT,
            "bg_color": FGN_RED, "align": "left",
        }),
        "v_green": wb.add_format({**base, "bg_color": _VERDICT_TINT[VERDICT_AGREE_NO]}),
        "v_yellow": wb.add_format({**base, "bg_color": _VERDICT_TINT[VERDICT_API_LAG]}),
        "v_orange": wb.add_format({**base, "bg_color": _VERDICT_TINT[VERDICT_NOTA_FALTA]}),
        "v_red": wb.add_format({**base, "bg_color": _VERDICT_TINT[VERDICT_NOTE_ONLY], "bold": True}),
        "v_gray": wb.add_format({**base, "bg_color": _VERDICT_TINT[VERDICT_NA]}),
    }


# ---------------------------------------------------------------------------
# Sheet 1 — Resumen
# ---------------------------------------------------------------------------
def _sheet_resumen(wb, fmt, audits: list[RowAudit], info: ReportInfo) -> None:
    ws = wb.add_worksheet("Resumen")
    ws.hide_gridlines(2)
    ws.set_column("A:A", 36)
    ws.set_column("B:B", 18)
    ws.set_column("C:C", 28)

    ws.write("A1", "Auditoría SECOP II — Excel FEAB", fmt["title"])
    ws.write("A2", "Cruce automático: nota OBSERVACIONES vs API datos.gov.co vs documentos publicados", fmt["subtitle"])

    ws.write("A4", "Archivo origen", fmt["kpi_label"])
    ws.write("B4", info.excel_source, fmt["cell_mono"])
    ws.write("A5", "Generado", fmt["kpi_label"])
    ws.write("B5", info.generated_at.strftime("%Y-%m-%d %H:%M"), fmt["cell_mono"])
    ws.write("A6", "Total filas analizadas", fmt["kpi_label"])
    ws.write_number("B6", info.total_rows, fmt["kpi_value"])
    ws.write("A7", "Filas que requieren revisión humana", fmt["kpi_label"])
    ws.write_number("B7", info.needs_review, fmt["kpi_value"])

    # Verdict breakdown
    ws.merge_range("A9:C9", "Distribución por veredicto", fmt["section"])
    ws.write_row("A10", ["Veredicto", "# Filas", "¿Requiere revisión?"], fmt["header"])

    by_verdict: dict[str, int] = {}
    for a in audits:
        by_verdict[a.verdict] = by_verdict.get(a.verdict, 0) + 1

    row = 10
    for verdict, count in sorted(by_verdict.items(), key=lambda kv: -kv[1]):
        cell_fmt = _verdict_cell_fmt(fmt, verdict)
        ws.write(row, 0, verdict, cell_fmt)
        ws.write_number(row, 1, count, cell_fmt)
        ws.write(row, 2, "Sí" if verdict == VERDICT_NOTE_ONLY else "no", cell_fmt)
        row += 1

    # Legend
    ws.merge_range(row + 1, 0, row + 1, 2, "Leyenda de veredictos", fmt["section"])
    legend = [
        (VERDICT_AGREE_NO, "API y nota concuerdan en que no hubo modificatorio"),
        (VERDICT_AGREE_SI, "API + docs + nota concuerdan en sí"),
        (VERDICT_API_LAG, "Docs publicados confirman; la API normalizada laguea (no es bug)"),
        (VERDICT_NOTA_FALTA, "SECOP confirma sí; la nota humana se quedó atrás"),
        (VERDICT_NOTE_ONLY, "La nota afirma sí pero SECOP no lo confirma — REVISIÓN HUMANA"),
        (VERDICT_DOCS_LIDERA, "Docs publicados sí, API formal aún no — probable lag"),
        (VERDICT_NA, "URL inválida o no se encontró en SECOP"),
    ]
    for i, (v, desc) in enumerate(legend, start=row + 2):
        ws.write(i, 0, v, _verdict_cell_fmt(fmt, v))
        ws.merge_range(i, 1, i, 2, desc, fmt["cell"])

    ws.write(row + 2 + len(legend) + 1, 0,
             "Generado por SECOP II CRM — todos los datos son verificables clic a clic en datos.gov.co",
             fmt["footer"])


# ---------------------------------------------------------------------------
# Sheet 2 — Detalle
# ---------------------------------------------------------------------------
_DETAIL_HEADERS = (
    "Fila", "Proceso", "Objeto", "Nota OBS dice mod?", "API dice mod?",
    "Docs # mods", "Docs # legal", "Veredicto", "Texto OBSERVACIONES",
    "Lista mods (docs)", "Lista legal (docs)",
)
_DETAIL_WIDTHS = (8, 22, 60, 16, 14, 12, 12, 28, 60, 60, 60)


def _sheet_detalle(wb, fmt, audits: list[RowAudit], info: ReportInfo) -> None:
    ws = wb.add_worksheet("Detalle")
    ws.hide_gridlines(2)
    for i, w in enumerate(_DETAIL_WIDTHS):
        ws.set_column(i, i, w)
    ws.set_row(0, 24)
    ws.write_row(0, 0, _DETAIL_HEADERS, fmt["header"])
    ws.freeze_panes(1, 2)
    ws.autofilter(0, 0, max(1, len(audits)), len(_DETAIL_HEADERS) - 1)

    for r, a in enumerate(audits, start=1):
        cell_fmt = fmt["cell_alt"] if r % 2 == 0 else fmt["cell"]
        verdict_fmt = _verdict_cell_fmt(fmt, a.verdict)
        ws.write_number(r, 0, a.fila, cell_fmt)
        ws.write(r, 1, a.process_id or "", fmt["cell_mono"])
        ws.write(r, 2, a.objeto, cell_fmt)
        ws.write(r, 3, "Sí" if a.note_says_modif else "No", cell_fmt)
        ws.write(r, 4, f"{'Sí' if a.api_says_modif else 'No'} ({a.api_count})", cell_fmt)
        ws.write_number(r, 5, a.docs_mod_count, cell_fmt)
        ws.write_number(r, 6, a.docs_leg_count, cell_fmt)
        ws.write(r, 7, a.verdict, verdict_fmt)
        ws.write(r, 8, a.note_text, cell_fmt)
        ws.write(r, 9, a.docs_mod_list, cell_fmt)
        ws.write(r, 10, a.docs_leg_list, cell_fmt)


# ---------------------------------------------------------------------------
# Sheet 3 — Banderas rojas
# ---------------------------------------------------------------------------
def _sheet_banderas_rojas(wb, fmt, audits: list[RowAudit], info: ReportInfo) -> None:
    ws = wb.add_worksheet("Banderas Rojas")
    ws.hide_gridlines(2)
    ws.set_column("A:A", 8)
    ws.set_column("B:B", 22)
    ws.set_column("C:C", 70)
    ws.set_column("D:D", 60)

    flagged = [a for a in audits if a.needs_review]

    ws.write("A1", "Casos que requieren revisión humana", fmt["title"])
    ws.write("A2",
             f"{len(flagged)} fila(s) donde la nota afirma un modificatorio que SECOP no respalda. "
             "Cada caso debe verificarse contra el archivo físico antes de cualquier informe.",
             fmt["subtitle"])

    ws.write_row(3, 0, ["Fila", "Proceso", "Objeto", "Acción sugerida"], fmt["header"])
    for r, a in enumerate(flagged, start=4):
        ws.write_number(r, 0, a.fila, fmt["v_red"])
        ws.write(r, 1, a.process_id or "", fmt["cell_mono"])
        ws.write(r, 2, a.objeto, fmt["cell"])
        ws.write(r, 3,
                 "Verificar archivo físico. Si no aparece modificatorio firmado, retirar la mención de la "
                 "columna OBSERVACIONES o documentar bajo qué expediente se firmó.",
                 fmt["cell"])

    # Detail block per flagged row
    row = 4 + len(flagged) + 2
    for a in flagged:
        ws.merge_range(row, 0, row, 3, f"Fila {a.fila} — {a.process_id}", fmt["section"])
        row += 1
        ws.write(row, 0, "Objeto", fmt["kpi_label"])
        ws.merge_range(row, 1, row, 3, a.objeto, fmt["cell"])
        row += 1
        ws.write(row, 0, "Tu nota", fmt["kpi_label"])
        ws.merge_range(row, 1, row, 3, a.note_text, fmt["cell"])
        row += 1
        ws.write(row, 0, "API", fmt["kpi_label"])
        ws.merge_range(row, 1, row, 3,
                       f"¿Hubo modificatorio? {'Sí' if a.api_says_modif else 'No'} "
                       f"({a.api_count} modificatorios formales en cb9c-h8sn)",
                       fmt["cell"])
        row += 1
        ws.write(row, 0, "Docs", fmt["kpi_label"])
        ws.merge_range(row, 1, row, 3,
                       f"{a.docs_mod_count} modificatorios + {a.docs_leg_count} legalizaciones publicadas en SECOP",
                       fmt["cell"])
        row += 2  # blank spacer


def _verdict_cell_fmt(fmt, verdict: str):
    if verdict == VERDICT_NOTE_ONLY:
        return fmt["v_red"]
    if verdict == VERDICT_NOTA_FALTA:
        return fmt["v_orange"]
    if verdict in (VERDICT_API_LAG, VERDICT_DOCS_LIDERA):
        return fmt["v_yellow"]
    if verdict in (VERDICT_AGREE_NO, VERDICT_AGREE_SI):
        return fmt["v_green"]
    return fmt["v_gray"]


__all__ = ["build_audit_workbook", "ReportInfo"]
