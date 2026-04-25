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

from dataclasses import dataclass
from typing import Any

from secop_ii.config import (
    FIELD_ADICION_DESCRIPCION,
    FIELD_ADICION_FECHA,
    FIELD_ADICION_TIPO,
    FIELD_CONTRATO_ADICIONES_DIAS,
    FIELD_CONTRATO_ID,
    FIELD_MODCTR_DESCRIPCION,
    FIELD_MODCTR_DIAS,
    FIELD_MODCTR_FECHA_APROB,
    FIELD_MODCTR_PROPOSITO,
    FIELD_MODCTR_VALOR,
)
from secop_ii.extractors.base import ExtractionResult, ProcessContext

COL_TIENE = "¿Hubo modificatorio?"
COL_CANTIDAD = "# modificatorios"
COL_TIPOS = "Tipos de modificatorio"
COL_DETALLE = "Detalle modificatorios"
COL_FECHA_ULTIMO = "Fecha último modificatorio"
COL_FUENTE = "Fuente modificatorio"
COL_VALOR_MOD = "Valor modificatorios"
COL_DIAS_MOD = "Días adicionados"
COL_OBS_SECOP = "Observación modificatorios SECOP II"


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
        COL_VALOR_MOD,
        COL_DIAS_MOD,
        COL_FUENTE,
        COL_OBS_SECOP,
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

        adiciones: list[dict] = []  # cb9c-h8sn — brings "tipo" (CESION, MODIFICACION GENERAL…)
        ricas: list[dict] = []  # u8cx-r425 — brings $, días extendidos, fecha aprobación, propósito
        for c in contratos:
            cid = c.get(FIELD_CONTRATO_ID)
            if not cid:
                continue
            try:
                adiciones.extend(ctx.adiciones_de(str(cid)))
            except Exception:  # pragma: no cover
                continue
            try:
                ricas.extend(ctx.modificaciones_ricas_de(str(cid)))
            except Exception:  # pragma: no cover
                continue

        # Días: prefer u8cx's per-row value; fall back to the rollup on contratos
        aggregate_dias_contrato = sum(
            _as_int(c.get(FIELD_CONTRATO_ADICIONES_DIAS)) for c in contratos
        )
        aggregate_dias_ricas = sum(_as_int(r.get(FIELD_MODCTR_DIAS)) for r in ricas)
        aggregate_dias = aggregate_dias_ricas or aggregate_dias_contrato
        aggregate_valor = sum(_as_float(r.get(FIELD_MODCTR_VALOR)) for r in ricas)

        tipos = sorted({
            (a.get(FIELD_ADICION_TIPO) or "").strip()
            for a in adiciones
            if a.get(FIELD_ADICION_TIPO)
        })
        # Count modificatorios as the UNION of both datasets (one might be
        # populated, the other empty). Cap to the larger of the two to avoid
        # double counting when both datasets describe the same mods.
        total = max(len(adiciones), len(ricas))

        # Use the richer "fecha_de_aprobacion" from u8cx when available.
        fechas = [r.get(FIELD_MODCTR_FECHA_APROB) for r in ricas if r.get(FIELD_MODCTR_FECHA_APROB)]
        fechas += [a.get(FIELD_ADICION_FECHA) for a in adiciones if a.get(FIELD_ADICION_FECHA)]
        fecha_ultima = max(fechas) if fechas else ""

        hubo = total > 0 or aggregate_dias > 0 or aggregate_valor > 0
        fuente_parts: list[str] = []
        if adiciones:
            fuente_parts.append(f"cb9c({len(adiciones)})")
        if ricas:
            fuente_parts.append(f"u8cx({len(ricas)})")
        if not fuente_parts and aggregate_dias:
            fuente_parts.append(f"+{aggregate_dias}d")
        fuente = "+".join(fuente_parts)

        detalle_parts: list[str] = []
        if aggregate_dias and not (adiciones or ricas):
            detalle_parts.append(f"{aggregate_dias} día(s) adicionados al contrato")
        # Prefer u8cx's text (proposito + descripcion + valor).
        for r in ricas[:10]:
            chunk_bits: list[str] = []
            prop = (r.get(FIELD_MODCTR_PROPOSITO) or "").strip()
            desc = (r.get(FIELD_MODCTR_DESCRIPCION) or "").strip()
            valor = _as_float(r.get(FIELD_MODCTR_VALOR))
            dias = _as_int(r.get(FIELD_MODCTR_DIAS))
            if valor:
                chunk_bits.append(f"${valor:,.0f}")
            if dias:
                chunk_bits.append(f"+{dias}d")
            if prop:
                chunk_bits.append(prop[:150])
            elif desc:
                chunk_bits.append(desc[:150])
            if chunk_bits:
                detalle_parts.append(" / ".join(chunk_bits))
        # If u8cx was empty, fall back to cb9c wording.
        if not detalle_parts:
            for a in adiciones[:10]:
                tipo = a.get(FIELD_ADICION_TIPO) or "modificación"
                desc = (a.get(FIELD_ADICION_DESCRIPCION) or "").strip()
                detalle_parts.append(f"{tipo} — {desc[:120]}" if desc else tipo)
        if total > 10:
            detalle_parts.append(f"… y {total - 10} más")

        # Narrative column — mirrors the Dra.'s hand-written OBSERVACIONES style
        # so she can read at a glance what SECOP II says about this process's
        # modificatorios.
        obs_secop = _build_obs_secop(
            tiene=hubo,
            total=total,
            tipos=tipos,
            valor=aggregate_valor,
            dias=aggregate_dias,
            fecha=fecha_ultima,
        )

        values: dict[str, Any] = {
            COL_TIENE: "Sí" if hubo else "No",
            COL_CANTIDAD: total,
            COL_TIPOS: "; ".join(tipos),
            COL_DETALLE: " | ".join(detalle_parts)[:500],
            COL_FECHA_ULTIMO: fecha_ultima,
            COL_VALOR_MOD: aggregate_valor if aggregate_valor else "",
            COL_DIAS_MOD: aggregate_dias if aggregate_dias else "",
            COL_FUENTE: fuente,
            COL_OBS_SECOP: obs_secop,
        }
        return ExtractionResult(values=values, ok=True)


