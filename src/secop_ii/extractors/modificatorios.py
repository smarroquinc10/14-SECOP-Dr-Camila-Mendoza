"""Detect whether a SECOP II process has had any "modificatorio".

The meaning of "modificatorio" depends on where the process is:

* **Before a contract exists** (process still in bidding / evaluation):
  modificatorios are *adendas* published against the tender documents.
  These live on the Procesos dataset (``p6dx-8zbt``) in the ``adendas``
  field, which is a free-text / list string.

* **After a contract is signed**: modificatorios include adiciones (extra
  money), prórrogas (extra time), otrosíes, suspensiones and cesiones.
  These live on the Adiciones dataset (``cb9c-h8sn``) linked to the
  contract, and the Contratos dataset (``jbjy-vk9h``) carries aggregate
  fields like ``valor_pagado_adiciones`` and ``dias_adicionados``.

This extractor combines both sources so a single "Sí/No" answer works
regardless of the process phase.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from secop_ii.config import (
    FIELD_ADICION_DESCRIPCION,
    FIELD_ADICION_FECHA,
    FIELD_ADICION_TIPO,
    FIELD_ADICION_VALOR,
    FIELD_CONTRATO_ADICIONES_DIAS,
    FIELD_CONTRATO_ADICIONES_PESOS,
    FIELD_CONTRATO_ID,
    FIELD_PROCESO_ADENDAS,
)
from secop_ii.extractors.base import ExtractionResult, ProcessContext

COL_TIENE = "¿Hubo modificatorio?"
COL_CANTIDAD = "# modificatorios"
COL_TIPOS = "Tipos de modificatorio"
COL_DETALLE = "Detalle modificatorios"
COL_FECHA_ULTIMO = "Fecha último modificatorio"
COL_FUENTE = "Fuente modificatorio"


@dataclass
class ModificatoriosExtractor:
    """V1 extractor: summarizes modificatorios for a process."""

    name: str = "modificatorios"
    output_columns: tuple[str, ...] = (
        COL_TIENE,
        COL_CANTIDAD,
        COL_TIPOS,
        COL_DETALLE,
        COL_FECHA_ULTIMO,
        COL_FUENTE,
    )

    def extract(self, ctx: ProcessContext) -> ExtractionResult:
        try:
            proceso = ctx.proceso()
        except Exception as exc:  # pragma: no cover - defensive
            return ExtractionResult(
                values=_empty_values(estado="error: " + str(exc)[:120]),
                ok=False,
                error=str(exc),
            )

        if proceso is None:
            return ExtractionResult(
                values=_empty_values(estado="no_encontrado"),
                ok=False,
                error="Proceso no encontrado en el dataset de SECOP II",
            )

        try:
            contratos = ctx.contratos()
        except Exception as exc:  # pragma: no cover
            contratos = []

        adendas_count, adendas_detail = _parse_adendas(
            proceso.get(FIELD_PROCESO_ADENDAS)
        )

        adiciones: list[dict] = []
        for c in contratos:
            cid = c.get(FIELD_CONTRATO_ID)
            if not cid:
                continue
            try:
                adiciones.extend(ctx.adiciones_de(str(cid)))
            except Exception:  # pragma: no cover
                continue

        aggregate_pesos = sum(_as_float(c.get(FIELD_CONTRATO_ADICIONES_PESOS)) for c in contratos)
        aggregate_dias = sum(_as_int(c.get(FIELD_CONTRATO_ADICIONES_DIAS)) for c in contratos)

        tipos = sorted({
            (a.get(FIELD_ADICION_TIPO) or "").strip()
            for a in adiciones
            if a.get(FIELD_ADICION_TIPO)
        })
        total = len(adiciones) + adendas_count
        fechas = [
            a.get(FIELD_ADICION_FECHA) for a in adiciones if a.get(FIELD_ADICION_FECHA)
        ]
        fecha_ultima = max(fechas) if fechas else ""

        hubo = total > 0 or aggregate_pesos > 0 or aggregate_dias > 0
        fuente = _pick_source(len(adiciones), adendas_count)

        detalle_parts: list[str] = []
        if adendas_count:
            detalle_parts.append(f"{adendas_count} adenda(s) al pliego")
        for a in adiciones[:10]:  # cap detail to keep the cell readable
            tipo = a.get(FIELD_ADICION_TIPO) or "modificación"
            desc = (a.get(FIELD_ADICION_DESCRIPCION) or "").strip()
            valor = _as_float(a.get(FIELD_ADICION_VALOR))
            chunk = tipo
            if valor:
                chunk += f" (${valor:,.0f})"
            if desc:
                chunk += f" — {desc[:120]}"
            detalle_parts.append(chunk)
        if len(adiciones) > 10:
            detalle_parts.append(f"… y {len(adiciones) - 10} más")
        if not detalle_parts and adendas_detail:
            detalle_parts.append(adendas_detail[:240])

        values: dict[str, Any] = {
            COL_TIENE: "Sí" if hubo else "No",
            COL_CANTIDAD: total,
            COL_TIPOS: "; ".join(tipos) if tipos else ("Adenda" if adendas_count else ""),
            COL_DETALLE: " | ".join(detalle_parts)[:500],
            COL_FECHA_ULTIMO: fecha_ultima,
            COL_FUENTE: fuente,
        }
        return ExtractionResult(values=values, ok=True)


def _empty_values(estado: str) -> dict[str, Any]:
    return {
        COL_TIENE: "",
        COL_CANTIDAD: "",
        COL_TIPOS: "",
        COL_DETALLE: estado,
        COL_FECHA_ULTIMO: "",
        COL_FUENTE: "",
    }


_ADENDA_SPLIT = re.compile(r"[;\n\r]+")


def _parse_adendas(raw: Any) -> tuple[int, str]:
    """Return ``(count, first_chunk)`` for the ``adendas`` field."""
    if not raw:
        return 0, ""
    text = str(raw).strip()
    if not text or text.lower() in {"no", "n/a", "ninguna", "ninguno"}:
        return 0, ""
    chunks = [c.strip() for c in _ADENDA_SPLIT.split(text) if c.strip()]
    return len(chunks), text


def _as_float(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(str(value).replace(",", ""))
    except (ValueError, TypeError):
        return 0.0


def _as_int(value: Any) -> int:
    return int(_as_float(value))


def _pick_source(n_adiciones: int, n_adendas: int) -> str:
    parts = []
    if n_adiciones:
        parts.append(f"contrato({n_adiciones})")
    if n_adendas:
        parts.append(f"pliego({n_adendas})")
    return "+".join(parts)
