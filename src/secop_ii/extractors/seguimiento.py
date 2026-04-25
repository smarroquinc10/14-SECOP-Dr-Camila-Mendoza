"""Combine progress (``mfmm-jqmq``) and suspensions (``u99c-7mfm``).

Coverage on FEAB is low (0/10 in the discovery sample) but when it
appears it is high-signal: a contract with avance-real << avance-esperado
is on its way to default; a suspended contract has explicit legal
implications. So we still surface them and rely on the empty-string
behaviour to keep cells clean when nothing is there.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from secop_ii.extractors.base import ExtractionResult, ProcessContext

COL_AVANCE_REAL = "Seguimiento: Avance real %"
COL_AVANCE_ESP = "Seguimiento: Avance esperado %"
COL_AVANCE_GAP = "Seguimiento: Brecha avance"
COL_FECHA_ENT_REAL = "Seguimiento: Última entrega real"
COL_FECHA_ENT_ESP = "Seguimiento: Última entrega esperada"
COL_NUM_SUSPENSIONES = "Seguimiento: # suspensiones"
COL_TIPO_SUSPENSION = "Seguimiento: Tipo suspensión"
COL_PROPOSITO_SUSP = "Seguimiento: Propósito suspensión"
COL_ULTIMA_SUSP = "Seguimiento: Última suspensión"


@dataclass
class SeguimientoExtractor:
    name: str = "seguimiento"
    output_columns: tuple[str, ...] = (
        COL_AVANCE_REAL,
        COL_AVANCE_ESP,
        COL_AVANCE_GAP,
        COL_FECHA_ENT_REAL,
        COL_FECHA_ENT_ESP,
        COL_NUM_SUSPENSIONES,
        COL_TIPO_SUSPENSION,
        COL_PROPOSITO_SUSP,
        COL_ULTIMA_SUSP,
    )

    def extract(self, ctx: ProcessContext) -> ExtractionResult:
        try:
            contratos = ctx.contratos()
        except Exception as exc:  # pragma: no cover
            return ExtractionResult(values=_empty(), ok=False, error=str(exc))

        ejec_rows: list[dict] = []
        susp_rows: list[dict] = []
        for c in contratos:
            cid = c.get("id_contrato")
            if not cid:
                continue
            try:
                ejec_rows.extend(ctx.ejecucion_de(cid))
                susp_rows.extend(ctx.suspensiones_de(cid))
            except Exception as exc:  # pragma: no cover
                return ExtractionResult(values=_empty(), ok=False, error=str(exc))

        # Avance: take MAX porcentaje_de_avance_real across all rows for the
        # process — the most recent reading wins. Same for esperado.
        avance_real = _max_pct(ejec_rows, "porcentaje_de_avance_real")
        avance_esp = _max_pct(ejec_rows, "porcentajedeavanceesperado")
        gap = ""
        if avance_real != "" and avance_esp != "":
            gap = round(float(avance_esp) - float(avance_real), 2)

        # Most recent entrega
        ent_real = _max_date(ejec_rows, "fechadeentregareal")
        ent_esp = _max_date(ejec_rows, "fechadeentregaesperada")

        # Suspensiones
        ult_susp_row = max(
            (s for s in susp_rows if s.get("fecha_de_creacion")),
            key=lambda s: s.get("fecha_de_creacion"),
            default=None,
        )
        if ult_susp_row:
            ult = (
                f"{(ult_susp_row.get('fecha_de_creacion') or '')[:10]} - "
                f"{ult_susp_row.get('tipo') or ''}"
            ).strip(" -")
        else:
            ult = ""

        values: dict[str, Any] = {
            COL_AVANCE_REAL: avance_real,
            COL_AVANCE_ESP: avance_esp,
            COL_AVANCE_GAP: gap,
            COL_FECHA_ENT_REAL: ent_real,
            COL_FECHA_ENT_ESP: ent_esp,
            COL_NUM_SUSPENSIONES: len(susp_rows),
            COL_TIPO_SUSPENSION: (ult_susp_row or {}).get("tipo") or "",
            COL_PROPOSITO_SUSP: ((ult_susp_row or {}).get("proposito_de_la_modificacion") or "")[:300],
            COL_ULTIMA_SUSP: ult,
        }
        return ExtractionResult(values=values, ok=True)


def _empty() -> dict[str, Any]:
    return {col: "" for col in SeguimientoExtractor.output_columns}


def _max_pct(rows: list[dict], field: str) -> float | str:
    best = -1.0
    for r in rows:
        v = r.get(field)
        if v is None or v == "":
            continue
        try:
            n = float(str(v).replace(",", ""))
            if n > best:
                best = n
        except (ValueError, TypeError):
            pass
    if best < 0:
        return ""
    return round(best, 2)


def _max_date(rows: list[dict], field: str) -> str:
    best = ""
    for r in rows:
        v = (r.get(field) or "")[:10]
        if v and v > best:
            best = v
    return best


__all__ = ["SeguimientoExtractor"]