def _empty_values(estado: str) -> dict[str, Any]:
    return {
        COL_TIENE: "",
        COL_CANTIDAD: "",
        COL_TIPOS: "",
        COL_DETALLE: estado,
        COL_FECHA_ULTIMO: "",
        COL_VALOR_MOD: "",
        COL_DIAS_MOD: "",
        COL_FUENTE: "",
        COL_OBS_SECOP: estado,
    }


def _build_obs_secop(
    *,
    tiene: bool,
    total: int,
    tipos: list[str],
    valor: float,
    dias: int,
    fecha: str,
) -> str:
    """Produce a one-liner that reads like a manual OBSERVACIONES entry."""
    if not tiene:
        return "Sin modificatorios registrados en SECOP II."
    plural = "modificatorios" if total != 1 else "modificatorio"
    tipos_str = (", ".join(tipos)) if tipos else "MODIFICACION"
    pieces: list[str] = [f"{total} {plural} en SECOP II ({tipos_str})"]
    if valor:
        pieces.append(f"valor acumulado ${valor:,.0f}")
    if dias:
        pieces.append(f"+{dias} día(s)")
    if fecha:
        # fecha is ISO; show date portion only for readability
        pieces.append(f"último {fecha[:10]}")
    return ". ".join(pieces)[:500]


def _as_int(value: Any) -> int:
    if value is None or value == "":
        return 0
    try:
        return int(float(str(value).replace(",", "")))
    except (ValueError, TypeError):
        return 0


def _as_float(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(str(value).replace(",", ""))
    except (ValueError, TypeError):
        return 0.0
