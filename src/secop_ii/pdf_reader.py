"""Download + read SECOP II PDFs with a multi-engine fallback.

When auditing a process, the open-data datasets give us a list of
``Public/Archive/RetrieveFile/Index?DocumentId=…`` URLs but never the file
contents. To answer questions like *"does the modificatorio mention
clause 8?"* we need to actually open the PDF.

Why a cascade of engines:

* **pdfplumber** is best at preserving layout (tables, multi-column).
* **pymupdf** (``fitz``) is the fastest text extractor and handles weird
  fonts that pdfplumber chokes on.
* **pypdf** is pure-python, ships in any wheel, and is our last resort
  before OCR.
* **pytesseract** + Pillow is for scanned PDFs (no extractable text).
  Optional — we degrade gracefully if the system Tesseract binary is
  missing instead of raising.

Downloads are cached on disk via :mod:`diskcache` so repeated audits do
not re-hit the SECOP II archive servers.
"""

from __future__ import annotations

import hashlib
import io
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

from secop_ii.paths import state_path

log = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = state_path("pdf")
DEFAULT_TIMEOUT_S = 30
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# Keywords we look for in the body to corroborate / refute the Dra.'s
# OBSERVACIONES note. Normalized (no accents, uppercase) before comparison.
_KEYWORDS_MOD = (
    "MODIFICATORIO", "MODIFICACION", "OTROSI", "OTRO SI", "PRORROGA",
    "ADICION", "CESION", "SUSPENSION", "CLAUSULA OCTAVA", "CLAUSULA 8",
    "AMPARO DE CALIDAD",
)
_KEYWORDS_LEG = ("LEGALIZACION", "ACTA DE INICIO", "POLIZA", "GARANTIA")


@dataclass
class PdfSummary:
    """Compact summary of a PDF's content — what we need for auditing."""

    url: str
    cache_path: Path | None
    n_pages: int = 0
    n_chars: int = 0
    engine: str = "none"  # which engine produced the text
    title: str | None = None
    creation_date: str | None = None
    text_preview: str = ""        # first ~800 chars
    keywords_modif: list[str] = field(default_factory=list)
    keywords_leg: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def looks_like_modificatorio(self) -> bool:
        return bool(self.keywords_modif)

    @property
    def looks_scanned(self) -> bool:
        # A PDF with pages but virtually no extractable text is most likely
        # a scan — at the page level we treat <40 chars/page as a signal.
        return self.n_pages > 0 and self.n_chars < 40 * self.n_pages


