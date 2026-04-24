"""Extract SECOP II process identifiers from public portal URLs.

SECOP II urls come in several shapes. The key identifier is a token of the
form ``CO1.<kind>.<digits>`` that lives either in the query string or the
path. Known kinds observed on the public portal:

* ``NTC``     – Notice (aviso, fase de selección)
* ``PPI``     – Published process (ContractNoticePhases/View)
* ``PCCNTR``  – Contract
* ``BDOS``    – Tender document
* ``PPROC``   – Pre-proceso

The parser is tolerant: it tries known query-string keys first
(``noticeUID``, ``PPI``, ``ProcessID``, ``NoticeId``…) and falls back to a
regex search against the full URL. It also normalizes the URL (lowercase
scheme/host, drop ``isModal``/``isFromPublicArea`` tracking params) so two
copies of the same link always produce the same ``ProcessRef``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

SECOP_HOST = "community.secop.gov.co"

_ID_RE = re.compile(r"CO1\.(?P<kind>[A-Z]+)\.[0-9A-Za-z]+")

_ID_QUERY_KEYS = (
    "noticeUID",
    "noticeuid",
    "NoticeUID",
    "NoticeId",
    "noticeId",
    "PPI",
    "ppi",
    "ProcessID",
    "ProcessId",
    "processId",
    "PCCNTR",
    "pccntr",
)

_TRACKING_KEYS = {
    "ismodal",
    "isfrompublicarea",
    "currentlanguage",
    "skinname",
    "country",
    "page",
}


class InvalidSecopUrlError(ValueError):
    """Raised when a string is not a recognizable SECOP II process URL."""


@dataclass(frozen=True)
class ProcessRef:
    """Canonical reference to a SECOP II process extracted from a URL.

    Attributes:
        process_id: The full ``CO1.<kind>.<digits>`` token.
        kind: The kind portion (``NTC``, ``PPI``, ``PCCNTR``, etc.).
        source_url: The original URL the reference was extracted from.
        normalized_url: A canonical form safe to compare across copies.
    """

    process_id: str
    kind: str
    source_url: str
    normalized_url: str

    @property
    def is_notice(self) -> bool:
        return self.kind == "NTC"

    @property
    def is_contract(self) -> bool:
        return self.kind == "PCCNTR"

    @property
    def is_published_process(self) -> bool:
        return self.kind == "PPI"


def parse_secop_url(url: str) -> ProcessRef:
    """Return a :class:`ProcessRef` for ``url``.

    Raises:
        InvalidSecopUrlError: The URL does not contain a recognizable
            SECOP II identifier.
    """
    if not url or not isinstance(url, str):
        raise InvalidSecopUrlError("URL vacía o no es una cadena")

    cleaned = url.strip()
    parsed = urlparse(cleaned)
    query = parse_qs(parsed.query, keep_blank_values=False)

    # 1. Try the known query-string keys first (case-insensitive).
    lower_query = {k.lower(): v for k, v in query.items()}
    for key in _ID_QUERY_KEYS:
        value = lower_query.get(key.lower())
        if value and _ID_RE.fullmatch(value[0]):
            token = value[0]
            kind = _ID_RE.fullmatch(token).group("kind")
            return ProcessRef(token, kind, cleaned, normalize_url(cleaned))

    # 2. Fall back to searching anywhere in the URL (path or query values).
    match = _ID_RE.search(cleaned)
    if match:
        token = match.group(0)
        return ProcessRef(token, match.group("kind"), cleaned, normalize_url(cleaned))

    raise InvalidSecopUrlError(
        f"No se encontró un identificador tipo CO1.XXX.NNN en la URL: {cleaned!r}"
    )


def normalize_url(url: str) -> str:
    """Normalize a SECOP II URL so duplicates compare equal.

    - Lowercases scheme and host.
    - Drops presentational/tracking query params (``isModal``,
      ``isFromPublicArea``, ``currentLanguage``, ``SkinName``, ``Country``,
      ``Page``).
    - Preserves the identifying params in a stable order.
    """
    parsed = urlparse(url.strip())
    query_pairs = [
        (k, v[0])
        for k, v in parse_qs(parsed.query, keep_blank_values=False).items()
        if k.lower() not in _TRACKING_KEYS and v
    ]
    query_pairs.sort()
    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path,
            parsed.params,
            urlencode(query_pairs),
            "",  # drop fragment
        )
    )
