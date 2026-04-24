"""HTTP client for the SECOP II Socrata open-data API.

The client handles:

* App-token authentication (header ``X-App-Token``).
* Rate limiting (simple token bucket so we never exceed ``N`` requests per
  second to stay under Socrata's throttling limits).
* Retries with exponential backoff for ``429`` and ``5xx`` responses,
  honoring the ``Retry-After`` header when present.
* In-memory memoization keyed on ``(dataset_id, query_hash)`` so the same
  process is not fetched twice during a single run.

The public entry points mirror the logical concepts a caller works with:
``get_proceso``, ``get_contratos``, ``get_adiciones``. Each returns plain
``dict``/``list[dict]`` so the extractors stay decoupled from pydantic.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Iterable
from urllib.parse import quote

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from secop_ii.config import (
    DATASET_ADICIONES,
    DATASET_CONTRATOS,
    DATASET_PROCESOS,
    DEFAULT_PAGE_SIZE,
    DEFAULT_RATE_NO_TOKEN,
    DEFAULT_RATE_WITH_TOKEN,
    DEFAULT_TIMEOUT_S,
    FIELD_ADICION_CONTRATO,
    FIELD_CONTRATO_PROCESO,
    FIELD_CONTRATO_URL,
    FIELD_PROCESO_ID,
    FIELD_PROCESO_URL,
    SOCRATA_BASE,
)

log = logging.getLogger(__name__)


class RateLimiter:
    """Minimum-interval limiter shared across threads.

    We don't need a full token bucket here: SECOP II calls are serial in the
    orchestrator, but making the limiter thread-safe future-proofs the
    client for the Streamlit UI (which runs callbacks off a thread).
    """

    def __init__(self, rate_per_second: float) -> None:
        self._min_interval = 1.0 / rate_per_second if rate_per_second > 0 else 0.0
        self._last = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        if self._min_interval == 0:
            return
        with self._lock:
            now = time.monotonic()
            wait = self._min_interval - (now - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()


class SocrataError(RuntimeError):
    """Raised for non-retryable Socrata responses (4xx other than 429)."""


class _RetryableError(Exception):
    """Internal signal that a request should be retried."""


@dataclass
class SecopClient:
    """Thin wrapper around the SECOP II Socrata endpoints."""

    app_token: str | None = None
    rate_per_second: float | None = None
    timeout_s: int = DEFAULT_TIMEOUT_S
    _session: requests.Session = field(default_factory=requests.Session, repr=False)
    _cache: dict[tuple[str, str], list[dict[str, Any]]] = field(
        default_factory=dict, repr=False
    )
    _limiter: RateLimiter = field(init=False, repr=False)

    def __post_init__(self) -> None:
        rate = self.rate_per_second
        if rate is None:
            rate = (
                DEFAULT_RATE_WITH_TOKEN if self.app_token else DEFAULT_RATE_NO_TOKEN
            )
        self._limiter = RateLimiter(rate)

    # ------------------------------------------------------------------
    # Logical queries
    # ------------------------------------------------------------------
    def get_proceso(self, process_id: str, url: str | None = None) -> dict | None:
        """Return the process row for ``process_id`` or ``None``.

        Tries ``id_del_proceso = <process_id>`` first. If that misses, falls
        back to a substring match on ``urlproceso`` using the raw URL when
        provided — this catches URL variants that encode the id differently.
        """
        rows = self.query(
            DATASET_PROCESOS,
            where=f"{FIELD_PROCESO_ID}='{_escape(process_id)}'",
            limit=1,
        )
        if rows:
            return rows[0]
        if url:
            rows = self.query(
                DATASET_PROCESOS,
                where=f"{FIELD_PROCESO_URL} like '%{_escape(process_id)}%'",
                limit=1,
            )
            if rows:
                return rows[0]
        return None

    def get_contratos(self, process_id: str) -> list[dict]:
        """Return every contract row linked to ``process_id``."""
        return self.query(
            DATASET_CONTRATOS,
            where=(
                f"{FIELD_CONTRATO_PROCESO}='{_escape(process_id)}'"
                f" OR {FIELD_CONTRATO_URL} like '%{_escape(process_id)}%'"
            ),
            limit=DEFAULT_PAGE_SIZE,
        )

    def get_adiciones(self, id_contrato: str) -> list[dict]:
        """Return every modification/addition row for ``id_contrato``."""
        return self.query(
            DATASET_ADICIONES,
            where=f"{FIELD_ADICION_CONTRATO}='{_escape(id_contrato)}'",
            limit=DEFAULT_PAGE_SIZE,
        )

    # ------------------------------------------------------------------
    # Raw query
    # ------------------------------------------------------------------
    def query(
        self,
        dataset_id: str,
        *,
        where: str | None = None,
        select: str | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Execute a SoQL query against ``dataset_id`` and return rows."""
        params: dict[str, Any] = {"$limit": limit, "$offset": offset}
        if where:
            params["$where"] = where
        if select:
            params["$select"] = select

        cache_key = (dataset_id, _params_key(params))
        if cache_key in self._cache:
            return self._cache[cache_key]

        rows = self._fetch_with_retries(dataset_id, params)
        self._cache[cache_key] = rows
        return rows

    def build_query_url(
        self, dataset_id: str, *, where: str | None = None, limit: int = 10
    ) -> str:
        """Return the URL that ``query`` would hit.

        Useful for diagnostics / letting an end user click through in their
        browser when the machine can reach datos.gov.co but the server
        running the tool cannot.
        """
        parts = [f"$limit={limit}"]
        if where:
            parts.append("$where=" + quote(where, safe=""))
        return f"{SOCRATA_BASE}/{dataset_id}.json?" + "&".join(parts)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    @retry(
        retry=retry_if_exception_type(_RetryableError),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=32),
        reraise=True,
    )
    def _fetch_with_retries(self, dataset_id: str, params: dict) -> list[dict]:
        self._limiter.wait()
        headers = {"Accept": "application/json"}
        if self.app_token:
            headers["X-App-Token"] = self.app_token

        url = f"{SOCRATA_BASE}/{dataset_id}.json"
        log.debug("GET %s params=%s", url, params)
        try:
            resp = self._session.get(
                url, params=params, headers=headers, timeout=self.timeout_s
            )
        except (requests.ConnectionError, requests.Timeout) as exc:
            raise _RetryableError(f"Network error: {exc}") from exc

        if resp.status_code == 429 or 500 <= resp.status_code < 600:
            retry_after = resp.headers.get("Retry-After")
            if retry_after:
                try:
                    time.sleep(float(retry_after))
                except ValueError:
                    pass
            raise _RetryableError(
                f"Socrata responded {resp.status_code}: {resp.text[:200]}"
            )
        if resp.status_code >= 400:
            raise SocrataError(
                f"Socrata {resp.status_code} for {dataset_id}: {resp.text[:200]}"
            )
        return resp.json()


def _escape(value: str) -> str:
    """Escape a single-quoted SoQL string literal."""
    return value.replace("'", "''")


def _params_key(params: dict) -> str:
    return "&".join(f"{k}={params[k]}" for k in sorted(params))


__all__ = ["SecopClient", "SocrataError", "RateLimiter"]
