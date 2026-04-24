"""Audit / identification extractor.

This extractor does NOT derive anything — it **mirrors** what SECOP II says
about a process so the user can verify fila-por-fila that the URL in her
Excel really corresponds to the entity/object/phase she thinks it does.
It also ships the exact ``datos.gov.co`` query URL used for this row so
the user can click it in her browser and read the raw JSON that fed the
answer ("evidencia").

Because the spirit is **auditoría**, the extractor always writes
something meaningful even when the process is not found on Socrata: in
that case the Fase column holds ``no_encontrado`` and the audit link
still points to the query that returned nothing — which itself is a
verifiable fact.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from secop_ii.config import (
    DATASET_PROCESOS,
    FIELD_PROCESO_ENTIDAD,
    FIELD_PROCESO_FASE,
    FIELD_PROCESO_ID,
    FIELD_PROCESO_NIT,
    FIELD_PROCESO_OBJETO,
    FIELD_PROCESO_VALOR,
)
from secop_ii.extractors.base import ExtractionResult, ProcessContext

COL_ID = "ID identificado"
COL_FASE = "Fase en SECOP"
COL_ENTIDAD = "Entidad en SECOP"
COL_NIT = "NIT entidad"
COL_OBJETO = "Objeto en SECOP"
COL_VALOR = "Valor estimado"
COL_LINK_API = "Link verificación API"


@dataclass
class AuditoriaExtractor:
    """Mirror key identifying fields from SECOP II for verification."""

    name: str = "auditoria"
    output_columns: tuple[str, ...] = (
        COL_ID,
        COL_FASE,
        COL_ENTIDAD,
        COL_NIT,
        COL_OBJETO,
        COL_VALOR,
        COL_LINK_API,
    )

    def extract(self, ctx: ProcessContext) -> ExtractionResult:
        pid = ctx.ref.process_id
        link_api = ctx.client.build_query_url(
            DATASET_PROCESOS,
            where=f"{FIELD_PROCESO_ID}='{pid}'",
            limit=10,
        )

        try:
            proceso = ctx.proceso()
        except Exception as exc:
            return ExtractionResult(
                values={
                    COL_ID: pid,
                    COL_FASE: f"error: {str(exc)[:80]}",
                    COL_ENTIDAD: "",
                    COL_NIT: "",
                    COL_OBJETO: "",
                    COL_VALOR: "",
                    COL_LINK_API: link_api,
                },
                ok=False,
                error=str(exc),
            )

        if proceso is None:
            return ExtractionResult(
                values={
                    COL_ID: pid,
                    COL_FASE: "no_encontrado",
                    COL_ENTIDAD: "",
                    COL_NIT: "",
                    COL_OBJETO: "",
                    COL_VALOR: "",
                    COL_LINK_API: link_api,
                },
                ok=False,
                error="Proceso no encontrado en el dataset de SECOP II",
            )

        values: dict[str, Any] = {
            COL_ID: pid,
            COL_FASE: _clean(proceso.get(FIELD_PROCESO_FASE)),
            COL_ENTIDAD: _clean(proceso.get(FIELD_PROCESO_ENTIDAD)),
            COL_NIT: _clean(proceso.get(FIELD_PROCESO_NIT)),
            COL_OBJETO: _clean(proceso.get(FIELD_PROCESO_OBJETO))[:250],
            COL_VALOR: _format_money(proceso.get(FIELD_PROCESO_VALOR)),
            COL_LINK_API: link_api,
        }
        return ExtractionResult(values=values, ok=True)


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _format_money(value: Any) -> Any:
    if value is None or value == "":
        return ""
    try:
        return float(str(value).replace(",", ""))
    except (ValueError, TypeError):
        return str(value)
