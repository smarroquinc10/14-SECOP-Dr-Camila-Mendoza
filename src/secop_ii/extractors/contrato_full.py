"""Mirror every audit-relevant contract field from ``jbjy-vk9h``.

The :mod:`modificatorios` extractor only computes "did this process have
modificatorios?" from the contracts; it intentionally ignores the rest
of the row. This extractor surfaces the contract identity, dates, value,
state, supervisor, ordenador and money flow fields so the Excel reflects
the full life cycle of the contract — not just whether it was modified.

Multiple contracts on the same process are concatenated with ``|`` so
the user can see all of them in one cell. Numeric totals (``valor_pagado``
etc.) are summed across the contracts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from secop_ii.extractors.base import ExtractionResult, ProcessContext

COL_ID_CONTRATO = "Contrato: ID(s)"
COL_REFERENCIA = "Contrato: Referencia"
COL_ESTADO = "Contrato: Estado"
COL_PROVEEDOR = "Contrato: Proveedor adjudicado"
COL_DOC_PROVEEDOR = "Contrato: NIT/doc proveedor"
COL_VALOR = "Contrato: Valor"
COL_VALOR_PAGADO = "Contrato: Valor pagado"
COL_VALOR_FACTURADO = "Contrato: Valor facturado"
COL_VALOR_PENDIENTE = "Contrato: Valor pendiente pago"
COL_DURACION = "Contrato: Duración"
COL_DIAS_ADIC = "Contrato: Días adicionados"
COL_FECHA_FIRMA = "Contrato: Fecha firma"
COL_FECHA_INICIO = "Contrato: Fecha inicio"
COL_FECHA_FIN = "Contrato: Fecha fin"
COL_LIQUIDACION = "Contrato: ¿Liquidación?"
COL_FECHA_INI_LIQ = "Contrato: Fecha inicio liquidación"
COL_FECHA_FIN_LIQ = "Contrato: Fecha fin liquidación"
COL_SUPERVISOR = "Contrato: Supervisor"
COL_ORDENADOR_GASTO = "Contrato: Ordenador del gasto"
COL_ORIGEN_RECURSOS = "Contrato: Origen recursos"
COL_PRORROGABLE = "Contrato: ¿Prorrogable?"
COL_RAMA = "Contrato: Rama"
COL_SECTOR = "Contrato: Sector"
COL_EXTRAS = "Contrato: Otros campos"

_EXPLICIT_FIELDS = {
    "id_contrato", "referencia_del_contrato", "estado_contrato",
    "proveedor_adjudicado", "documento_proveedor", "tipodocproveedor",
    "valor_del_contrato", "valor_pagado", "valor_facturado",
    "valor_pendiente_de_pago", "valor_pendiente_de_ejecucion",
    "duraci_n_del_contrato", "dias_adicionados",
    "fecha_de_firma", "fecha_de_inicio_del_contrato", "fecha_de_fin_del_contrato",
    "liquidaci_n", "fecha_inicio_liquidacion", "fecha_fin_liquidacion",
    "nombre_supervisor", "nombre_ordenador_del_gasto",
    "origen_de_los_recursos", "el_contrato_puede_ser_prorrogado",
    "rama", "sector",
    # Already in proceso_full or auditoria — don't duplicate.
    "nombre_entidad", "nit_entidad", "objeto_del_contrato",
    "descripcion_del_proceso", "modalidad_de_contratacion",
    "proceso_de_compra", "urlproceso", "tipo_de_contrato",
    "codigo_entidad", "codigo_proveedor",
}


@dataclass
class ContratoFullExtractor:
    name: str = "contrato_full"
    output_columns: tuple[str, ...] = (
        COL_ID_CONTRATO,
        COL_REFERENCIA,
        COL_ESTADO,
        COL_PROVEEDOR,
        COL_DOC_PROVEEDOR,
        COL_VALOR,
        COL_VALOR_PAGADO,
        COL_VALOR_FACTURADO,
        COL_VALOR_PENDIENTE,
        COL_DURACION,
        COL_DIAS_ADIC,
        COL_FECHA_FIRMA,
        COL_FECHA_INICIO,
        COL_FECHA_FIN,
        COL_LIQUIDACION,
        COL_FECHA_INI_LIQ,
        COL_FECHA_FIN_LIQ,
        COL_SUPERVISOR,
        COL_ORDENADOR_GASTO,
        COL_ORIGEN_RECURSOS,
        COL_PRORROGABLE,
        COL_RAMA,
        COL_SECTOR,
        COL_EXTRAS,
    )

    def extract(self, ctx: ProcessContext) -> ExtractionResult:
        try:
            contratos = ctx.contratos()
        except Exception as exc:  # pragma: no cover
            return ExtractionResult(values=_empty(), ok=False, error=str(exc))
        if not contratos:
            return ExtractionResult(values=_empty(), ok=True)  # legitimate: not every process has a contract

        ids = [c.get("id_contrato", "") for c in contratos]
        refs = [c.get("referencia_del_contrato", "") for c in contratos]
        estados = sorted({c.get("estado_contrato", "") for c in contratos if c.get("estado_contrato")})
        proveedores = sorted({c.get("proveedor_adjudicado", "") for c in contratos if c.get("proveedor_adjudicado")})
        docs = sorted({
            f"{c.get('tipodocproveedor', '')}{':' if c.get('tipodocproveedor') else ''}{c.get('documento_proveedor', '')}".strip(":")
            for c in contratos if c.get("documento_proveedor")
        })

        values: dict[str, Any] = {
            COL_ID_CONTRATO: " | ".join(filter(None, ids)),
            COL_REFERENCIA: " | ".join(filter(None, refs)),
            COL_ESTADO: " | ".join(estados),
            COL_PROVEEDOR: " | ".join(proveedores),
            COL_DOC_PROVEEDOR: " | ".join(docs),
            COL_VALOR: _sum(c.get("valor_del_contrato") for c in contratos),
            COL_VALOR_PAGADO: _sum(c.get("valor_pagado") for c in contratos),
            COL_VALOR_FACTURADO: _sum(c.get("valor_facturado") for c in contratos),
            COL_VALOR_PENDIENTE: _sum(c.get("valor_pendiente_de_pago") for c in contratos),
            COL_DURACION: _join_unique(c.get("duraci_n_del_contrato") for c in contratos),
            COL_DIAS_ADIC: _sum(c.get("dias_adicionados") for c in contratos),
            COL_FECHA_FIRMA: _join_dates(c.get("fecha_de_firma") for c in contratos),
            COL_FECHA_INICIO: _join_dates(c.get("fecha_de_inicio_del_contrato") for c in contratos),
            COL_FECHA_FIN: _join_dates(c.get("fecha_de_fin_del_contrato") for c in contratos),
            COL_LIQUIDACION: _join_unique(c.get("liquidaci_n") for c in contratos),
            COL_FECHA_INI_LIQ: _join_dates(c.get("fecha_inicio_liquidacion") for c in contratos),
            COL_FECHA_FIN_LIQ: _join_dates(c.get("fecha_fin_liquidacion") for c in contratos),
            COL_SUPERVISOR: _join_unique(c.get("nombre_supervisor") for c in contratos),
            COL_ORDENADOR_GASTO: _join_unique(c.get("nombre_ordenador_del_gasto") for c in contratos),
            COL_ORIGEN_RECURSOS: _join_unique(c.get("origen_de_los_recursos") for c in contratos),
            COL_PRORROGABLE: _join_unique(c.get("el_contrato_puede_ser_prorrogado") for c in contratos),
            COL_RAMA: _join_unique(c.get("rama") for c in contratos),
            COL_SECTOR: _join_unique(c.get("sector") for c in contratos),
            COL_EXTRAS: _format_extras(contratos),
        }
        return ExtractionResult(values=values, ok=True)


def _empty() -> dict[str, Any]:
    return {col: "" for col in ContratoFullExtractor.output_columns}


def _sum(values) -> int | float | str:
    total = 0.0
    found = False
    for v in values:
        if v is None or v == "":
            continue
        try:
            total += float(str(v).replace(",", ""))
            found = True
        except (ValueError, TypeError):
            pass
    if not found:
        return ""
    return int(total) if total.is_integer() else total


def _join_unique(values) -> str:
    seen = []
    for v in values:
        if v is None or v == "" or v in ("No definido", "No Definido"):
            continue
        s = str(v).strip()
        if s and s not in seen:
            seen.append(s)
    return " | ".join(seen)


def _join_dates(values) -> str:
    return _join_unique(str(v)[:10] if v else "" for v in values)


def _format_extras(contratos: list[dict]) -> str:
    """Per-contract catch-all: all non-empty fields not in _EXPLICIT_FIELDS."""
    parts: list[str] = []
    for c in contratos:
        for k in sorted(c.keys()):
            if k in _EXPLICIT_FIELDS or k.startswith("_"):
                continue
            v = c[k]
            if v is None or v == "" or v in ("No definido", "No Definido", "0", 0):
                continue
            if isinstance(v, dict):
                v = v.get("url") or str(v)
            text = str(v).replace("\n", " ").replace("|", " ")
            parts.append(f"{k}={text[:60]}")
    return " | ".join(parts)[:2000]


__all__ = ["ContratoFullExtractor"]
