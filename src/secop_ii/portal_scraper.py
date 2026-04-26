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

import gzip
import io
import json
import logging
import os
import random
import re
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from secop_ii.paths import state_path
from typing import Any

import requests
from bs4 import BeautifulSoup, Tag

# Critical fields that prove the OpportunityDetail page rendered fully. If any
# are empty after a scrape, we retry once before giving up — guards against
# silent partial captures (page not fully loaded, captcha-then-redirect race,
# etc.). These map to keys in ``_LABEL_TO_KEY``.
_CRITICAL_FIELDS = ("titulo", "tipo_proceso", "numero_proceso")

# Scrape status enum (written to "Portal: Estado scraping" column).
STATUS_OK_COMPLETE = "ok_completo"
STATUS_OK_PARTIAL = "ok_parcial"
STATUS_CAPTCHA_BLOCKED = "bloqueado_captcha"
STATUS_NETWORK_ERROR = "error_red"
STATUS_NOT_AVAILABLE = "no_disponible"

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

# `playwright-recaptcha` is the community-maintained reference solver for
# reCAPTCHA v2 (audio challenge). It downloads the audio, transcribes via
# Google Speech, types the answer and waits for the token to populate.
# Optionally falls back to CapSolver (paid, ~$0.80/1k) for image challenges.
# If the lib isn't installed at runtime we fall back to the bespoke solver
# below — but the lib should be the preferred path because it's better
# tested against Google's anti-bot heuristics than our hand-rolled code.
try:
    from playwright_recaptcha import recaptchav2  # type: ignore[import-not-found]
    _RECAPTCHA_LIB_AVAILABLE = True
except ImportError:  # pragma: no cover
    recaptchav2 = None  # type: ignore[assignment]
    _RECAPTCHA_LIB_AVAILABLE = False

# Idiomas para el audio solver (cascade). El portal corre con locale es-CO,
# así que la primera transcripción usa Spanish; si Google sirve audio en
# inglés (a veces lo hace cuando detecta bot bajo) caemos a en-US.
_AUDIO_LANGS = ("es-CO", "es", "en-US")

log = logging.getLogger(__name__)

OPPORTUNITY_URL = (
    "https://community.secop.gov.co/Public/Tendering/OpportunityDetail/Index"
    "?noticeUID={notice_uid}&isFromPublicArea=True&isModal=False"
)

# Curated mapping of OpportunityDetail labels (as they appear on the portal,
# without the trailing colon, accent-insensitive comparison) to short keys.
# Keys are stable; we use them as Excel column suffixes.
_LABEL_TO_KEY = {
    "Precio estimado total": "precio_estimado",
    "Numero del proceso": "numero_proceso",
    "Titulo": "titulo",
    "Fase": "fase",
    "Estado": "estado",
    "Descripcion": "descripcion",
    "Tipo de proceso": "tipo_proceso",
    "Limitacion de todo el proceso a MiPymes": "mipyme_limitacion",
    "Tipo de contrato": "tipo_contrato",
    "Justificacion de la modalidad de contratacion": "justificacion_modalidad",
    "Duracion del contrato": "duracion_contrato",
    "Direccion de ejecucion del contrato": "direccion_ejecucion",
    "Codigo UNSPSC": "unspsc_principal",
    "Lista adicional de codigos UNSPSC": "unspsc_adicional",
    "Lotes?": "lotes",
    "Dar publicidad al proceso": "dar_publicidad",
    "Uso del modulo de forma publicitaria?": "modulo_publicitario",
    "Fecha de Firma del Contrato": "fecha_firma_contrato",
    "Fecha de inicio de ejecucion del contrato": "fecha_inicio_ejecucion",
    "Plazo de ejecucion del contrato": "plazo_ejecucion",
    "Fecha de terminacion del contrato": "fecha_terminacion",
    "Fecha de publicacion": "fecha_publicacion",
    "Destinacion del gasto": "destinacion_gasto",
    "Valor total": "valor_total",
    "Solicitud de garantias?": "solicita_garantias",
    "% del valor del contrato": "garantia_pct_valor",
    "Fecha de vigencia (desde)": "garantia_vigencia_desde",
    "Fecha de vigencia (hasta)": "garantia_vigencia_hasta",
    "Responsabilidad civil extra contractual": "garantia_resp_civil",
    "Cumplimiento": "garantia_cumplimiento",
    "No. de SMMLV": "garantia_smmlv",
}