@dataclass
class PdfReader:
    """Download and parse SECOP II PDFs with on-disk caching."""

    cache_dir: Path = DEFAULT_CACHE_DIR
    timeout_s: int = DEFAULT_TIMEOUT_S

    def __post_init__(self) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------
    def download(self, url: str) -> Path | None:
        """Return a local path to the PDF, downloading if not cached."""
        if not url:
            return None
        target = self._cache_path_for(url)
        if target.exists() and target.stat().st_size > 0:
            return target

        try:
            resp = requests.get(
                url,
                headers={"User-Agent": _USER_AGENT, "Accept": "application/pdf,*/*"},
                timeout=self.timeout_s,
                stream=True,
            )
        except requests.RequestException as exc:
            log.warning("PDF download failed %s: %s", url, exc)
            return None

        if resp.status_code != 200:
            log.warning("PDF download %s -> HTTP %s", url, resp.status_code)
            return None

        # Stream to a temp file then rename — never leave a half-written PDF
        # in the cache (subsequent runs would treat it as valid).
        tmp = target.with_suffix(target.suffix + ".part")
        with tmp.open("wb") as fh:
            for chunk in resp.iter_content(chunk_size=64 * 1024):
                if chunk:
                    fh.write(chunk)
        tmp.replace(target)
        return target

    # ------------------------------------------------------------------
    # Parse
    # ------------------------------------------------------------------
    def summarize(self, url: str, *, max_pages: int = 5) -> PdfSummary:
        """Download (cached) + extract a compact summary from the PDF."""
        path = self.download(url)
        if path is None:
            return PdfSummary(url=url, cache_path=None, error="download_failed")

        try:
            text, n_pages, engine = _extract_text(path, max_pages=max_pages)
        except Exception as exc:  # noqa: BLE001 — last-ditch safety
            return PdfSummary(
                url=url, cache_path=path, error=f"extract_failed: {exc}"
            )

        meta = _extract_meta(path)
        norm = _normalize(text)
        kw_mod = sorted({kw for kw in _KEYWORDS_MOD if _normalize(kw) in norm})
        kw_leg = sorted({kw for kw in _KEYWORDS_LEG if _normalize(kw) in norm})

        return PdfSummary(
            url=url,
            cache_path=path,
            n_pages=n_pages,
            n_chars=len(text),
            engine=engine,
            title=meta.get("title"),
            creation_date=meta.get("creation_date"),
            text_preview=text[:800].strip(),
            keywords_modif=kw_mod,
            keywords_leg=kw_leg,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _cache_path_for(self, url: str) -> Path:
        # Keep the basename of the URL when possible (helps debugging),
        # but prefix with the URL hash so different URLs with the same
        # filename never collide.
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
        suffix = ".pdf"
        return self.cache_dir / f"{digest}{suffix}"


# ---------------------------------------------------------------------------
# Engine cascade
# ---------------------------------------------------------------------------
def _extract_text(path: Path, *, max_pages: int) -> tuple[str, int, str]:
    """Try engines in order, return (text, n_pages, engine_name)."""
    # 1) pdfplumber — best layout, slower
    try:
        import pdfplumber  # type: ignore[import-not-found]

        with pdfplumber.open(str(path)) as pdf:
            n = len(pdf.pages)
            chunks = []
            for i, page in enumerate(pdf.pages[:max_pages]):
                chunks.append(page.extract_text() or "")
            text = "\n".join(chunks)
            if text.strip():
                return text, n, "pdfplumber"
    except Exception as exc:  # noqa: BLE001
        log.debug("pdfplumber failed on %s: %s", path.name, exc)

    # 2) pymupdf (fitz) — fastest, broad font support
    try:
        import fitz  # type: ignore[import-not-found]

        with fitz.open(str(path)) as doc:
            n = doc.page_count
            chunks = []
            for i in range(min(max_pages, n)):
                chunks.append(doc.load_page(i).get_text("text"))
            text = "\n".join(chunks)
            if text.strip():
                return text, n, "pymupdf"
    except Exception as exc:  # noqa: BLE001
        log.debug("pymupdf failed on %s: %s", path.name, exc)

    # 3) pypdf — slow but pure-python
    try:
        from pypdf import PdfReader as _PyPdfReader  # type: ignore[import-not-found]

        reader = _PyPdfReader(str(path))
        n = len(reader.pages)
        chunks = [(reader.pages[i].extract_text() or "") for i in range(min(max_pages, n))]
        text = "\n".join(chunks)
        if text.strip():
            return text, n, "pypdf"
    except Exception as exc:  # noqa: BLE001
        log.debug("pypdf failed on %s: %s", path.name, exc)

    # 4) Tesseract OCR — for scans. We render via pymupdf if present.
    try:
        import fitz  # type: ignore[import-not-found]
        import pytesseract  # type: ignore[import-not-found]
        from PIL import Image  # type: ignore[import-not-found]

        with fitz.open(str(path)) as doc:
            n = doc.page_count
            chunks = []
            for i in range(min(max_pages, n)):
                pix = doc.load_page(i).get_pixmap(dpi=200)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                chunks.append(pytesseract.image_to_string(img, lang="spa"))
            text = "\n".join(chunks)
            if text.strip():
                return text, n, "tesseract-ocr"
    except Exception as exc:  # noqa: BLE001
        log.debug("OCR failed on %s: %s", path.name, exc)

    return "", 0, "none"


def _extract_meta(path: Path) -> dict[str, Any]:
    """Best-effort metadata extraction (title + creation date)."""
    out: dict[str, Any] = {}
    try:
        from pypdf import PdfReader as _PyPdfReader  # type: ignore[import-not-found]

        info = _PyPdfReader(str(path)).metadata or {}
        title = info.get("/Title")
        if title:
            out["title"] = str(title)
        created = info.get("/CreationDate")
        if created:
            out["creation_date"] = str(created)
    except Exception:  # noqa: BLE001
        pass
    return out


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    no_marks = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return no_marks.upper()


__all__ = ["PdfReader", "PdfSummary"]
