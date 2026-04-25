"""Summarize the ``ibyt-yi2f`` invoices/payments for a process's contracts.

This is the single most useful piece of money-flow info the Dra. has to
type by hand: how many invoices, how much was paid, when was the last
payment. The extractor sums everything across all contracts of a process
so a one-shot view tells the full story.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from secop_ii.extractors.base import ExtractionResult, ProcessContext

COL_TOTAL = "Pagos: # facturas"
COL_PAGADAS = "Pagos: # pagadas"
COL_TOTAL_FACTURADO = "Pagos: Total facturado"
COL_TOTAL_PAGADO = "Pagos: Total pagado"
COL_TOTAL_NETO = "Pagos: Total neto"
COL_ULTIMA = "Pagos: Última factura"
COL_DETALLE = "Pagos: Detalle"


@dataclass
class PagosExtractor:
    name: str = "pagos"
    output_columns: tuple[str, ...] = (
        COL_TOTAL,
        COL_PAGADAS,
        COL_TOTAL_FACTURADO,
        COL_TOTAL_PAGADO,
        COL_TOTAL_NETO,
        COL_ULTIMA,
        COL_DETALLE,
    )

    def extract(self, ctx: ProcessContext) -> ExtractionResult:
        try:
            contratos = ctx.contratos()
        except Exception as exc:  # pragma: no cover
            return ExtractionResult(values=_empty(), ok=False, error=str(exc))

        all_fact: list[dict] = []
        for c in contratos:
            cid = c.get("id_contrato")
            if not cid:
                continue
            try:
                all_fact.extend(ctx.facturas_de(cid))
            except Exception as exc:  # pragma: no cover
                return ExtractionResult(values=_empty(), ok=False, error=str(exc))

        if not all_fact:
            return ExtractionResult(values=_empty(), ok=True)

        pagadas = [f for f in all_fact if str(f.get("pago_confirmado")).lower() in ("true", "1")]
        tot_fact = _sum_field(all_fact, "valor_total")
        tot_pag = _sum_field(all_fact, "valor_a_pagar")
        tot_neto = _sum_field(all_fact, "valor_neto")

        # Most recent factura by fecha_factura
        all_fact_sorted = sorted(
            all_fact, key=lambda f: f.get("fecha_factura") or "", reverse=True
        )
        ult = all_fact_sorted[0] if all_fact_sorted else {}
        ult_str = ""
        if ult:
            ult_str = (
                f"{(ult.get('fecha_factura') or '')[:10]} "
                f"#{ult.get('numero_de_factura') or ''} "
                f"{ult.get('estado') or ''} "
                f"${ult.get('valor_a_pagar') or ''}"
            ).strip()

        detalle = []
        for f in all_fact_sorted[:8]:
            fc = (f.get("fecha_factura") or "")[:10]
            num = f.get("numero_de_factura") or ""
            est = f.get("estado") or ""
            val = f.get("valor_a_pagar") or ""
            detalle.append(f"{fc} #{num} {est} ${val}")

        values: dict[str, Any] = {
            COL_TOTAL: len(all_fact),
            COL_PAGADAS: len(pagadas),
            COL_TOTAL_FACTURADO: tot_fact,
            COL_TOTAL_PAGADO: tot_pag,
            COL_TOTAL_NETO: tot_neto,
            COL_ULTIMA: ult_str,
            COL_DETALLE: " | ".join(detalle)[:1000],
        }
        return ExtractionResult(values=values, ok=True)


def _empty() -> dict[str, Any]:
    return {col: "" for col in PagosExtractor.output_columns}


def _sum_field(rows: list[dict], field: str) -> int | float | str:
    total = 0.0
    found = False
    for r in rows:
        v = r.get(field)
        if v is None or v == "":
            continue
        try:
            total += float(str(v).replace(",", ""))
            found = True
        except (ValueError, TypeError):
            pass
    if not found:
        return ""
    return int(total) if total.is_integer() else round(total, 2)


__all__ = ["PagosExtractor"]
