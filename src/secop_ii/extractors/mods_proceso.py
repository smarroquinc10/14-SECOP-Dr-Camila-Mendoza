"""Surface modifications to the **process** (not the contract) from ``e2u2-swiw``.

A SECOP II process can be edited after publication — addenda, scope
changes, deadline extensions before adjudication. Those edits do **not**
touch the contract once signed, so they don't show up in any of our
contract-level datasets. This extractor uses ``portafolio`` (CO1.BDOS.*)
to fetch them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from secop_ii.extractors.base import ExtractionResult, ProcessContext

COL_TOTAL = "Mods proceso: # ediciones"
COL_ULTIMA = "Mods proceso: Última edición"
COL_DETALLE = "Mods proceso: Detalle"


@dataclass
class ModsProcesoExtractor:
    name: str = "mods_proceso"
    output_columns: tuple[str, ...] = (
        COL_TOTAL,
        COL_ULTIMA,
        COL_DETALLE,
    )

    def extract(self, ctx: ProcessContext) -> ExtractionResult:
        try:
            rows = ctx.mods_proceso()
        except Exception as exc:  # pragma: no cover
            return ExtractionResult(values=_empty(), ok=False, error=str(exc))

        if not rows:
            return ExtractionResult(values=_empty(), ok=True)

        ultima = max((r.get("ultima_modificacion", "") for r in rows), default="")
        detalle = []
        for r in sorted(rows, key=lambda r: r.get("ultima_modificacion", ""), reverse=True)[:5]:
            fc = (r.get("ultima_modificacion") or "")[:19]
            desc = (r.get("descripcion_proceso") or "")[:60]
            detalle.append(f"{fc} {desc}".strip())

        values: dict[str, Any] = {
            COL_TOTAL: len(rows),
            COL_ULTIMA: (ultima or "")[:19],
            COL_DETALLE: " | ".join(detalle)[:800],
        }
        return ExtractionResult(values=values, ok=True)


def _empty() -> dict[str, Any]:
    return {col: "" for col in ModsProcesoExtractor.output_columns}


__all__ = ["ModsProcesoExtractor"]
