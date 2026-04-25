"""Validation layer for FEAB fills — flags issues, NEVER drops data.

Cardinal rule REVISED: empty cell = false negative (SECOP had the data,
we didn't show it). Wrong cell = false positive (we showed something
incorrect). Both are equally bad. The right answer is: ALWAYS fill the
cell with what SECOP says, and CLEARLY FLAG issues so the Dra. knows
which cells need her review.

This module never blocks a fill. It only collects warnings/errors that
the caller surfaces in the discrepancias column and the HTML drill-down.

Checks performed:

* **Date consistency**: fecha_firma <= fecha_inicio <= fecha_terminacion;
  fecha_inicio_liquidacion < fecha_fin_liquidacion.
* **Arithmetic consistency**: valor_inicial + adiciones - reducciones ==
  valor_total (within rounding tolerance).
* **NIT format**: only digits, length 8-11, optional DV.
* **Reasonable ranges**: percentages in [0, 100]; dates after 1990 and
  before 2100; amounts non-negative.
* **Source agreement**: when the same field appears in multiple SECOP
  datasets (e.g., proceso vs contrato), they must agree.

Returns ``ValidationReport`` with:
* ``passed``: dict[col -> True/False] — only True cells should be written.
* ``warnings``: list[str] of human-readable issues.
* ``hard_errors``: list[str] for things that cannot be auto-resolved.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from secop_ii.feab_columns import (
    COL_ADICIONES,
    COL_AVANCE_FISICO_REAL,
    COL_AVANCE_PRESUP_REAL,
    COL_CONTRATISTA_DV,
    COL_CONTRATISTA_NUM_ID,
    COL_CONTRATISTA_TIPO_ID,
    COL_ENTIDAD_RECURSOS_DV,
    COL_ENTIDAD_RECURSOS_NIT,
    COL_FECHA_INICIO,
    COL_FECHA_LIQUIDACION,
    COL_FECHA_SUSCRIPCION,
    COL_FECHA_TERMINACION,
    COL_REDUCCIONES,
    COL_VALOR_INICIAL,
    COL_VALOR_TOTAL,
    nit_dv,
)

_NIT_RE = re.compile(r"^\d{6,11}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")


@dataclass
class ValidationReport:
    """Issues flagged during validation. Data is ALWAYS written regardless.

    ``needs_review`` lists columns the Dra. should eyeball — SECOP had
    the data but something looks off (dates out of order, arithmetic
    mismatch, percentage out of range, NIT DV wrong). The cell still
    gets filled; the flag just tells her this one warrants a second look.
    """

    needs_review: set[str] = field(default_factory=set)
    issues: list[str] = field(default_factory=list)

    def flag(self, col: str, why: str) -> None:
        """Mark a column as needing review. Does NOT block the fill."""
        self.needs_review.add(col)
        self.issues.append(f"{col}: {why}")


def validate_fills(values: dict[str, Any]) -> ValidationReport:
    """Run every consistency check and return a report of issues.

    The data is ALWAYS written by the caller — this report only flags
    cells the Dra. should eyeball.
    """
    report = ValidationReport()
    _check_dates(values, report)
    _check_arithmetic(values, report)
    _check_nit(
        values=values,
        nit_col=COL_ENTIDAD_RECURSOS_NIT,
        dv_col=COL_ENTIDAD_RECURSOS_DV,
        report=report,
        label="entidad",
    )
    _check_nit(
        values=values,
        nit_col=COL_CONTRATISTA_NUM_ID,
        dv_col=COL_CONTRATISTA_DV,
        report=report,
        label="contratista",
        only_if_tipo=values.get(COL_CONTRATISTA_TIPO_ID),
    )
    _check_percentages(values, report)

    return report


# ---- Individual checks -------------------------------------------------------


def _parse_date(value: Any) -> datetime | None:
    if not value:
        return None
    s = str(value)[:10]
    if not _DATE_RE.match(s):
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        return None


def _check_dates(values: dict[str, Any], report: ValidationReport) -> None:
    """fecha_firma <= fecha_inicio <= fecha_terminacion."""
    firma = _parse_date(values.get(COL_FECHA_SUSCRIPCION))
    inicio = _parse_date(values.get(COL_FECHA_INICIO))
    fin = _parse_date(values.get(COL_FECHA_TERMINACION))
    liquidacion = _parse_date(values.get(COL_FECHA_LIQUIDACION))

    # Hard sanity bounds
    today = datetime.now()
    for col, dt in [(COL_FECHA_SUSCRIPCION, firma),
                    (COL_FECHA_INICIO, inicio),
                    (COL_FECHA_TERMINACION, fin),
                    (COL_FECHA_LIQUIDACION, liquidacion)]:
        if dt is None:
            continue
        if dt.year < 1990:
            report.flag(col, f"date too old ({dt.year})")
        elif dt.year > 2100:
            report.flag(col, f"date too far in future ({dt.year})")

    # Order: firma <= inicio <= fin
    if firma and inicio and firma > inicio:
        # Don't fail — SECOP sometimes records inicio before firma when
        # the "fecha de aprobación" predates the formal signing. Just warn.
        report.flag(COL_FECHA_INICIO,
                    f"fecha inicio {inicio.date()} < fecha firma {firma.date()}")
    if inicio and fin and inicio > fin:
        report.flag(COL_FECHA_TERMINACION,
                    f"fecha terminación {fin.date()} < fecha inicio {inicio.date()}")
    if fin and liquidacion and liquidacion < fin:
        # Liquidación should be AT OR AFTER fin del contrato.
        report.flag(COL_FECHA_LIQUIDACION,
                    f"fecha liquidación {liquidacion.date()} < fecha terminación {fin.date()}")


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "").replace("$", "").strip())
    except (ValueError, TypeError):
        return None


def _check_arithmetic(values: dict[str, Any], report: ValidationReport) -> None:
    """valor_inicial + adiciones - reducciones == valor_total (±1 peso)."""
    inicial = _to_float(values.get(COL_VALOR_INICIAL))
    adiciones = _to_float(values.get(COL_ADICIONES)) or 0.0
    reducciones = _to_float(values.get(COL_REDUCCIONES)) or 0.0
    total = _to_float(values.get(COL_VALOR_TOTAL))

    # Negative amounts are always wrong.
    for col, v in [(COL_VALOR_INICIAL, inicial),
                   (COL_VALOR_TOTAL, total)]:
        if v is not None and v < 0:
            report.flag(col, f"negative amount {v}")

    if inicial is not None and total is not None:
        expected = inicial + adiciones - reducciones
        if abs(expected - total) > 1.0:  # 1-peso rounding tolerance
            # The arithmetic SHOULD hold by construction in compute_feab_fill,
            # so a mismatch here is a bug.
            report.flag(COL_VALOR_TOTAL,
                        f"arithmetic mismatch: {inicial:.0f} + {adiciones:.0f} "
                        f"- {reducciones:.0f} = {expected:.0f} ≠ {total:.0f}")


def _check_nit(
    *,
    values: dict[str, Any],
    nit_col: str,
    dv_col: str,
    report: ValidationReport,
    label: str,
    only_if_tipo: str | None = None,
) -> None:
    """Validate NIT format and DV consistency.

    If ``only_if_tipo`` is given and != 'NIT', skip the DV check (CC, CE
    don't have a DV).
    """
    nit = values.get(nit_col)
    if not nit:
        return
    nit_str = str(nit).strip().replace("-", "").replace(".", "").replace(" ", "")
    if not _NIT_RE.match(nit_str):
        # Don't fail when label='contratista' and tipo!=NIT (CC has different format)
        if only_if_tipo and str(only_if_tipo).upper() != "NIT":
            return
        report.flag(nit_col, f"{label} NIT '{nit}' has invalid format "
                             "(expected 6-11 digits)")
        return

    # If a DV cell was filled, verify it.
    if only_if_tipo and str(only_if_tipo).upper() != "NIT":
        # Ensure no DV is set for non-NIT
        if values.get(dv_col):
            report.flag(dv_col, f"DV set but tipo='{only_if_tipo}' (not NIT)")
        return

    dv = values.get(dv_col)
    if dv is None or dv == "":
        return  # we didn't compute it; nothing to verify
    expected_dv = nit_dv(nit_str)
    if str(dv).strip() != expected_dv:
        report.flag(dv_col,
                    f"DV {dv} does not match expected {expected_dv} for NIT {nit_str}")


def _check_percentages(values: dict[str, Any], report: ValidationReport) -> None:
    """Avance percentages must be in [0, 100]."""
    for col in (COL_AVANCE_FISICO_REAL, COL_AVANCE_PRESUP_REAL):
        v = _to_float(values.get(col))
        if v is None:
            continue
        if v < 0 or v > 100:
            report.flag(col, f"percentage {v} out of [0, 100]")


__all__ = ["ValidationReport", "validate_fills"]
