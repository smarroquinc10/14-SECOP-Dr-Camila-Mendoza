"""Summarize the ``gjp9-cutm`` policies (garantías) for a process's contracts.

Each contract can have several pólizas (cumplimiento, calidad, salarios,
seguridad social, etc.). The Dra. tracks them by hand to know which one
expired and needs renewal. This extractor counts them, lists their
insurance companies and the latest expiration date.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from secop_ii.extractors.base import ExtractionResult, ProcessContext

COL_TOTAL = "Garantías: # pólizas"
COL_VIGENTES = "Garantías: # vigentes"
COL_ASEGURADORAS = "Garantías: Aseguradoras"
COL_TIPOS = "Garantías: Tipos de póliza"
COL_FIN_MAX = "Garantías: Fecha fin más lejana"
COL_VALOR_TOTAL = "Garantías: Valor total"
COL_DETALLE = "Garantías: Detalle"


@dataclass
class GarantiasExtractor:
    name: str = "garantias"
    output_columns: tuple[str, ...] = (
        COL_TOTAL,
        COL_VIGENTES,
        COL_ASEGURADORAS,
        COL_TIPOS,
        COL_FIN_MAX,
        COL_VALOR_TOTAL,
        COL_DETALLE,
    )

    def extract(self, ctx: ProcessContext) -> ExtractionResult:
        try:
            contratos = ctx.contratos()
        except Exception as exc:  # pragma: no cover
            return ExtractionResult(values=_empty(), ok=False, error=str(exc))

        all_polizas: list[dict] = []
        for c in contratos:
            cid = c.get("id_contrato")
            if not cid:
                continue
            try:
                all_polizas.extend(ctx.garantias_de(cid))
            except Exception as exc:  # pragma: no cover
                return ExtractionResult(values=_empty(), ok=False, error=str(exc))

        if not all_polizas:
            return ExtractionResult(values=_empty(), ok=True)

        vigentes = [p for p in all_polizas if (p.get("estado") or "").lower() == "vigente"]
        aseguradoras = sorted({(p.get("aseguradora") or "").strip() for p in all_polizas if p.get("aseguradora")})
        tipos = sorted({(p.get("tipopoliza") or "").strip() for p in all_polizas if p.get("tipopoliza")})

        fechas_fin = [p.get("fechafinpoliza") for p in all_polizas if p.get("fechafinpoliza")]
        fin_max = max(fechas_fin)[:10] if fechas_fin else ""

        valor_total = 0.0
        for p in all_polizas:
            try:
                valor_total += float(str(p.get("valor") or 0).replace(",", ""))
            except (ValueError, TypeError):
                pass

        detalle_rows = []
        for p in all_polizas[:10]:  # cap so the cell stays readable
            asg = (p.get("aseguradora") or "")[:30]
            tipo = (p.get("tipopoliza") or "")[:25]
            num = p.get("numeropoliza") or ""
            estado = p.get("estado") or ""
            fin = (p.get("fechafinpoliza") or "")[:10]
            detalle_rows.append(f"{tipo} {asg} #{num} ({estado}, vence {fin})")

        values: dict[str, Any] = {
            COL_TOTAL: len(all_polizas),
            COL_VIGENTES: len(vigentes),
            COL_ASEGURADORAS: " | ".join(aseguradoras),
            COL_TIPOS: " | ".join(tipos),
            COL_FIN_MAX: fin_max,
            COL_VALOR_TOTAL: int(valor_total) if valor_total.is_integer() else valor_total,
            COL_DETALLE: " | ".join(detalle_rows)[:1000],
        }
        return ExtractionResult(values=values, ok=True)


def _empty() -> dict[str, Any]:
    return {col: "" for col in GarantiasExtractor.output_columns}


__all__ = ["GarantiasExtractor"]
