"""Resolve SECOP II ``CO1.PPI.*`` pivot URLs to their ``CO1.NTC.*`` notice ID.

SECOP II public portal URLs come in two flavors:

* ``/Public/Tendering/OpportunityDetail/Index?noticeUID=CO1.NTC.XXXX`` — the
  canonical *notice* URL. This is the one stored in the ``urlproceso`` field
  of the ``p6dx-8zbt`` open-data dataset.
* ``/Public/Tendering/ContractNoticePhases/View?PPI=CO1.PPI.XXXX`` — a *pivot*
  page that lists each phase of a procurement with a link to its
  corresponding notice URL. The ``CO1.PPI.*`` token is **not** stored in the
  open-data dataset, so we can't query by it directly.

Entities like FEAB (Fondo Especial de la Fiscalía) publish their links using
the pivot URL. To match those rows against the API, we fetch the pivot page
once, extract the first ``CO1.NTC.*`` token and cache it on disk so repeated
runs never hit the portal again for the same PPI.

The scrape is intentionally minimal — ``requests`` + a browser User-Agent is
enough; the portal serves the phase links inline in the HTML. This keeps the
.exe build lightweight (no Playwright / Chromium).
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from dataclasses import dataclass, field

from secop_ii.paths import state_path
from pathlib import Path

import requests

log = logging.getLogger(__name__)

_NTC_RE = re.compile(r"CO1\.NTC\.\d+")
_PPI_IN_URL_RE = re.compile(r"PPI=(CO1\.PPI\.\d+)", re.IGNORECASE)

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
    "Accept-Language": "es-CO,es;q=0.9,en;q=0.8",
}


@dataclass
class NoticeResolver:
    """Map ``CO1.PPI.*`` pivot URLs to ``CO1.NTC.*`` notice IDs (cached)."""

    cache_path: Path = field(default_factory=lambda: state_path("ppi_ntc.json"))
    min_interval_s: float = 1.0
    timeout_s: int = 20
    _cache: dict[str, str | None] = field(default_factory=dict, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _last_request_at: float = field(default=0.0, init=False, repr=False)
    _loaded: bool = field(default=False, init=False, repr=False)

    def resolve(self, ppi_url: str) -> str | None:
        """Return the ``CO1.NTC.*`` notice id embedded in the pivot page.

        ``None`` is returned when the URL doesn't look like a PPI pivot, when
        the page has no NTC link, or when the network call fails.
        """
        ppi_token = _extract_ppi(ppi_url)
        if not ppi_token:
            return None

        self._ensure_loaded()

        if ppi_token in self._cache:
            return self._cache[ppi_token]

        ntc = self._fetch_ntc(ppi_url)
        # Cache both hits and misses so we don't retry a broken URL every run.
        self._cache[ppi_token] = ntc
        self._flush()
        return ntc

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _fetch_ntc(self, url: str) -> str | None:
        self._respect_rate()
        try:
            resp = requests.get(url, headers=_BROWSER_HEADERS, timeout=self.timeout_s)
        except requests.RequestException as exc:
            log.warning("PPI pivot fetch falló %s: %s", url, exc)
            return None
        if resp.status_code != 200:
            log.warning("PPI pivot %s -> HTTP %s", url, resp.status_code)
            return None
        match = _NTC_RE.search(resp.text)
        if not match:
            log.info("No se encontró CO1.NTC.* en %s", url)
            return None
        return match.group(0)

    def _respect_rate(self) -> None:
        with self._lock:
            gap = time.monotonic() - self._last_request_at
            if gap < self.min_interval_s:
                time.sleep(self.min_interval_s - gap)
            self._last_request_at = time.monotonic()

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        try:
            raw = self.cache_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return
        except OSError as exc:
            log.warning("No pude leer caché PPI %s: %s", self.cache_path, exc)
            return
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            log.warning("Caché PPI %s corrupta; ignorada", self.cache_path)
            return
        if isinstance(data, dict):
            self._cache.update(data)

    def _flush(self) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(
                json.dumps(self._cache, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        except OSError as exc:
            log.warning("No pude escribir caché PPI %s: %s", self.cache_path, exc)


def _extract_ppi(url: str) -> str | None:
    if not url:
        return None
    match = _PPI_IN_URL_RE.search(url)
    if match:
        return match.group(1)
    return None


__all__ = ["NoticeResolver"]
