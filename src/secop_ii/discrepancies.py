"""Cross-check API (Socrata) vs Portal (OpportunityDetail) values.

When ``--mirror-portal`` is on we end up with two independent reads of the
same fact for many fields: one from the Socrata open-data datasets, one
from the public portal HTML. Most of the time they agree. When they don't,
the user wants to know — that's exactly the "fila 33 NO LEG" case where
the API was lagging behind the portal by ~24 hours.

The functions in this module are pure (no I/O), take the merged
``combined_values`` dict that the orchestrator builds row-by-row, and
return a list of human-readable discrepancy strings. We never modify the
underlying values; if there's a mismatch the user sees both and decides.
"""

from __future__ import annotations

import re
from typing import Any

# Excel columns we cross-check. Each tuple is ``(API column, Portal column,
# kind)`` where kind drives the comparison strategy.
_PAIRS = (
    ("Fase en SECOP", "Portal: Fase", "exact_ci"),
    ("Valor estimado", "Portal: Precio estimado", "money"),
    ("Entidad en SECOP", "Portal: Título", "skip"),  # portal title isn't entidad — different fields
    ("# modificatorios", "Portal: # notificaciones", "mods_count"),
)

COL_DISCREPANCIAS = "Audit: Discrepancias API vs Portal"


def detect_discrepancies(values: dict[str, Any]) -> str:
    """Return a human-readable discrepancy list (empty string if all clear)."""
    issues: list[str] = []

    for api_col, portal_col, kind in _PAIRS:
        api_v = values.get(api_col)
        portal_v = values.get(portal_col)
        if kind == "skip":
            continue
        # Honest skip: only when truly absent (None or empty string). A
        # legitimate ``0`` (e.g. "# modificatorios = 0") MUST be compared,
        # otherwise we'd silently miss the "API says 0, Portal has many"
        # case which is the most important discrepancy.
        if api_v in (None, "") or portal_v in (None, ""):
            continue
        msg = _compare(api_col, api_v, portal_col, portal_v, kind)
        if msg:
            issues.append(msg)

    return " | ".join(issues)


def _compare(api_col: str, api_v: Any, portal_col: str, portal_v: Any, kind: str) -> str:
    if kind == "exact_ci":
        a = _norm(str(api_v))
        b = _norm(str(portal_v))
        if a != b:
            return f"{api_col}: API='{api_v}' vs Portal='{portal_v}'"
    elif kind == "money":
        a = _parse_money(api_v)
        b = _parse_money(portal_v)
        if a is None or b is None:
            return ""
        if b == 0:
            return ""
        # 1% tolerance accounts for COP-vs-USD rounding and whitespace differences
        if abs(a - b) / b > 0.01:
            return f"{api_col}: API=${a:,.0f} vs Portal=${b:,.0f}"
    elif kind == "mods_count":
        a = _safe_int(api_v)
        b = _safe_int(portal_v)
        # Notificaciones include the original publication + every modification
        # publication. So if API says 0 mods and portal has >1 notifications,
        # SECOP probably published a modification that hasn't reached Socrata.
        if a == 0 and b > 1:
            return f"API: 0 modificatorios; Portal: {b} notificaciones (¿API atrasado?)"
    return ""


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).lower()


def _parse_money(value: Any) -> float | None:
    """Parse a money string regardless of locale formatting.

    Handles:
      * Plain numbers (int/float): ``88284000`` or ``88284000.0`` → 88284000.0
      * Colombian thousands: ``"88.284.000"`` (multiple dots) → 88284000.0
      * Colombian + decimal: ``"1.234.567,89"`` → 1234567.89
      * US thousands+decimal: ``"1,234,567.89"`` → 1234567.89
      * With currency: ``"$ 88.284.000 COP"`` → 88284000.0

    The trick is to count how many dots and commas appear and decide which
    is the decimal separator vs thousands separator. A single dot in a
    "looks like decimal" context (like ``88284000.0``) must be preserved.
    """
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value)
    # Strip currency markers and whitespace.
    s = re.sub(r"[\$\s]|COP", "", s, flags=re.I)
    if not s:
        return None

    n_dots = s.count(".")
    n_commas = s.count(",")

    if n_dots > 1 and n_commas == 0:
        # "88.284.000" — Colombian thousands without decimal
        s = s.replace(".", "")
    elif n_dots > 1 and n_commas == 1:
        # "1.234.567,89" — Colombian thousands + decimal
        s = s.replace(".", "").replace(",", ".")
    elif n_commas > 1 and n_dots == 1:
        # "1,234,567.89" — US thousands + decimal
        s = s.replace(",", "")
    elif n_commas > 1 and n_dots == 0:
        # "88,284,000" — US thousands without decimal
        s = s.replace(",", "")
    elif n_commas == 1 and n_dots == 0:
        # Could be Colombian decimal "12,5" OR US thousands "1,200".
        # Heuristic: if exactly 3 digits follow the comma → thousands.
        if re.search(r",\d{3}$", s):
            s = s.replace(",", "")
        else:
            s = s.replace(",", ".")
    # n_dots == 1 with no commas: it's a decimal point — leave it alone.
    # n_dots == 0 and n_commas == 0: pure digits — leave it alone.

    try:
        return float(s)
    except ValueError:
        return None


def _safe_int(value: Any) -> int:
    if value is None or value == "":
        return 0
    try:
        return int(float(str(value).replace(",", "")))
    except (ValueError, TypeError):
        return 0


__all__ = ["detect_discrepancies", "COL_DISCREPANCIAS"]
