"""Scrape per-process data from SECOP II's ``OpportunityDetail`` page.

The open-data API (Socrata) covers ~95% of what the public portal shows, but a
few fields only appear on the HTML page:

* Dirección de ejecución del contrato
* Lista adicional de códigos UNSPSC
* Lotes
* Publicidad del proceso
* Documentos adjuntos (PDFs de pliegos, actas, modificatorios)

The portal gates ``OpportunityDetail`` behind a Google reCAPTCHA that Google
serves as a hard challenge to headless browsers. The pragmatic workaround:
launch visible Chrome with a *persistent* profile so cookies survive between
runs, prompt the user to solve the captcha once per 30-minute session, and
reuse the session for every contract after that.

The scraped data is cached to disk (keyed on ``CO1.NTC.*``) so a second run
doesn't re-visit contracts that already succeeded.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# patchright is a drop-in Playwright fork that strips the "Chrome is being
# controlled by automated test software" banner and hides the automation
# fingerprints Google's reCAPTCHA uses to serve a hard challenge.
try:
    from patchright.sync_api import (  # type: ignore[import]
        BrowserContext,
        Page,
        TimeoutError as PWTimeout,
        sync_playwright,
    )
except ImportError:  # fall back gracefully
    from playwright.sync_api import (  # type: ignore[import]
        BrowserContext,
        Page,
        TimeoutError as PWTimeout,
        sync_playwright,
    )

log = logging.getLogger(__name__)

OPPORTUNITY_URL = (
    "https://community.secop.gov.co/Public/Tendering/OpportunityDetail/Index"
    "?noticeUID={notice_uid}&isFromPublicArea=True&isModal=False"
)

# Fields we pull out of the HTML. Keys become Excel column suffixes.
_FIELD_LABELS = {
    "direccion_ejecucion": r"Direcci[oó]n de ejecuci[oó]n del contrato",
    "unspsc_principal": r"C[oó]digo UNSPSC",
    "unspsc_adicional": r"Lista adicional de c[oó]digos UNSPSC",
    "duracion_contrato": r"Duraci[oó]n del contrato",
    "fecha_terminacion": r"Fecha de terminaci[oó]n del contrato",
    "justificacion_modalidad": r"Justificaci[oó]n de la modalidad de contrataci[oó]n",
    "mipyme_limitacion": r"Limitaci[oó]n de todo el proceso a MiPymes",
    "lotes": r"Lotes\?",
    "dar_publicidad": r"Dar publicidad al proceso",
    "modulo_publicitario": r"Uso del m[oó]dulo de forma publicitaria",
}


@dataclass
class PortalData:
    """What we extract for a single OpportunityDetail page."""

    notice_uid: str
    fields: dict[str, str]
    documents: list[dict[str, str]]
    raw_length: int

    def as_flat(self) -> dict[str, Any]:
        out: dict[str, Any] = {f"portal_{k}": v for k, v in self.fields.items()}
        out["portal_documentos_count"] = len(self.documents)
        out["portal_documentos"] = " | ".join(
            d.get("name", "") for d in self.documents[:10]
        )[:500]
        return out


@dataclass
class PortalScraper:
    """Visible-Chrome scraper with persistent cookies and on-disk cache."""

    profile_dir: Path = field(
        default_factory=lambda: Path(
            os.environ.get("LOCALAPPDATA", str(Path.home())),
        )
        / "secop-ii-scraper"
        / "profile"
    )
    cache_path: Path = field(
        default_factory=lambda: Path(".cache") / "portal_opportunity.json"
    )
    captcha_timeout_s: int = 180
    page_timeout_s: int = 45
    _pw: Any = field(default=None, init=False, repr=False)
    _browser: BrowserContext | None = field(default=None, init=False, repr=False)
    _cache: dict[str, dict] = field(default_factory=dict, init=False, repr=False)
    _cache_loaded: bool = field(default=False, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def __enter__(self) -> "PortalScraper":
        self._load_cache()
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._pw = sync_playwright().start()
        # patchright applies its own stealth patches; passing extra args or
        # init scripts undoes some of them. Keep it clean.
        self._browser = self._pw.chromium.launch_persistent_context(
            user_data_dir=str(self.profile_dir),
            headless=False,
            channel="chrome",
            viewport={"width": 1280, "height": 900},
            locale="es-CO",
            timezone_id="America/Bogota",
        )
        return self

    def __exit__(self, *_: object) -> None:
        try:
            if self._browser:
                self._browser.close()
        finally:
            if self._pw:
                self._pw.stop()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------
    def fetch(self, notice_uid: str) -> PortalData | None:
        """Return cached or freshly scraped data for ``notice_uid``."""
        if not notice_uid:
            return None
        if notice_uid in self._cache:
            return self._hydrate(notice_uid, self._cache[notice_uid])
        if self._browser is None:
            raise RuntimeError("PortalScraper must be used as a context manager")

        page = self._browser.new_page()
        try:
            data = self._scrape(page, notice_uid)
        finally:
            page.close()

        if data is not None:
            self._cache[notice_uid] = {
                "fields": data.fields,
                "documents": data.documents,
                "raw_length": data.raw_length,
            }
            self._flush_cache()
        return data

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _scrape(self, page: Page, notice_uid: str) -> PortalData | None:
        url = OPPORTUNITY_URL.format(notice_uid=notice_uid)
        log.info("Scraping %s", notice_uid)
        # The portal is occasionally flaky — one retry with reload covers most blips.
        last_err: Exception | None = None
        for attempt in range(2):
            try:
                page.goto(url, timeout=self.page_timeout_s * 1000, wait_until="domcontentloaded")
                break
            except PWTimeout as exc:
                last_err = exc
                log.warning("Timeout abriendo %s (intento %d)", notice_uid, attempt + 1)
        else:
            log.warning("No pude abrir %s: %s", notice_uid, last_err)
            return None

        # Handle captcha: first try to auto-click the "No soy un robot" checkbox.
        # On a real Chrome session with Colombian IP this usually passes without
        # a challenge. If Google presents a challenge anyway, fall back to the
        # user solving it manually in the visible window.
        if "GoogleReCaptcha" in page.url:
            if _try_auto_click_checkbox(page):
                try:
                    page.wait_for_url(
                        lambda u: "GoogleReCaptcha" not in u, timeout=12000
                    )
                    print(
                        f"  * Auto-clic pasó para {notice_uid}. Cookie guardada.",
                        flush=True,
                    )
                except PWTimeout:
                    # Google exige challenge → pedir al usuario
                    print(
                        f"\n  * Captcha con challenge para {notice_uid}. "
                        f"Haz clic en 'No soy un robot' y resuelve el challenge "
                        f"en la ventana de Chrome. Esperando hasta "
                        f"{self.captcha_timeout_s}s...",
                        flush=True,
                    )
                    try:
                        page.wait_for_url(
                            lambda u: "GoogleReCaptcha" not in u,
                            timeout=self.captcha_timeout_s * 1000,
                        )
                        print(f"  * Captcha OK, cookie guardada.", flush=True)
                    except PWTimeout:
                        log.warning("Timeout esperando captcha para %s", notice_uid)
                        return None
            else:
                print(
                    f"\n  * No pude auto-clicar. Resuelve el captcha a mano "
                    f"en la ventana de Chrome (hasta {self.captcha_timeout_s}s)...",
                    flush=True,
                )
                try:
                    page.wait_for_url(
                        lambda u: "GoogleReCaptcha" not in u,
                        timeout=self.captcha_timeout_s * 1000,
                    )
                    print(f"  * Captcha OK.", flush=True)
                except PWTimeout:
                    return None

        try:
            page.wait_for_load_state("networkidle", timeout=20000)
        except PWTimeout:
            pass

        html = page.content()
        fields = _extract_fields(html)
        documents = _extract_documents(html)
        return PortalData(
            notice_uid=notice_uid,
            fields=fields,
            documents=documents,
            raw_length=len(html),
        )

    def _hydrate(self, notice_uid: str, raw: dict) -> PortalData:
        return PortalData(
            notice_uid=notice_uid,
            fields=raw.get("fields", {}),
            documents=raw.get("documents", []),
            raw_length=raw.get("raw_length", 0),
        )

    def _load_cache(self) -> None:
        if self._cache_loaded:
            return
        self._cache_loaded = True
        try:
            data = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Cache portal corrupta/ilegible (%s); ignorada", exc)
            return
        if isinstance(data, dict):
            self._cache.update(data)

    def _flush_cache(self) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(
                json.dumps(self._cache, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        except OSError as exc:
            log.warning("No pude escribir cache portal: %s", exc)


# ------------------------------------------------------------------
# Captcha helper
# ------------------------------------------------------------------
def _try_auto_click_checkbox(page: Page) -> bool:
    """Click the 'No soy un robot' checkbox inside reCAPTCHA's anchor iframe.

    Returns True if the click succeeded (regardless of whether the token was
    issued — the caller decides that by watching for URL changes).
    """
    try:
        anchor = page.wait_for_selector(
            "iframe[src*='api2/anchor']", timeout=10000
        )
        if not anchor:
            return False
        frame = anchor.content_frame()
        if not frame:
            return False
        frame.locator("#recaptcha-anchor").click(timeout=8000)
        return True
    except PWTimeout:
        return False
    except Exception as exc:  # pragma: no cover
        log.warning("auto-click fallo: %s", exc)
        return False


# ------------------------------------------------------------------
# HTML extraction
# ------------------------------------------------------------------
def _strip_tags(html: str) -> str:
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.I)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.I)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n", "\n", text)
    return text.strip()


def _extract_fields(html: str) -> dict[str, str]:
    """Pull labeled key/value pairs from SECOP's table-based layout.

    The portal renders each field as ``<label>: <value>``. We look for the
    label anywhere in the stripped text and capture up to the next label
    or ~200 chars, whichever comes first.
    """
    text = _strip_tags(html)
    out: dict[str, str] = {}
    # Sort labels longest first so "Lista adicional..." matches before "Código UNSPSC"
    ordered = sorted(_FIELD_LABELS.items(), key=lambda kv: -len(kv[1]))
    for key, pattern in ordered:
        m = re.search(pattern + r"\s*:?\s*(.{1,400}?)(?:\n|(?=[A-Z][a-záéíóúñ ]{2,40}:\s))", text)
        if m:
            value = m.group(1).strip(" :\t")
            # Trim to something printable
            value = re.sub(r"\s+", " ", value).strip()
            if value:
                out[key] = value[:300]
    return out


_DOC_LINK_RE = re.compile(
    r'href="([^"]*DocumentDownloader[^"]*)"[^>]*>\s*([^<]{3,160})',
    re.I,
)


def _extract_documents(html: str) -> list[dict[str, str]]:
    docs: list[dict[str, str]] = []
    for m in _DOC_LINK_RE.finditer(html):
        url = m.group(1).replace("&amp;", "&")
        name = re.sub(r"\s+", " ", m.group(2)).strip()
        if name and not any(d["url"] == url for d in docs):
            docs.append({"url": url, "name": name[:200]})
    return docs


__all__ = ["PortalScraper", "PortalData"]