@dataclass
class PortalData:
    """What we extract for a single OpportunityDetail page."""

    notice_uid: str
    fields: dict[str, str]
    documents: list[dict[str, str]]
    raw_length: int
    notificaciones: list[dict[str, str]] = field(default_factory=list)
    all_labels: dict[str, str] = field(default_factory=dict)  # full dump for audit
    status: str = STATUS_OK_COMPLETE  # see STATUS_* constants
    missing_fields: list[str] = field(default_factory=list)  # critical fields that came up empty
    scraped_at: str = ""  # ISO timestamp

    def is_complete(self) -> bool:
        return self.status == STATUS_OK_COMPLETE and not self.missing_fields

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
        default_factory=lambda: state_path("portal_opportunity.json")
    )
    # Raw-HTML archive: gzipped per NTC, lets us re-extract any field later
    # without revisiting the portal. ~50 KB per process compressed.
    html_archive_dir: Path = field(
        default_factory=lambda: state_path("portal_html")
    )
    captcha_timeout_s: int = 180
    page_timeout_s: int = 45
    # Pause between successful scrapes. Google's reCAPTCHA flags us as a bot
    # after ~6 auto-clicks in quick succession; staying above ~25s per request
    # keeps us under the threshold in practice. Random jitter mimics a human
    # opening one tab at a time.
    request_delay_min_s: float = 30.0
    request_delay_max_s: float = 55.0
    _pw: Any = field(default=None, init=False, repr=False)
    _browser: BrowserContext | None = field(default=None, init=False, repr=False)
    _cache: dict[str, dict] = field(default_factory=dict, init=False, repr=False)
    _cache_loaded: bool = field(default=False, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _last_fetch_at: float = field(default=0.0, init=False, repr=False)

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
        # Pre-warm: si el persistent profile es nuevo, visitar la home
        # del portal antes del primer OpportunityDetail. Esto siembra
        # cookies básicas y le da a reCAPTCHA un "score" más humano
        # (visita la home → navega → consulta detalle, vs. visita
        # detalle directo a la primera). Idempotente: si ya hay cookies
        # del dominio, retorna inmediato.
        try:
            self._prewarm_session()
        except Exception as exc:  # pragma: no cover
            log.debug("pre-warm fallo (no critico): %s", exc)
        return self

    def _prewarm_session(self) -> None:
        """Visita la home SECOP para sembrar cookies si el profile es nuevo."""
        if self._browser is None:
            return
        # Heuristic: si ya hay cookies del dominio community.secop.gov.co
        # asumimos que la sesión fue inicializada previamente y skipeamos.
        cookies = self._browser.cookies()
        has_secop = any(
            "secop.gov.co" in (c.get("domain") or "") for c in cookies
        )
        if has_secop:
            return
        log.info("Pre-warm: profile nuevo, visitando home SECOP...")
        page = self._browser.new_page()
        try:
            page.goto(
                "https://community.secop.gov.co/Public/Tendering/ContractNoticeManagement/Index",
                timeout=30000,
                wait_until="domcontentloaded",
            )
            # Pausa breve para que JS asyncrono setee cookies + Google
            # tracking ping. Sin pausa Google puede no ver la "visita"
            # como real.
            page.wait_for_timeout(3000)
        except PWTimeout:
            log.info("Pre-warm timeout — continuando igual.")
        finally:
            page.close()

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
        """Return cached or freshly scraped data for ``notice_uid``.

        Cache hits are returned only if the previous scrape was complete.
        Partial/failed cached entries are re-attempted (so a flaky earlier
        run doesn't permanently poison the cache).
        """
        if not notice_uid:
            return None
        if notice_uid in self._cache:
            cached = self._hydrate(notice_uid, self._cache[notice_uid])
            if cached.is_complete():
                return cached
            log.info(
                "Cache para %s estaba %s — reintentando", notice_uid, cached.status
            )
        if self._browser is None:
            raise RuntimeError("PortalScraper must be used as a context manager")

        # Throttle: don't fire a fresh scrape immediately after the previous one.
        # Random delay so the cadence looks human, not robotic.
        if self._last_fetch_at:
            elapsed = time.monotonic() - self._last_fetch_at
            wait = random.uniform(self.request_delay_min_s, self.request_delay_max_s)
            if elapsed < wait:
                sleep_for = wait - elapsed
                log.debug("Esperando %.1fs antes de scrapear %s", sleep_for, notice_uid)
                time.sleep(sleep_for)

        page = self._browser.new_page()
        try:
            data = self._scrape(page, notice_uid)
        finally:
            page.close()
            self._last_fetch_at = time.monotonic()

        if data is not None:
            self._cache[notice_uid] = {
                "fields": data.fields,
                "documents": data.documents,
                "notificaciones": data.notificaciones,
                "all_labels": data.all_labels,
                "raw_length": data.raw_length,
                "status": data.status,
                "missing_fields": data.missing_fields,
                "scraped_at": data.scraped_at,
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
            return PortalData(
                notice_uid=notice_uid,
                fields={},
                documents=[],
                raw_length=0,
                status=STATUS_NETWORK_ERROR,
            )

        # Handle captcha. Cascade (de lo m\u00e1s r\u00e1pido a lo m\u00e1s caro):
        #   1. auto-click "No soy un robot"  (cookies cacheadas \u2192 0s)
        #   2. CapSolver API directa (Fix Error #9, 99.9% exito si key configurada)
        #   3. playwright-recaptcha lib SyncSolver (legacy fallback)
        #   4. solver manual interno con cascade es-CO \u2192 en-US
        #   5. fallback humano (\u00faltimo recurso, ventana Chrome visible)
        if "GoogleReCaptcha" in page.url:
            clicked = _try_auto_click_checkbox(page)
            passed = False
            if clicked:
                try:
                    page.wait_for_url(
                        lambda u: "GoogleReCaptcha" not in u, timeout=8000
                    )
                    passed = True
                    print(f"  * Auto-clic paso para {notice_uid}.", flush=True)
                except PWTimeout:
                    pass

            # NUEVO (Fix Error #9 / 2026-04-26): CapSolver directo antes
            # de la lib que se cuelga. Si CAPSOLVER_API_KEY esta seteada,
            # esto maneja 99.9% de los captchas en ~30s. El cascade nunca
            # llega a los pasos siguientes en operacion normal.
            if not passed and os.environ.get("CAPSOLVER_API_KEY"):
                print(
                    f"  * Challenge en {notice_uid} - CapSolver directo...",
                    flush=True,
                )
                if _try_solve_with_capsolver_direct(page):
                    try:
                        page.wait_for_url(
                            lambda u: "GoogleReCaptcha" not in u, timeout=15000
                        )
                        passed = True
                        print("    * CapSolver directo paso.", flush=True)
                    except PWTimeout:
                        pass

            if not passed and _RECAPTCHA_LIB_AVAILABLE:
                print(
                    f"  * Fallback playwright-recaptcha lib...",
                    flush=True,
                )
                if _try_solve_with_recaptcha_lib(page):
                    try:
                        page.wait_for_url(
                            lambda u: "GoogleReCaptcha" not in u, timeout=20000
                        )
                        passed = True
                        print("    * playwright-recaptcha paso.", flush=True)
                    except PWTimeout:
                        pass

            if not passed:
                print(
                    f"  * Cayendo a solver manual (audio es-CO -> en-US)...",
                    flush=True,
                )
                if _try_solve_audio_challenge(page):
                    try:
                        page.wait_for_url(
                            lambda u: "GoogleReCaptcha" not in u, timeout=15000
                        )
                        passed = True
                        print("    * Audio solver manual paso.", flush=True)
                    except PWTimeout:
                        pass

            if not passed:
                print(
                    f"  * Auto-solvers fallaron. Resuelve a mano en Chrome "
                    f"(hasta {self.captcha_timeout_s}s)...",
                    flush=True,
                )
                try:
                    page.wait_for_url(
                        lambda u: "GoogleReCaptcha" not in u,
                        timeout=self.captcha_timeout_s * 1000,
                    )
                    print("  * Captcha OK (resuelto manual).", flush=True)
                except PWTimeout:
                    log.warning("Timeout esperando captcha para %s", notice_uid)
                    return None

        try:
            page.wait_for_load_state("networkidle", timeout=20000)
        except PWTimeout:
            pass

        # Some sections (notably the notification log and document list) are
        # rendered after the initial DOMContentLoaded. Scroll to bottom to
        # trigger lazy renders, then give the framework a moment to settle.
        try:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(2500)
            page.evaluate("window.scrollTo(0, 0)")
        except Exception:  # pragma: no cover
            pass

        # Deep dive: expand every collapsed accordion / click every tab so
        # the DOM exposes documents that only render on demand. Vortal uses
        # a handful of patterns — we try them all and silently skip the ones
        # that don't exist on a particular page. Runs once; best-effort.
        try:
            _expand_all_sections(page)
            page.wait_for_timeout(1500)
        except Exception as exc:  # pragma: no cover
            log.debug("expand_all_sections fallo: %s", exc)

        html = page.content()

        # Persist raw HTML — perpetual audit trail. If we ever extract a new
        # field, we re-process from disk without revisiting the portal.
        self._archive_html(notice_uid, html)

        all_labels, fields = _extract_fields(html)
        documents = _extract_documents(html)
        notificaciones = _extract_notificaciones(html)

        # Validate critical fields. If any are missing the page rendered
        # incompletely (race with captcha redirect, JS still loading, etc.).
        missing = [k for k in _CRITICAL_FIELDS if not fields.get(k)]

        # If incomplete, give the page another 5 s and re-extract — handles
        # the common "JS hadn't finished filling labels yet" race.
        if missing:
            log.info(
                "%s: faltan %s — esperando 5s para re-extraer", notice_uid, missing
            )
            try:
                page.wait_for_timeout(5000)
                html = page.content()
                self._archive_html(notice_uid, html)
                all_labels, fields = _extract_fields(html)
                documents = _extract_documents(html)
                notificaciones = _extract_notificaciones(html)
                missing = [k for k in _CRITICAL_FIELDS if not fields.get(k)]
            except Exception as exc:  # pragma: no cover
                log.warning("Re-extract fallo para %s: %s", notice_uid, exc)

        from datetime import datetime
        status = STATUS_OK_COMPLETE if not missing else STATUS_OK_PARTIAL
        return PortalData(
            notice_uid=notice_uid,
            fields=fields,
            documents=documents,
            notificaciones=notificaciones,
            all_labels=all_labels,
            raw_length=len(html),
            status=status,
            missing_fields=missing,
            scraped_at=datetime.utcnow().isoformat(timespec="seconds"),
        )

    def _hydrate(self, notice_uid: str, raw: dict) -> PortalData:
        return PortalData(
            notice_uid=notice_uid,
            fields=raw.get("fields", {}),
            documents=raw.get("documents", []),
            notificaciones=raw.get("notificaciones", []),
            all_labels=raw.get("all_labels", {}),
            raw_length=raw.get("raw_length", 0),
            status=raw.get("status", STATUS_OK_COMPLETE),
            missing_fields=raw.get("missing_fields", []),
            scraped_at=raw.get("scraped_at", ""),
        )

    def _archive_html(self, notice_uid: str, html: str) -> None:
        """Compress + persist HTML for ``notice_uid`` (overwrites previous copy)."""
        try:
            self.html_archive_dir.mkdir(parents=True, exist_ok=True)
            target = self.html_archive_dir / f"{notice_uid}.html.gz"
            with gzip.open(target, "wb") as fh:
                fh.write(html.encode("utf-8"))
        except OSError as exc:
            log.warning("No pude guardar snapshot HTML %s: %s", notice_uid, exc)

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
# Captcha helpers
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


def _try_solve_with_recaptcha_lib(page: Page) -> bool:
    """Use the community-maintained `playwright-recaptcha` library to
    solve the audio challenge, optionally with CapSolver as a paid
    fallback for image challenges.

    Reads ``CAPSOLVER_API_KEY`` from env if set; that lets the lib fall
    through to image challenges when the audio variant gets blocked
    ("Try again later").

    Returns True iff the lib reports a solved token. Caller still has
    to verify the navigation away from /GoogleReCaptcha/ (the form may
    silently reject the token if anti-bot heuristics flagged us).
    """
    if not _RECAPTCHA_LIB_AVAILABLE or recaptchav2 is None:
        return False
    capsolver_key = os.environ.get("CAPSOLVER_API_KEY") or None
    try:
        with recaptchav2.SyncSolver(
            page, capsolver_api_key=capsolver_key
        ) as solver:
            # Fix Error #6 + #7 (2026-04-26): playwright-recaptcha
            # removio el kwarg `language` y wait=True sin wait_timeout
            # cuelga indefinidamente en versiones recientes. Signature:
            # solve_recaptcha(*, attempts, wait, wait_timeout, image_challenge).
            # wait_timeout=60 es duro - el captcha completo NO debe tardar
            # mas. Si tarda mas, salimos y caemos al solver manual interno.
            # El audio captcha se decodifica en es-CO via faster-whisper en
            # el solver fallback (line ~680).
            token = solver.solve_recaptcha(
                wait=True,
                wait_timeout=60,
                image_challenge=False,
                attempts=3,
            )
        if token:
            return True
    except Exception as exc:
        # The lib raises on various failure modes (audio blocked, network
        # hiccup, captcha not found, etc). We swallow and fall back to the
        # next solver in the cascade — nothing here is critical enough to
        # crash the whole batch run.
        log.info("playwright-recaptcha solver fallo: %s", str(exc)[:200])
    return False


def _try_solve_with_capsolver_direct(page: Page) -> bool:
    """Solver de captcha via CapSolver API directa - Fix Error #9 (2026-04-26).

    Bypassa la lib `playwright-recaptcha` (que se cuelga buscando elementos
    DOM que no existen en este captcha specifico). Llama CapSolver API
    directamente con `ReCaptchaV2TaskProxyLess`, recibe token y lo inyecta
    en `g-recaptcha-response` del DOM. Despues invoca el callback
    `onSubmit(token)` que el portal SECOP usa para enviar el form.

    Costos:
      - createTask: gratis
      - solucion completada: ~$0.001 USD por captcha
      - typical latencia: 15-45s end-to-end

    Solo se activa si `CAPSOLVER_API_KEY` esta en env. Sin la key,
    retorna False inmediatamente y la cascada cae al solver lib o manual.

    Returns True iff token resuelto + inyectado + callback invocado. El
    caller tiene que verificar `wait_for_url` que GoogleReCaptcha desaparezca
    para confirmar que el portal acepto el token.
    """
    capsolver_key = os.environ.get("CAPSOLVER_API_KEY")
    if not capsolver_key:
        return False
    try:
        # 1. Extraer sitekey del DOM. SECOP usa div.g-recaptcha[data-sitekey].
        sitekey = page.evaluate(
            "() => document.querySelector('.g-recaptcha')?.getAttribute('data-sitekey')"
        )
        if not sitekey:
            log.debug("CapSolver: no encuentro div.g-recaptcha en pagina")
            return False
        page_url = page.url
        log.info("CapSolver direct: solving sitekey=%s...", sitekey[:20])

        # 2. Crear task. ReCaptchaV2TaskProxyLess = sin proxy, mas barato.
        import requests as _requests
        task_resp = _requests.post(
            "https://api.capsolver.com/createTask",
            json={
                "clientKey": capsolver_key,
                "task": {
                    "type": "ReCaptchaV2TaskProxyLess",
                    "websiteURL": page_url,
                    "websiteKey": sitekey,
                },
            },
            timeout=15,
        )
        task_data = task_resp.json()
        if task_data.get("errorId") != 0:
            log.warning("CapSolver createTask fail: %s", task_data.get("errorDescription"))
            return False
        task_id = task_data.get("taskId")
        if not task_id:
            return False

        # 3. Polling resultado (max 90s = 30 intentos x 3s).
        token = None
        for attempt in range(30):
            time.sleep(3)
            res = _requests.post(
                "https://api.capsolver.com/getTaskResult",
                json={"clientKey": capsolver_key, "taskId": task_id},
                timeout=10,
            )
            rd = res.json()
            status = rd.get("status")
            if status == "ready":
                token = rd.get("solution", {}).get("gRecaptchaResponse")
                break
            elif status == "failed":
                log.warning("CapSolver task failed: %s", rd.get("errorDescription"))
                return False
        if not token:
            log.warning("CapSolver timeout 90s sin solucion")
            return False

        # 4. Inyectar token + navegar al URL final del SECOP.
        # El portal valida con: /Public/Common/GoogleReCaptcha/CaptchaCheck
        #   ?responseKey=<TOKEN>&mkey=<UNIQUE_PER_SESSION>
        # El mkey es unico por sesion - lo extraemos del onclick del boton
        # btnCaptchaCheckButton (no podemos asumir valor fijo).
        # Inyectamos token en AMBOS textareas (g-recaptcha-response Y
        # txaresponseKey) para satisfacer cualquier validacion del portal.
        captcha_url = page.evaluate(
            """(token) => {
                const ta1 = document.getElementById('g-recaptcha-response');
                if (ta1) { ta1.value = token; ta1.textContent = token; }
                const ta2 = document.getElementById('txaresponseKey');
                if (ta2) { ta2.value = token; ta2.textContent = token; }
                const btn = document.getElementById('btnCaptchaCheckButton');
                if (!btn) return null;
                const oc = btn.getAttribute('onclick') || '';
                const m = oc.match(/mkey=([a-zA-Z0-9_-]+)/);
                if (!m) return null;
                return '/Public/Common/GoogleReCaptcha/CaptchaCheck?responseKey=' +
                       encodeURIComponent(token) + '&mkey=' + m[1];
            }""",
            token,
        )
        if not captcha_url:
            log.warning("CapSolver direct: no encuentro btnCaptchaCheckButton o mkey")
            return False
        log.info("CapSolver direct: token inyectado, navegando a CaptchaCheck...")
        # Navegar al URL final - SECOP valida y redirige a la pagina real.
        full_url = "https://community.secop.gov.co" + captcha_url
        try:
            page.goto(full_url, wait_until="domcontentloaded", timeout=20000)
        except Exception as exc:
            log.warning("CapSolver direct: page.goto fallo: %s", str(exc)[:100])
            return False
        # Si despues del goto la URL ya no contiene GoogleReCaptcha → exito.
        return "GoogleReCaptcha" not in page.url
    except Exception as exc:  # noqa: BLE001
        log.warning("CapSolver direct exception: %s", str(exc)[:200])
        return False


def _try_solve_audio_challenge(page: Page) -> bool:
    """When Google demands a challenge, switch to audio mode and transcribe.

    Returns True iff the challenge was passed (token populated). The caller
    then waits for the navigation away from /GoogleReCaptcha/ to know the
    SECOP form actually accepted the token.

    Uses ``SpeechRecognition`` with Google's free Speech-to-Text endpoint
    (no API key) and ``imageio-ffmpeg`` to convert the audio. If anything
    along the chain fails, we return False so the caller can fall back to
    asking the user to solve it manually.
    """
    try:
        bframe_el = page.wait_for_selector(
            "iframe[src*='api2/bframe']", timeout=8000
        )
    except PWTimeout:
        return False
    bframe = bframe_el.content_frame()
    if bframe is None:
        return False

    # 1. Switch to audio challenge.
    try:
        bframe.locator("#recaptcha-audio-button").click(timeout=8000)
    except Exception as exc:
        log.info("no pude clicar el bot\u00f3n audio: %s", exc)
        return False

    # Sometimes Google blocks audio challenges with "Try later". Detect that.
    try:
        bframe.wait_for_selector(
            ".rc-audiochallenge-tdownload-link, .rc-doscaptcha-header",
            timeout=15000,
        )
    except PWTimeout:
        return False

    if bframe.locator(".rc-doscaptcha-header").count() > 0:
        log.warning("Google rechaz\u00f3 challenge audio (try later)")
        return False

    audio_link = bframe.locator(".rc-audiochallenge-tdownload-link").first
    audio_url = audio_link.get_attribute("href")
    if not audio_url:
        return False

    # 2. Download MP3 + transcribe.
    try:
        text = _transcribe_audio(audio_url)
    except Exception as exc:
        log.warning("transcripci\u00f3n fall\u00f3: %s", exc)
        return False
    if not text:
        return False
    log.info("audio captcha transcrito: %s", text[:40])

    # 3. Type answer + verify.
    try:
        bframe.locator("#audio-response").fill(text, timeout=8000)
        bframe.locator("#recaptcha-verify-button").click(timeout=8000)
    except Exception as exc:
        log.warning("submit del audio fall\u00f3: %s", exc)
        return False

    # 4. Wait for token to populate in the outer page.
    try:
        page.wait_for_function(
            "() => { const t = document.getElementById('g-recaptcha-response'); return t && t.value && t.value.length > 0; }",
            timeout=15000,
        )
    except PWTimeout:
        return False
    return True


def _transcribe_audio_with_whisper(wav_path: str) -> str | None:
    """Transcribe a WAV file with `faster-whisper` (local, free, MIT).

    Whisper es notablemente más preciso que Google Speech para audio en
    español (que es lo que sirve reCAPTCHA bajo locale es-CO). Modelo
    ``tiny`` (~75MB) es suficiente para captcha — el audio es 5-10s de
    voz clara, no necesita el modelo grande.

    Devuelve la transcripción o ``None`` si la lib no está instalada
    (caller cae a Google Speech como fallback).
    """
    try:
        from faster_whisper import WhisperModel  # type: ignore[import-not-found]
    except ImportError:
        return None
    try:
        # Modelo cacheado en disco después del primer download.
        # int8 cuantizado: corre fluido en CPU sin GPU.
        model = WhisperModel("tiny", device="cpu", compute_type="int8")
        segments, _info = model.transcribe(
            wav_path, language="es", beam_size=1, without_timestamps=True
        )
        text = " ".join(seg.text for seg in segments).strip()
        if text:
            log.info("audio captcha transcrito (whisper-tiny es): %s", text[:40])
            return text
    except Exception as exc:  # pragma: no cover
        log.info("whisper transcribe fallo: %s", str(exc)[:200])
    return None


def _transcribe_audio(mp3_url: str) -> str | None:
    """Download MP3, convert to WAV, transcribe with cascade:
    Whisper local (es) → Google Speech (es-CO → es → en-US).

    Whisper se intenta PRIMERO porque es más preciso para español y
    100% local (no depende de la red). Si Whisper no está instalado o
    devuelve vacío, caemos a Google Speech."""
    import subprocess
    import speech_recognition as sr  # lazy import — only on captcha path
    import imageio_ffmpeg

    ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()

    resp = requests.get(mp3_url, timeout=20)
    if resp.status_code != 200:
        return None

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as mp3_f:
        mp3_path = mp3_f.name
        mp3_f.write(resp.content)
    wav_path = mp3_path.replace(".mp3", ".wav")
    try:
        # Direct ffmpeg subprocess. Bypasses pydub which can't find the binary
        # on Windows when imageio-ffmpeg installed it under a versioned name
        # outside PATH. ``-y`` overwrites WAV; ``-loglevel error`` is quiet.
        result = subprocess.run(
            [
                ffmpeg_bin, "-y", "-loglevel", "error",
                "-i", mp3_path,
                "-ac", "1", "-ar", "16000",  # mono, 16kHz — best for STT
                wav_path,
            ],
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0:
            log.warning("ffmpeg fallo (code=%s): %s", result.returncode, result.stderr[:200])
            return None

        # 1) Whisper local (free, español nativo)
        whisper_text = _transcribe_audio_with_whisper(wav_path)
        if whisper_text:
            return whisper_text

        # 2) Google Speech como fallback (cascada de idiomas)
        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)
        last_err: str | None = None
        for lang in _AUDIO_LANGS:
            try:
                text = recognizer.recognize_google(audio_data, language=lang)
                if text and text.strip():
                    log.info("audio captcha transcrito (google %s): %s", lang, text[:40])
                    return text.strip()
            except sr.UnknownValueError:
                last_err = f"unknown_value_{lang}"
                continue  # probar próximo idioma
            except sr.RequestError as exc:
                last_err = f"request_{lang}: {exc}"
                continue
        log.info("audio captcha no transcrito por ningún solver: %s", last_err)
        return None
    finally:
        for p in (mp3_path, wav_path):
            try:
                os.unlink(p)
            except OSError:
                pass


# ------------------------------------------------------------------
# HTML extraction
# ------------------------------------------------------------------
_TRANSLATOR_JS = re.compile(r"translator\.loadFile|loadFileAndTranslate")
_NOISE_LABELS = {"si", "no", "*", ""}  # radio button labels and empty markers


def _expand_all_sections(page) -> None:  # pragma: no cover — needs a live Vortal page
    """Click every collapsed element so hidden documents become visible.

    Vortal (the CMS behind SECOP II) uses several patterns for collapsed
    sections — accordions, tree branches, tabs. We try each pattern in
    turn, clicking every visible match and giving the page a beat to
    render before moving on. Any pattern that doesn't exist on this
    particular page is silently skipped.

    We cap the number of clicks per pattern at ``_MAX_CLICKS`` so a
    pathological page with hundreds of elements can't stall the scrape.
    """
    _MAX_CLICKS = 40
    selectors = [
        # Vortal accordions
        "div.vrt-accordion-header:not(.vrt-accordion-open)",
        "div.vrt-accordion-header.collapsed",
        ".vrt-accordion .vrt-accordion-header",
        # ARIA collapsed panels
        "[aria-expanded='false']",
        # Treeview expand nodes
        "span.vrt-tree-expand-node",
        "img[src*='ExpandNode']",
        # Tabs
        ".vrt-tab:not(.vrt-tab-selected)",
        "li[role='tab']",
        # "Show more" / Ver más
        "a.vrt-show-more",
        "a[onclick*='ShowMore']",
        "a[onclick*='showMore']",
        # Generic toggle links
        "a[onclick*='Expand']",
        "a[onclick*='expand']",
        "a[onclick*='Toggle']",
        "a[onclick*='toggle']",
        # "+" image toggles Vortal uses
        "img[src*='plus']",
        "img[alt*='Expand']",
    ]

    for sel in selectors:
        try:
            locator = page.locator(sel)
            count = min(locator.count(), _MAX_CLICKS)
        except Exception:
            continue
        for i in range(count):
            try:
                el = locator.nth(i)
                if not el.is_visible():
                    continue
                el.click(timeout=1500)
                page.wait_for_timeout(250)
            except Exception:
                continue  # element moved / stale / not clickable — skip
        if count:
            log.debug("Expandidos %d elementos con selector %s", count, sel)


def _normalize_label(text: str) -> str:
    """Uppercase + strip accents + drop trailing colon/whitespace."""
    import unicodedata
    decomposed = unicodedata.normalize("NFD", text or "")
    cleaned = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return cleaned.strip().rstrip(":").strip()


def _value_for_label(label_tag: Tag) -> str:
    """Find the value cell associated with a ``<label>`` tag.

    SECOP II uses Vortal's table layout: each field is a ``<tr>`` with the
    label in one ``<td>`` and the value in the next sibling ``<td>``. The
    value can be a plain text node, an ``<input value="...">`` (read-only
    fields), or a nested ``<span>``/``<div>``. We try those in order and
    fall back to the next sibling element of the label itself.
    """
    parent_td = label_tag.find_parent("td")
    if parent_td is not None:
        next_td = parent_td.find_next_sibling("td")
        if next_td is not None:
            return _td_text(next_td)
    # Some fields render the value as the next sibling element of the label.
    nxt = label_tag.find_next_sibling()
    while nxt is not None and getattr(nxt, "name", None) in {"br", "i", "em"}:
        nxt = nxt.find_next_sibling()
    if nxt is not None and isinstance(nxt, Tag):
        return _td_text(nxt)
    return ""


def _td_text(td: Tag) -> str:
    """Extract a clean string from a value cell (input value or text)."""
    inp = td.find("input")
    if inp is not None and inp.get("value"):
        return _clean_value(inp.get("value", ""))
    txt = td.get_text(" ", strip=True)
    return _clean_value(txt)


def _clean_value(text: str) -> str:
    if not text:
        return ""
    # Drop the JS placeholder Vortal injects when a value is loaded async
    if _TRANSLATOR_JS.search(text):
        return ""
    text = text.replace("\u00a0", " ")  # nbsp -> space
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s*\n\s*", " | ", text)
    return text.strip()


def _extract_fields(html: str) -> tuple[dict[str, str], dict[str, str]]:
    """Return ``(all_labels, mapped_fields)``.

    ``all_labels`` is the raw label->value dump (for audit). ``mapped_fields``
    maps the curated keys in :data:`_LABEL_TO_KEY` to their values.
    """
    soup = BeautifulSoup(html, "lxml")
    all_labels: dict[str, str] = {}
    for label in soup.find_all("label"):
        raw_label = label.get_text(" ", strip=True)
        norm = _normalize_label(raw_label)
        if not norm or len(norm) > 120:
            continue
        if norm.lower() in _NOISE_LABELS:
            continue
        # If we've seen the same label already (radio groups), keep the
        # first non-empty value to avoid overwriting good data with "".
        if norm in all_labels and all_labels[norm]:
            continue
        all_labels[norm] = _value_for_label(label)

    mapped: dict[str, str] = {}
    for label_text, key in _LABEL_TO_KEY.items():
        norm = _normalize_label(label_text)
        if norm in all_labels:
            value = all_labels[norm]
            if value:
                mapped[key] = value[:500]
    return all_labels, mapped


_DOC_ONCLICK_RE = re.compile(
    r"getAction\(\s*'(/Public/Tendering/[A-Za-z]+/DownloadFile)'\s*\+\s*'\?'\s*\+\s*'documentFileId='\s*\+\s*'(\d+)'(?:.*?'mkey=' ?\+ ?'([0-9a-f_]+)')?",
    re.I,
)


def _extract_documents(html: str) -> list[dict[str, str]]:
    """Find document download links inside the OpportunityDetail document grid.

    SECOP II's Vortal layout puts each row as ``<tr>``:
    cell 1 = ``<span class="VortalSpan">filename.pdf</span>``,
    cell 2 = ``<a onclick="javascript:getAction('.../DownloadFile?documentFileId=NNN&mkey=...', true);">Descargar</a>``.

    The download URL lives inside the JavaScript ``onclick`` attribute,
    not the ``href`` (which is just ``javascript:void(0);``). We pull both
    the filename and the canonical download URL so the cell shows real
    document names and the user can hand-craft the URL if needed.
    """
    soup = BeautifulSoup(html, "lxml")
    docs: list[dict[str, str]] = []
    seen: set[str] = set()

    # Pattern A: explicit document grid (most common)
    grids = soup.find_all("table", id=re.compile(r"DocumentList|GridDocument", re.I))
    rows: list[Tag] = []
    for grid in grids:
        rows.extend(grid.find_all("tr"))

    # Pattern B: any row containing a VortalSpan with a filename + a Descargar link
    if not rows:
        for tr in soup.find_all("tr"):
            spans = tr.find_all("span", class_="VortalSpan")
            if any(re.search(r"\.(pdf|docx?|xlsx?|zip|rar|jpe?g|png|txt)\b", s.get_text() or "", re.I) for s in spans):
                rows.append(tr)

    for tr in rows:
        name_span = tr.find("span", class_="VortalSpan")
        link = tr.find("a", onclick=True)
        if not name_span or not link:
            continue
        name = re.sub(r"\s+", " ", name_span.get_text(strip=True))
        if not name:
            continue
        onclick = link.get("onclick", "")
        m = _DOC_ONCLICK_RE.search(onclick)
        url = ""
        if m:
            base = "https://community.secop.gov.co" + m.group(1)
            doc_id = m.group(2)
            mkey = m.group(3) or ""
            url = f"{base}?documentFileId={doc_id}"
            if mkey:
                url += f"&mkey={mkey}"
        if name in seen:
            continue
        seen.add(name)
        docs.append({"name": name[:250], "url": url[:500]})
    return docs


_NOTIF_DATE = re.compile(
    r"(\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}\s*(?:AM|PM|a\.?m\.?|p\.?m\.?)?)",
    re.I,
)


def _extract_notificaciones(html: str) -> list[dict[str, str]]:
    """Extract the "Notificación" log near the bottom of the page.

    The portal renders publication events as rows of:
    ``Notificación | <id_proceso> | <evento> | <fecha>``. We parse those
    so the user can see when each modificatorio was published, even if
    the open-data API hasn't ingested it yet.
    """
    soup = BeautifulSoup(html, "lxml")
    out: list[dict[str, str]] = []
    # Find rows whose first cell text is exactly "Notificación"
    for tr in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all("td")]
        if not cells:
            continue
        first = _normalize_label(cells[0]).lower()
        if first != "notificacion":
            continue
        # Remaining cells are: process_id, evento, fecha
        rest = [c for c in cells[1:] if c]
        if not rest:
            continue
        proc_id = rest[0] if len(rest) > 0 else ""
        evento = rest[1] if len(rest) > 1 else ""
        fecha = rest[2] if len(rest) > 2 else ""
        # Sometimes evento and fecha are merged in one cell; pull the date out
        if not fecha and evento:
            m = _NOTIF_DATE.search(evento)
            if m:
                fecha = m.group(1)
                evento = evento[: m.start()].strip()
        if proc_id or evento or fecha:
            out.append({"proceso": proc_id, "evento": evento, "fecha": fecha})
    return out


__all__ = ["PortalScraper", "PortalData"]
