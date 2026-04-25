"""Cross-check API (Socrata) vs Portal (OpportunityDetail) + internal consistency.

When ``--mirror-portal`` is on we end up with two independent reads of the
same fact for many fields: one from the Socrata open-data datasets, one
from the public portal HTML. Most of the time they agree. When they don't,
the user wants to know — that's exactly the "fila 33 NO LEG" case where
the API was lagging behind the portal by ~24 hours.

On top of that, we also cross-check **internal consistency** of the API
data itself — e.g. the proceso's adjudicated supplier should match the
contract's supplier; the proceso's valor_total_adjudicacion should be
close to the contract's valor_del_contrato; firma/inicio/fin dates must
be monotonic.

All comparisons are tolerant-by-default: short strings use Jaro-Winkler
similarity (handles "MENDOZA" vs "MENDOSA"); money uses 1% tolerance for
rounding; dates are parsed through ``dateparser`` so "6/03/2024" vs
"2024-03-06" doesn't raise a false flag.

The functions here are pure (no I/O), take the merged ``combined_values``
dict that the orchestrator builds row-by-row, and return a list of
human-readable discrepancy strings.
"""

from __future__ import annotations

import re
from typing import Any

try:
    import jellyfish  # type: ignore[import-not-found]
    _HAS_JELLYFISH = True
except ImportError:  # pragma: no cover
    _HAS_JELLYFISH = False

try:
    import dateparser  # type: ignore[import-not-found]
    _HAS_DATEPARSER = True
except ImportError:  # pragma: no cover
    _HAS_DATEPARSER = False


# Cross-source: fields where we have both an API-derived column and a
# Portal-derived column and want to confirm they agree.
_PAIRS_API_VS_PORTAL = (
    ("Fase en SECOP", "Portal: Fase", "exact_ci"),
    ("Valor estimado", "Portal: Precio estimado", "money"),
    ("Entidad en SECOP", "Portal: Título", "skip"),  # different fields
    ("# modificatorios", "Portal: # notificaciones", "mods_count"),
    ("Proceso: Modalidad", "Portal: Modalidad", "exact_ci"),
    ("Proceso: Valor adjudicación", "Portal: Precio estimado", "money_soft"),
)

# Internal consistency: columns populated from different Socrata datasets
# that should agree because they describe the same fact.
_PAIRS_API_INTERNAL = (
    ("Proceso: Nombre proveedor adjudicado", "Contrato: Proveedor adjudicado", "fuzzy_name"),
    ("Proceso: NIT proveedor adjudicado", "Contrato: NIT/doc proveedor", "nit"),
    ("Proceso: Valor adjudicación", "Contrato: Valor", "money"),
)

# Date monotonicity: firma ≤ inicio ≤ fin. Violations mean corrupt dates.
_DATE_ORDER = (
    "Contrato: Fecha firma",
    "Contrato: Fecha inicio",
    "Contrato: Fecha fin",
)

COL_DISCREPANCIAS = "Audit: Discrepancias API vs Portal"


def detect_discrepancies(values: dict[str, Any]) -> str:
    """Return a human-readable discrepancy list (empty string if all clear)."""
    issues: list[str] = []

    # 1) API vs Portal
    for api_col, portal_col, kind in _PAIRS_API_VS_PORTAL:
        api_v = values.get(api_col)
        portal_v = values.get(portal_col)
        if kind == "skip":
            continue
        # Honest skip: only when truly absent (None or empty string). A
        # legitimate ``0`` (e.g. "# modificatorios = 0") MUST be compared.
        if api_v in (None, "") or portal_v in (None, ""):
            continue
        msg = _compare(api_col, api_v, portal_col, portal_v, kind)
        if msg:
            issues.append(msg)

    # 2) Internal consistency (proceso vs contrato, same source)
    for a_col, b_col, kind in _PAIRS_API_INTERNAL:
        a_v = values.get(a_col)
        b_v = values.get(b_col)
        if a_v in (None, "") or b_v in (None, ""):
            continue
        msg = _compare(a_col, a_v, b_col, b_v, kind)
        if msg:
            issues.append(msg)

    # 3) Date monotonicity
    dates = [(c, _parse_date(values.get(c))) for c in _DATE_ORDER]
    prev_col, prev_val = None, None
    for col, val in dates:
        if val is None:
            continue
        if prev_val is not None and val < prev_val:
            issues.append(
                f"Fechas fuera de orden: {prev_col}={prev_val} > {col}={val}"
            )
        prev_col, prev_val = col, val

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
    elif kind == "money_soft":
        # Soft money check for adjudicación vs precio_estimado: the two
        # are related but not required to match exactly (estimado is a
        # budget, adjudicación is what was actually awarded). Only flag
        # when they differ by >20% — suggests data entry error.
        a = _parse_money(api_v)
        b = _parse_money(portal_v)
        if a is None or b is None or b == 0:
            return ""
        if abs(a - b) / b > 0.20:
            return f"{api_col}: API=${a:,.0f} vs Portal=${b:,.0f} (>20% desvío)"
    elif kind == "fuzzy_name":
        a = _norm(str(api_v))
        b = _norm(str(portal_v))
        if not a or not b:
            return ""
        similarity = _name_similarity(a, b)
        if similarity < 0.85:
            return (
                f"{api_col} ≠ {portal_col}: '{api_v}' vs '{portal_v}' "
                f"(similitud {similarity:.0%})"
            )
    elif kind == "nit":
        a = _clean_nit(api_v)
        b = _clean_nit(portal_v)
        if not a or not b:
            return ""
        # NIT of proveedor in contrato row comes prefixed with "NIT:"
        # sometimes; both sides compared after cleaning.
        if a != b and not (a in b or b in a):
            return f"{api_col} ≠ {portal_col}: '{api_v}' vs '{portal_v}'"
    return ""


def _name_similarity(a: str, b: str) -> float:
    """Jaro-Winkler on normalized names; falls back to exact if jellyfish absent."""
    if _HAS_JELLYFISH:
        return float(jellyfish.jaro_winkler_similarity(a, b))
    return 1.0 if a == b else 0.0


def _clean_nit(value: Any) -> str:
    """Strip prefixes ("NIT:"), spaces and dashes from a NIT-like string."""
    if value is None:
        return ""
    s = re.sub(r"[^\d]", "", str(value))
    return s.lstrip("0")  # some sources prepend zeros


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


def _parse_date(value: Any):
    """Parse any reasonable date format to a comparable YYYY-MM-DD string.

    Uses dateparser when available (handles Spanish "6 de marzo de 2024")
    and falls back to a crude prefix match. Returns None when the input
    can't be read as a date.
    """
    if value is None or value == "":
        return None
    s = str(value).strip()
    # Reject noisy cells ("|"-joined lists — take the first segment only)
    if "|" in s:
        s = s.split("|", 1)[0].strip()
    if _HAS_DATEPARSER:
        try:
            parsed = dateparser.parse(s, languages=["es", "en"])
            if parsed:
                return parsed.date().isoformat()
        except Exception:
            pass
    # Fallback: YYYY-MM-DD prefix — the Socrata timestamp format
    m = re.match(r"(\d{4}-\d{2}-\d{2})", s)
    return m.group(1) if m else None


__all__ = ["detect_discrepancies", "COL_DISCREPANCIAS"]
