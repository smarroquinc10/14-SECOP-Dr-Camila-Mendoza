"""Fill the Dra.'s 77 FEAB columns from cross-verified SECOP data.

Cardinal rules (REVISED — SECOP is the source of truth):

1. SECOP IS THE TRUTH. For any SECOP-derivable column, the SECOP value
   wins. If the cell currently has a different manual value, OVERWRITE
   it — but log the previous value to "FEAB: Valores reemplazados" so
   nothing is "eaten" without a trail.
2. INTERNAL_ONLY columns (CDP, Orfeo, Abogado, etc.) are never touched —
   SECOP doesn't have those, so the manual value stands.
3. EMPTY cells get filled when SECOP has the data (no false negative).
4. EVERY filled cell carries a provenance trail in the audit columns
   (which dataset, which field, which confidence, what was replaced).

Output columns this extractor manages:

* The 77 Dra.-facing columns (filled with SECOP data when available).
* "FEAB: Auto-llenadas"     — list of column numbers we filled this run.
* "FEAB: Valores reemplazados" — old manual values that SECOP overwrote.
* "FEAB: Celdas a revisar"  — validation-flagged cells.
* "FEAB: Confianza global"  — HIGH/MEDIUM/LOW worst-of-cell.
* "FEAB: Fuentes"           — pipe-separated provenance summary.
* "FEAB: Hash SECOP"        — SHA-256 evidence fingerprint.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from secop_ii.audit_log import append_entry as _audit_append
from secop_ii.extractors.base import ExtractionResult, ProcessContext
from secop_ii.feab_columns import (
    FEAB_COLUMNS_ORDERED,
    INTERNAL_ONLY,
    compute_feab_fill,
    source_fingerprint,
)
from secop_ii.feab_validation import validate_fills

COL_AUTO_LLENADAS = "FEAB: Auto-llenadas"
COL_REEMPLAZADOS = "FEAB: Valores reemplazados (manual previo)"
COL_CONFIANZA = "FEAB: Confianza global"
COL_FUENTES = "FEAB: Fuentes"
COL_VER_DETALLE = "FEAB: Ver detalle"
COL_REVISAR = "FEAB: Celdas a revisar"
COL_HASH_SECOP = "FEAB: Hash SECOP (SHA-256)"
# Backwards-compat alias so older callers (and the orchestrator) keep working
COL_DISCREPANCIAS = COL_REEMPLAZADOS


# Currency / amount columns — comparison must be numeric, not string.
_NUMERIC_COLUMNS = {
    "28.VALOR INICIAL DEL CONTRATO (INCLUIDAS VIGENCIA ACTUAL Y FUTURAS)",
    "29. VALOR INICIAL DEL CONTRATO VIGENCIA ACTUAL",
    "34. ANTICIPOS o PAGO ANTICIPADO : VALOR TOTAL",
    "35A. REDUCCIONES VALOR TOTAL",
    "35A. ADICIONES VALOR TOTAL",
    "36. VALOR TOTAL",
    "37. PRÓRROGAS : NÚMERO DE DÍAS",
    "63. PORCENTAJE DE AVANCE FÍSICO PROGRAMADO",
    "64. PORCENTAJE DE AVANCE FÍSICO REAL",
    "65. PORCENTAJE AVANCE PRESUPUESTAL PROGRAMADO",
    "66. PORCENTAJE AVANCE PRESUPUESTAL REAL",
    "VALOR TOTAL INGRESO",
}

# Date columns — comparison normalizes both sides to YYYY-MM-DD before
# comparing so "2024-06-13 00:00:00" and "13/06/2024" don't false-flag.
_DATE_COLUMNS = {
    "5. FECHA SUSCRIPCIÓN",
    "8. FECHA INICIO",
    "9. FECHA TERMINACIÓN",
    "25A. FECHA CDP",
    "26A. FECHA REGISTRO PRESUPUESTAL",
    "49. GARANTÍAS : FECHA DE EXPEDICIÓN DE GARANTÍAS",
    "60.FECHA DE RADICADO DE ÚLTIMO INFORME DE SUPERVISION PRESENTADO",
    "61.FECHA ESTIMADA DE PRESENTACIÓN PRÓXIMO INFORME  DE SUPERVISION",
    "68. FECHA LIQUIDACIÓN",
}


@dataclass
class FeabFillExtractor:
    """The main extractor that fills the Dra.'s 77 columns.

    Behavior:
    * Reads existing cell values (passed as ``ctx.existing_row``) so we
      never overwrite manual data.
    * Calls compute_feab_fill() with all available SECOP data.
    * Returns only fillable columns + 4 audit metadata columns.
    """

    name: str = "feab_fill"
    output_columns: tuple[str, ...] = (
        FEAB_COLUMNS_ORDERED + (
            COL_AUTO_LLENADAS,
            COL_REEMPLAZADOS,
            COL_REVISAR,
            COL_CONFIANZA,
            COL_FUENTES,
            COL_HASH_SECOP,
            COL_VER_DETALLE,
        )
    )

    def extract(self, ctx: ProcessContext) -> ExtractionResult:
        try:
            proceso = ctx.proceso()
            contratos = ctx.contratos()
        except Exception as exc:  # pragma: no cover
            return ExtractionResult(values={}, ok=False, error=str(exc))

        # Cross-cut: pull adiciones / garantias / ejecucion in one batch
        # so compute_feab_fill has everything it needs.
        adiciones_by_contrato: dict[str, list[dict]] = {}
        garantias_by_contrato: dict[str, list[dict]] = {}
        ejecucion_by_contrato: dict[str, list[dict]] = {}

        for c in contratos or []:
            cid = c.get("id_contrato")
            if not cid:
                continue
            try:
                adiciones_by_contrato[cid] = ctx.adiciones_de(cid)
            except Exception:
                adiciones_by_contrato[cid] = []
            try:
                garantias_by_contrato[cid] = ctx.garantias_de(cid)
            except Exception:
                garantias_by_contrato[cid] = []
            try:
                ejecucion_by_contrato[cid] = ctx.ejecucion_de(cid)
            except Exception:
                ejecucion_by_contrato[cid] = []

        result = compute_feab_fill(
            proceso=proceso,
            contratos=contratos,
            notice_uid=ctx.notice_uid(),
            source_url=ctx.ref.source_url,
            adiciones_by_contrato=adiciones_by_contrato,
            garantias_by_contrato=garantias_by_contrato,
            ejecucion_by_contrato=ejecucion_by_contrato,
        )

        existing = getattr(ctx, "existing_row", {}) or {}

        fill_values, replaced_log, fuentes = _decide_fills(
            result=result, existing=existing
        )

        # Run consistency validation on the SECOP-derived values. The
        # validation NEVER blocks fills — it only collects flags so the
        # Dra. knows which cells warrant her review. Empty cell would be
        # a false negative; we always show what SECOP says and tell her
        # if something looks off (date inversion, NIT DV mismatch, etc.).
        validation = validate_fills(result.values)
        revisar_cells = sorted(
            (_extract_numbers(c) or c for c in validation.needs_review),
            key=_num_sort_key,
        )

        # Build audit summary columns.
        confidences = [result.confidence[c] for c in fill_values
                      if c in result.confidence]
        if not confidences:
            confianza_global = ""
        elif "LOW" in confidences:
            confianza_global = "LOW"
        elif "MEDIUM" in confidences:
            confianza_global = "MEDIUM"
        else:
            confianza_global = "HIGH"

        # Auto-llenadas column: list "2, 5, 8, 9, ..." sorted numerically
        # (so "4" comes before "27", not after as string sort would).
        auto_nums_raw = [_extract_numbers(c) for c in fill_values
                        if _extract_numbers(c)]
        seen: set[str] = set()
        auto_nums_unique: list[str] = []
        for n in sorted(auto_nums_raw, key=_num_sort_key):
            if n not in seen:
                seen.add(n)
                auto_nums_unique.append(n)

        # The "ver detalle" link is a relative path generated later by
        # the HTML drill-down module; here we just record the expected
        # filename based on the process_id.
        process_id = ctx.ref.process_id
        ver_detalle = f"detalles/{process_id}.html" if process_id else ""

        # Cryptographic fingerprint of the SECOP raw payload — Dra. can
        # prove "this is what SECOP returned at update time" if she has
        # to defend a value in compliance/audit later.
        hash_secop = source_fingerprint(
            proceso=proceso,
            contratos=contratos or [],
            notice_uid=ctx.notice_uid(),
        )

        # Append every fill / replace to the immutable hash-chained
        # audit log. The chain links each entry to the previous one's
        # SHA-256 so any post-hoc edit breaks integrity.
        try:
            log_path = Path(".cache") / "audit_log.jsonl"
            row_idx = getattr(ctx, "row_idx", None)
            for col, new_val in fill_values.items():
                old = existing.get(col)
                op = "replace" if old not in (None, "") else "fill"
                _audit_append(
                    log_path,
                    op=op,
                    row=row_idx,
                    process_id=ctx.ref.process_id,
                    column=col,
                    old=str(old) if old not in (None, "") else None,
                    new=str(new_val),
                    source=fuentes.get(col),
                    confidence=result.confidence.get(col),
                    secop_hash=hash_secop,
                )
        except Exception as exc:  # pragma: no cover — audit must never block
            import logging
            logging.getLogger(__name__).warning(
                "audit log append failed (non-fatal): %s", exc
            )

        out = dict(fill_values)
        out[COL_AUTO_LLENADAS] = ", ".join(auto_nums_unique)
        out[COL_REEMPLAZADOS] = " | ".join(replaced_log)[:2000]
        out[COL_REVISAR] = ", ".join(revisar_cells + [
            i.split(":")[0].strip() for i in validation.issues
        ])
        out[COL_CONFIANZA] = confianza_global
        out[COL_FUENTES] = " | ".join(
            f"{_extract_numbers(c) or c}={fuentes[c]}"
            for c in sorted(fuentes)
        )[:2000]
        out[COL_HASH_SECOP] = hash_secop
        out[COL_VER_DETALLE] = ver_detalle

        return ExtractionResult(values=out, ok=True)


def _decide_fills(
    *, result, existing: dict[str, Any]
) -> tuple[dict[str, Any], list[str], dict[str, str]]:
    """Apply the SECOP-wins rule. Log replaced manual values for audit.

    For every SECOP-derivable cell:
    * Cell empty -> fill with SECOP value (no false negative).
    * Cell matches SECOP -> no-op (preserve formatting).
    * Cell differs from SECOP -> OVERWRITE with SECOP, log old value to
      "Valores reemplazados" so nothing is lost without a paper trail.
    INTERNAL_ONLY columns are never touched (SECOP doesn't have them).

    Returns ``(values_to_write, replaced_log, sources_used)`` where
    replaced_log is the list of "col: prev='...' nuevo='...'" entries
    surfaced in the COL_REEMPLAZADOS audit cell.
    """
    values_to_write: dict[str, Any] = {}
    replaced_log: list[str] = []
    sources_used: dict[str, str] = {}

    for col, secop_value in result.values.items():
        # Never touch internal-only columns — SECOP doesn't own them.
        if col in INTERNAL_ONLY:
            continue

        existing_value = existing.get(col)
        existing_norm = _normalize_for_compare(existing_value, col)
        secop_norm = _normalize_for_compare(secop_value, col)

        # SECOP wins. Always write the SECOP value (unless equal to current,
        # in which case skip to preserve any custom formatting).
        if existing_norm == secop_norm:
            continue

        values_to_write[col] = secop_value
        sources_used[col] = result.sources.get(col, "")

        # If the cell had a different non-empty value before, log the
        # replacement so the Dra. has a full audit trail.
        if existing_norm not in (None, "", "NO", "N/A"):
            replaced_log.append(
                f"{_extract_numbers(col) or col}: "
                f"previo='{_truncate(str(existing_value))}' "
                f"SECOP='{_truncate(str(secop_value))}'"
            )

    return values_to_write, replaced_log, sources_used


def _normalize_for_compare(value: Any, col: str) -> Any:
    """Normalize a value for comparison so we don't false-flag.

    * Empty-ish values collapse to "".
    * Numeric columns compare as floats (rounded).
    * Date columns compare as YYYY-MM-DD.
    * Other strings are stripped + uppercased.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        s = value.strip()
        if not s or s.lower() in {"no definido", "no definida", "n/a"}:
            return ""
    if col in _NUMERIC_COLUMNS:
        try:
            return round(float(str(value).replace(",", "").replace("$", "")), 2)
        except (ValueError, TypeError):
            return str(value).strip().upper()
    if col in _DATE_COLUMNS:
        s = str(value)[:10]
        return s
    s = str(value).strip().upper()
    # Collapse whitespace
    return re.sub(r"\s+", " ", s)


_NUM_RE = re.compile(r"^(\d+[A-Z]?)\.")


def _extract_numbers(col: str) -> str:
    """Extract '35A' from '35A. ADICIONES VALOR TOTAL'."""
    m = _NUM_RE.match(col.strip())
    return m.group(1) if m else ""


def _num_sort_key(label: str) -> tuple[int, str]:
    """Sort '4' < '12' < '27' < '35A' < '35B'."""
    m = re.match(r"^(\d+)([A-Z]?)$", label)
    if not m:
        return (10_000, label)
    return (int(m.group(1)), m.group(2))


def _truncate(s: str, n: int = 60) -> str:
    return s if len(s) <= n else s[:n - 1] + "…"


__all__ = [
    "FeabFillExtractor",
    "COL_AUTO_LLENADAS",
    "COL_DISCREPANCIAS",
    "COL_CONFIANZA",
    "COL_FUENTES",
    "COL_VER_DETALLE",
]
