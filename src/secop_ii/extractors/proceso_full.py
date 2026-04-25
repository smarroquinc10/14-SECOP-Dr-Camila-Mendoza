"""Pull every audit-relevant field from ``p6dx-8zbt`` (procesos).

The existing :mod:`auditoria` extractor only mirrors a handful of fields
(entidad, NIT, objeto, valor base, fase, link). Socrata exposes ~50 more
columns that an auditor would normally check by hand: modalidad, tipo de
contrato, valor adjudicación, proveedor adjudicado, departamento, fechas
de fase 3, conteo de ofertas, etc.

This extractor pulls them all and prefixes every output column with
``Proceso:`` so the human can scan them as a coherent block.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from secop_ii.extractors.base import ExtractionResult, ProcessContext

COL_MODALIDAD = "Proceso: Modalidad"
COL_JUSTIF_MODALIDAD = "Proceso: Justificación modalidad"
COL_TIPO_CONTRATO = "Proceso: Tipo contrato"
COL_SUBTIPO_CONTRATO = "Proceso: Subtipo contrato"
COL_REFERENCIA = "Proceso: Referencia"
COL_NOMBRE = "Proceso: Nombre"
COL_ADJUDICADOR = "Proceso: Adjudicador"
COL_UNIDAD = "Proceso: Unidad de contratación"
COL_DEPARTAMENTO = "Proceso: Departamento entidad"
COL_CIUDAD = "Proceso: Ciudad entidad"
COL_PRECIO_BASE = "Proceso: Precio base"
COL_VALOR_ADJ = "Proceso: Valor adjudicación"
COL_NIT_PROVEEDOR = "Proceso: NIT proveedor adjudicado"
COL_NOMBRE_PROVEEDOR = "Proceso: Nombre proveedor adjudicado"
COL_DURACION = "Proceso: Duración"
COL_NUM_LOTES = "Proceso: # lotes"
COL_OFERTAS_RECIBIDAS = "Proceso: # ofertas recibidas"
COL_PROVEEDORES_INVITADOS = "Proceso: # proveedores invitados"
COL_PROVEEDORES_MANIFESTARON = "Proceso: # proveedores manifestaron"
COL_FECHA_PUBLICACION = "Proceso: Fecha publicación"
COL_FECHA_FASE3 = "Proceso: Fecha fase 3"
COL_FECHA_APERTURA = "Proceso: Fecha apertura ofertas"
COL_FECHA_ULTIMA_PUB = "Proceso: Última publicación"
COL_ID_ADJUDICACION = "Proceso: ID adjudicación"
COL_ESTADO_PROC = "Proceso: Estado"
COL_EXTRAS = "Proceso: Otros campos"

# Fields we already surface as their own column — must NOT appear again in
# the catch-all so the extras stay readable.
_EXPLICIT_FIELDS = {
    "modalidad_de_contratacion", "justificaci_n_modalidad_de",
    "tipo_de_contrato", "subtipo_de_contrato", "referencia_del_proceso",
    "nombre_del_procedimiento", "nombre_del_adjudicador",
    "nombre_de_la_unidad_de", "departamento_entidad", "ciudad_entidad",
    "precio_base", "valor_total_adjudicacion",
    "nit_del_proveedor_adjudicado", "nombre_del_proveedor",
    "duracion", "unidad_de_duracion", "numero_de_lotes",
    "respuestas_al_procedimiento", "proveedores_invitados",
    "proveedores_que_manifestaron", "fecha_de_publicacion_del",
    "fecha_de_publicacion_fase_3", "fecha_de_apertura_efectiva",
    "fecha_de_ultima_publicaci", "id_adjudicacion",
    "estado_del_procedimiento",
    # Already covered by the auditoria extractor — don't duplicate.
    "id_del_proceso", "id_del_portafolio", "urlproceso", "fase",
    "entidad", "nit_entidad", "descripci_n_del_procedimiento",
    "nombre_entidad", "ordenentidad", "codigo_entidad", "codigo_pci",
    "ppi", "id_estado_del_procedimiento",
}


@dataclass
class ProcesoFullExtractor:
    name: str = "proceso_full"
    output_columns: tuple[str, ...] = (
        COL_MODALIDAD,
        COL_JUSTIF_MODALIDAD,
        COL_TIPO_CONTRATO,
        COL_SUBTIPO_CONTRATO,
        COL_REFERENCIA,
        COL_NOMBRE,
        COL_ADJUDICADOR,
        COL_UNIDAD,
        COL_DEPARTAMENTO,
        COL_CIUDAD,
        COL_PRECIO_BASE,
        COL_VALOR_ADJ,
        COL_NIT_PROVEEDOR,
        COL_NOMBRE_PROVEEDOR,
        COL_DURACION,
        COL_NUM_LOTES,
        COL_OFERTAS_RECIBIDAS,
        COL_PROVEEDORES_INVITADOS,
        COL_PROVEEDORES_MANIFESTARON,
        COL_FECHA_PUBLICACION,
        COL_FECHA_FASE3,
        COL_FECHA_APERTURA,
        COL_FECHA_ULTIMA_PUB,
        COL_ID_ADJUDICACION,
        COL_ESTADO_PROC,
        COL_EXTRAS,
    )

    def extract(self, ctx: ProcessContext) -> ExtractionResult:
        try:
            proceso = ctx.proceso()
        except Exception as exc:  # pragma: no cover
            return ExtractionResult(values=_empty(), ok=False, error=str(exc))
        if proceso is None:
            return ExtractionResult(values=_empty(), ok=False, error="proceso no encontrado")

        values: dict[str, Any] = {
            COL_MODALIDAD: proceso.get("modalidad_de_contratacion") or "",
            COL_JUSTIF_MODALIDAD: proceso.get("justificaci_n_modalidad_de") or "",
            COL_TIPO_CONTRATO: proceso.get("tipo_de_contrato") or "",
            COL_SUBTIPO_CONTRATO: proceso.get("subtipo_de_contrato") or "",
            COL_REFERENCIA: proceso.get("referencia_del_proceso") or "",
            COL_NOMBRE: proceso.get("nombre_del_procedimiento") or "",
            COL_ADJUDICADOR: proceso.get("nombre_del_adjudicador") or "",
            COL_UNIDAD: proceso.get("nombre_de_la_unidad_de") or "",
            COL_DEPARTAMENTO: proceso.get("departamento_entidad") or "",
            COL_CIUDAD: proceso.get("ciudad_entidad") or "",
            COL_PRECIO_BASE: _num(proceso.get("precio_base")),
            COL_VALOR_ADJ: _num(proceso.get("valor_total_adjudicacion")),
            COL_NIT_PROVEEDOR: proceso.get("nit_del_proveedor_adjudicado") or "",
            COL_NOMBRE_PROVEEDOR: proceso.get("nombre_del_proveedor") or "",
            COL_DURACION: _format_duracion(
                proceso.get("duracion"), proceso.get("unidad_de_duracion")
            ),
            COL_NUM_LOTES: _num(proceso.get("numero_de_lotes")),
            COL_OFERTAS_RECIBIDAS: _num(proceso.get("respuestas_al_procedimiento")),
            COL_PROVEEDORES_INVITADOS: _num(proceso.get("proveedores_invitados")),
            COL_PROVEEDORES_MANIFESTARON: _num(proceso.get("proveedores_que_manifestaron")),
            COL_FECHA_PUBLICACION: _date(proceso.get("fecha_de_publicacion_del")),
            COL_FECHA_FASE3: _date(proceso.get("fecha_de_publicacion_fase_3")),
            COL_FECHA_APERTURA: _date(proceso.get("fecha_de_apertura_efectiva")),
            COL_FECHA_ULTIMA_PUB: _date(proceso.get("fecha_de_ultima_publicaci")),
            COL_ID_ADJUDICACION: proceso.get("id_adjudicacion") or "",
            COL_ESTADO_PROC: proceso.get("estado_del_procedimiento") or "",
            COL_EXTRAS: _format_extras(proceso),
        }
        return ExtractionResult(values=values, ok=True)


def _format_extras(proceso: dict) -> str:
    """Compact ``key=value`` listing for fields not in ``_EXPLICIT_FIELDS``."""
    parts: list[str] = []
    for k in sorted(proceso.keys()):
        if k in _EXPLICIT_FIELDS or k.startswith("_"):
            continue
        v = proceso[k]
        if v is None or v == "" or v in ("No definido", "No Definido"):
            continue
        if isinstance(v, dict):
            v = v.get("url") or str(v)
        text = str(v).replace("\n", " ").replace("|", " ")
        parts.append(f"{k}={text[:80]}")
    return " | ".join(parts)[:1500]


def _empty() -> dict[str, Any]:
    return {col: "" for col in ProcesoFullExtractor.output_columns}


def _num(value: Any) -> int | float | str:
    if value is None or value == "":
        return ""
    try:
        n = float(str(value).replace(",", ""))
        return int(n) if n.is_integer() else n
    except (ValueError, TypeError):
        return str(value)


def _date(value: Any) -> str:
    """Return YYYY-MM-DD or empty."""
    if not value:
        return ""
    return str(value)[:10]


def _format_duracion(amount: Any, unit: Any) -> str:
    if not amount:
        return ""
    return f"{amount} {unit or ''}".strip()


__all__ = ["ProcesoFullExtractor"]
