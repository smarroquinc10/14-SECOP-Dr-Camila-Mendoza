"""Parse the free-text ``OBSERVACIONES`` column from the Dra.'s Excel.

FEAB administers régimen especial contracts. Some modificatorios (prórrogas,
adiciones, cesiones) are signed but **not legalized through SECOP II** — they
get published on the FGN's own web site instead. The Dra. tracks those by
hand in the OBSERVACIONES column with markers like:

* ``MODIFICATORIO No 1 PRORROGA POR 1 AÑO Y VALOR. NO LEG``
* ``MODIFICATORIO NO 1 PRRROGA POR 1 AÑO Y VALOR. NO LEG``
* ``PUBLICADO EN PÁGINA WEB FGN``

The ``NO LEG`` marker means "not legalized in SECOP". For those rows the
Socrata API will report zero modificatorios — which would be **misleading**
because the modification really exists, just outside SECOP.

This module reads OBSERVACIONES **read-only** and surfaces two signals per
row so the final Excel is honest:

* ``Modificatorio en OBS`` — ``Sí`` / ``No`` — did the Dra.'s note mention
  a modificatorio that the API might not show?
* ``NO LEG`` — ``Sí`` / ``No`` — is the ``NO LEG`` marker present?

The column is never written to.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

# Keywords that, when present in OBSERVACIONES, indicate the Dra. documented
# a modificatorio by hand. We match a normalized (accent-stripped, uppercase)
# version of the text so "PRÓRROGA" and "PRORROGA" both count.
_MOD_KEYWORDS = (
    "MODIFICATORIO",
    "MODIFICACION",
    "PRORROGA",
    "ADICION",
    "OTROSI",
    "OTRO SI",
    "SUSPENSION",
    "CESION",
    "AMPLIACION",
    "REAJUSTE",
)

_NO_LEG_RE = re.compile(r"\bNO\s*LEG\b", re.IGNORECASE)

COL_MOD_EN_OBS = "Modificatorio en OBS"
COL_NO_LEG = "NO LEG"
COL_MENCIONES_OBS = "Menciones en OBS"

OUTPUT_COLUMNS = (COL_MOD_EN_OBS, COL_NO_LEG, COL_MENCIONES_OBS)

OBS_HEADER_HINTS = ("OBSERVACIONES", "OBSERVACION")


def detect_observaciones_column(ws, header_row: int = 1) -> int | None:
    """Return the 1-based column index of OBSERVACIONES or ``None``."""
    for cell in ws[header_row]:
        value = cell.value
        if not value:
            continue
        header_normalized = _normalize(str(value))
        for hint in OBS_HEADER_HINTS:
            if hint in header_normalized:
                return cell.column
    return None


def parse_observaciones(text: str | None) -> dict[str, Any]:
    """Return ``{Modificatorio en OBS, NO LEG, Menciones en OBS}`` for a cell."""
    if not text:
        return {COL_MOD_EN_OBS: "", COL_NO_LEG: "", COL_MENCIONES_OBS: ""}

    normalized = _normalize(text)
    hits = [kw for kw in _MOD_KEYWORDS if kw in normalized]
    # "PRORROGA" is a substring of "PRORROGADOR" etc — uncommon but be safe.
    hits = [h for h in hits if re.search(rf"\b{h}", normalized)]
    no_leg = bool(_NO_LEG_RE.search(text))

    return {
        COL_MOD_EN_OBS: "Sí" if hits else "No",
        COL_NO_LEG: "Sí" if no_leg else "No",
        COL_MENCIONES_OBS: "; ".join(sorted(set(hits)))[:200],
    }


def _normalize(text: str) -> str:
    """Uppercase + strip accents (so PRÓRROGA == PRORROGA)."""
    decomposed = unicodedata.normalize("NFD", text)
    without_accents = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return without_accents.upper()


__all__ = [
    "COL_MOD_EN_OBS",
    "COL_NO_LEG",
    "COL_MENCIONES_OBS",
    "OUTPUT_COLUMNS",
    "detect_observaciones_column",
    "parse_observaciones",
]
