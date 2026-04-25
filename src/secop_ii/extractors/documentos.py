"""Pull and classify the documents published for a process.

This extractor uses **only** the open-data datasets — ``dmgg-8hin``,
``3skv-9na7``, ``kgcd-kt7i`` — which list every document Colombia Compra
publishes for a process, indexed by ``id_del_portafolio`` (CO1.BDOS.*).
The download URLs they expose (``Public/Archive/RetrieveFile/Index?...``)
are reachable via plain HTTP — no captcha, no browser. So this is the
"SPOA-equivalent" for SECOP II's document layer: pure backend, fast.

Documents are classified by filename pattern so the Excel can show counts
of each kind (modificatorios, legalizaciones, actas, informes, pliegos)
without the user opening any PDF.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from secop_ii.config import (
    FIELD_ARCHIVO_FECHA,
    FIELD_ARCHIVO_NOMBRE,
    FIELD_ARCHIVO_TAMANO,
    FIELD_CONTRATO_ID,
)
from secop_ii.extractors.base import ExtractionResult, ProcessContext

COL_DOCS_TOTAL = "Docs: Total"
COL_DOCS_MOD = "Docs: # Modificatorios"
COL_DOCS_LEG = "Docs: # Legalizaciones"
COL_DOCS_ACTA = "Docs: # Actas"
COL_DOCS_INFORME = "Docs: # Informes supervisión"
COL_DOCS_PLIEGO = "Docs: # Pliegos/anexos"
COL_DOCS_OTROS = "Docs: # Otros"
COL_DOCS_MOD_LIST = "Docs: Lista modificatorios"
COL_DOCS_LEG_LIST = "Docs: Lista legalizaciones"
COL_DOCS_FUENTE = "Docs: Estado scraping"


# Classification rules: keyword (in normalized filename) → category.
# Order matters — the FIRST match wins (so "LEGALIZACION MOD" is "Legalización", not "Modificatorio").
_RULES = (
    ("legalizacion", "legalizaciones", ("LEGALIZAC", "LEGALIZADO")),
    ("modificatorios", "modificatorios", (
        "MODIFICATORIO", "MODIFICACION", "OTROSI", "OTRO SI", "PRORROGA",
        "PRÓRROGA", "ADICION", "ADIClON", "CESION", "SUSPENSION",
    )),
    ("actas", "actas", ("ACTA",)),
    ("informes", "informes", ("INFORME",)),
    ("pliegos", "pliegos", (
        "PLIEGO", "ANEXO", "ESTUDIO PREVIO", "MATRIZ DE RIESGO",
        "MANIFESTAC", "ESTUDIO DEL SECTOR", "INVITACION", "INVITACIÓN",
    )),
)


@dataclass
class DocumentosExtractor:
    """Counts + lists of published documents per category."""

    name: str = "documentos"
    output_columns: tuple[str, ...] = (
        COL_DOCS_TOTAL,
        COL_DOCS_MOD,
        COL_DOCS_LEG,
        COL_DOCS_ACTA,
        COL_DOCS_INFORME,
        COL_DOCS_PLIEGO,
        COL_DOCS_OTROS,
        COL_DOCS_MOD_LIST,
        COL_DOCS_LEG_LIST,
        COL_DOCS_FUENTE,
    )

    def extract(self, ctx: ProcessContext) -> ExtractionResult:
        try:
            proceso = ctx.proceso()
        except Exception as exc:  # pragma: no cover
            return ExtractionResult(
                values=_empty(estado=f"error: {str(exc)[:80]}"),
                ok=False,
                error=str(exc),
            )
        if proceso is None:
            return ExtractionResult(
                values=_empty(estado="proceso_no_encontrado"),
                ok=False,
                error="proceso no encontrado en API",
            )

        portfolio_id = proceso.get("id_del_portafolio")
        if not portfolio_id:
            return ExtractionResult(
                values=_empty(estado="sin_id_portafolio"),
                ok=False,
                error="proceso sin id_del_portafolio",
            )

        try:
            archivos = ctx.client.get_archivos(str(portfolio_id))
        except Exception as exc:
            return ExtractionResult(
                values=_empty(estado=f"error: {str(exc)[:80]}"),
                ok=False,
                error=str(exc),
            )

        # Bucket by category; each archivo lands in exactly one bucket.
        buckets: dict[str, list[dict]] = {
            "legalizaciones": [],
            "modificatorios": [],
            "actas": [],
            "informes": [],
            "pliegos": [],
            "otros": [],
        }
        for arc in archivos:
            name = (arc.get(FIELD_ARCHIVO_NOMBRE) or "").strip()
            cat = _classify(name)
            buckets[cat].append(arc)

        values: dict[str, Any] = {
            COL_DOCS_TOTAL: len(archivos),
            COL_DOCS_MOD: len(buckets["modificatorios"]),
            COL_DOCS_LEG: len(buckets["legalizaciones"]),
            COL_DOCS_ACTA: len(buckets["actas"]),
            COL_DOCS_INFORME: len(buckets["informes"]),
            COL_DOCS_PLIEGO: len(buckets["pliegos"]),
            COL_DOCS_OTROS: len(buckets["otros"]),
            COL_DOCS_MOD_LIST: _format_list(buckets["modificatorios"])[:500],
            COL_DOCS_LEG_LIST: _format_list(buckets["legalizaciones"])[:500],
            COL_DOCS_FUENTE: "ok",
        }
        return ExtractionResult(values=values, ok=True)


def _empty(estado: str) -> dict[str, Any]:
    return {
        COL_DOCS_TOTAL: "",
        COL_DOCS_MOD: "",
        COL_DOCS_LEG: "",
        COL_DOCS_ACTA: "",
        COL_DOCS_INFORME: "",
        COL_DOCS_PLIEGO: "",
        COL_DOCS_OTROS: "",
        COL_DOCS_MOD_LIST: "",
        COL_DOCS_LEG_LIST: "",
        COL_DOCS_FUENTE: estado,
    }


def _classify(filename: str) -> str:
    """Return the category bucket for a document filename."""
    if not filename:
        return "otros"
    norm = _normalize(filename)
    for _key, bucket, kws in _RULES:
        for kw in kws:
            if _normalize(kw) in norm:
                return bucket
    return "otros"


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn").upper()


def _format_list(items: list[dict]) -> str:
    """Compact "name (date)" listing, sorted by fecha desc."""
    rows = []
    for it in items:
        nm = (it.get(FIELD_ARCHIVO_NOMBRE) or "").strip()
        fc = (it.get(FIELD_ARCHIVO_FECHA) or "")[:10]
        rows.append((fc, nm))
    rows.sort(reverse=True)  # newest first
    return " | ".join(f"{nm} ({fc})" if fc else nm for fc, nm in rows[:8])


__all__ = ["DocumentosExtractor"]
