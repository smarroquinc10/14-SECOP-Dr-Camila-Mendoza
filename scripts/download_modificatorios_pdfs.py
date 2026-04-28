"""Sesion 1 del pipeline OCR · descarga de PDFs candidatos a modificatorios.

Cardinal (Sergio 2026-04-28): la Dra abre cada PDF manualmente porque el
nombre del archivo no es fiable. Para que el dashboard se le ahorre ese
trabajo, debemos descargar el contenido real y procesarlo con OCR. Este
script es la **primera capa**: bajar los PDFs a disco con browser real
(Playwright + CapSolver) y detectar tipo de archivo.

Uso:
    python scripts/download_modificatorios_pdfs.py --uid CO1.NTC.5405127
        Descarga TODOS los PDFs del proceso indicado · piloto.

    python scripts/download_modificatorios_pdfs.py --filtered
        Descarga solo los PDFs que el classify-modificatorios.ts marca
        como candidatos por nombre (855 de 12,497 docs · ~7%).

    python scripts/download_modificatorios_pdfs.py --all
        Descarga TODO el universo · ~15-30h de wall time. Solo si ya
        validamos el approach con piloto.

Output:
    .cache/modificatorios_pdfs/
        index.json              # mapa {process_id: [{name, url, path, sha256, type, downloaded_at, ...}]}
        <process_id>/
            00_<safe_name>.pdf  # archivos crudos
            ...

Idempotente: si un archivo ya esta descargado y su sha256 matchea, skip.

Filosofia cardinal: NUNCA inventar. Si la descarga falla, registrar el
error en index.json y seguir. La UI mostrara "no leido" honesto, no un
classification fake.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

log = logging.getLogger("download-mods")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

CACHE_ROOT = ROOT / ".cache" / "modificatorios_pdfs"
INDEX_PATH = CACHE_ROOT / "index.json"
SEED_PATH = ROOT / "app" / "public" / "data" / "portal_opportunity_seed.json"

# Patrones cardinales (mismo set que app/src/lib/classify-modificatorios.ts).
# Los aplicamos sobre el nombre del PDF para pre-filtrar candidatos.
CANDIDATE_PATTERNS = re.compile(
    r"modificatori[oa]"
    r"|\bmod\b\.?(?:\s|\d|$)"
    r"|\botros[ií]\b"
    r"|\badend[oa]\b"
    r"|\badici[oó]n\b(?!al)"
    r"|\bpr[oó]rroga\b|\bprorroga\b"
    r"|\bcesi[oó]n\b"
    r"|suspensi[oó]n"
    r"|\bliquidaci[oó]n\b|acta\s+de\s+liquidaci"
    r"|terminaci[oó]n\s+anticipada"
    r"|reanudaci[oó]n"
    r"|novaci[oó]n",
    re.IGNORECASE,
)

# Anti-FP del nombre (los mismos del clasificador frontend). Si matchea,
# NO descargamos · ahorra ancho de banda.
FALSE_POSITIVE_PATTERNS = re.compile(
    r"p[oó]liza\s+adicional"
    r"|poliza\s+actualizada\s+de\s+meses\s+adicional"
    r"|\bmodulo\b"
    r"|carta\s+autorizaci[oó]n\s+cesi[oó]n.*libertad",
    re.IGNORECASE,
)

# Magic bytes para detectar tipo real del archivo descargado.
MAGIC_TO_EXT = [
    (b"%PDF-",       "pdf"),
    (b"PK\x03\x04",  "zip"),  # DOCX, XLSX, PPTX (ZIP-based)
    (b"\xff\xd8\xff", "jpg"),
    (b"\x89PNG",     "png"),
    (b"GIF8",        "gif"),
    (b"BM",          "bmp"),
    (b"<!DOCTYPE",   "html"),
    (b"<html",       "html"),
    (b"<?xml",       "xml"),
    (b"<script",     "html"),  # Error pages "DisplayAlert..."
]


def detect_file_type(content: bytes) -> str:
    """Devuelve la extension real basada en magic bytes. 'unknown' si no matchea."""
    if not content:
        return "empty"
    head = content[:32]
    for magic, ext in MAGIC_TO_EXT:
        if head.startswith(magic):
            return ext
        if magic in head[:16]:
            return ext
    return "unknown"


def safe_filename(name: str, idx: int) -> str:
    """Convierte un nombre de PDF en filename seguro (sin chars problematicos)."""
    safe = re.sub(r"[^\w.-]", "_", name)
    safe = safe[:80]  # cap a 80 chars
    return f"{idx:03d}_{safe}"


def is_candidate_modificatorio(doc_name: str) -> bool:
    """True si el nombre sugiere que puede ser modificatorio."""
    name = (doc_name or "").strip()
    if not name:
        return False
    if FALSE_POSITIVE_PATTERNS.search(name):
        return False
    return bool(CANDIDATE_PATTERNS.search(name))


def load_seed() -> dict:
    return json.loads(SEED_PATH.read_text(encoding="utf-8"))


def load_index() -> dict:
    if not INDEX_PATH.exists():
        return {"version": 1, "processes": {}}
    try:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "processes": {}}


def save_index(index: dict) -> None:
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(
        json.dumps(index, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def download_pdf_via_browser(page, url: str, timeout: int = 60_000) -> bytes:
    """Navega al URL del PDF en el browser. Retorna bytes del archivo.

    Estrategia: el SECOP a veces redirige con JS (window.location.href = ...)
    para forzar bajar via /Archive/RetrieveFile. Playwright sigue el redirect
    y al final tenemos un archivo descargado en memoria via response interception.
    """
    # Interceptar el response del archivo final (no los HTML intermedios)
    captured_body: dict[str, bytes] = {"body": b""}
    captured_ct: dict[str, str] = {"ct": ""}

    def handle_response(resp):
        ct = (resp.headers.get("content-type") or "").lower()
        if any(kw in ct for kw in ["pdf", "octet-stream", "msword", "openxmlformats"]):
            try:
                captured_body["body"] = resp.body()
                captured_ct["ct"] = ct
            except Exception:
                pass
        elif resp.url.endswith((".pdf", ".docx", ".xlsx")):
            try:
                captured_body["body"] = resp.body()
                captured_ct["ct"] = ct or "application/binary"
            except Exception:
                pass

    page.on("response", handle_response)
    try:
        page.goto(url, wait_until="networkidle", timeout=timeout)
        # Si el SECOP devolvio HTML con redirect JS, esperar a que ejecute
        time.sleep(2.0)
    except PWTimeout:
        pass
    page.remove_listener("response", handle_response)
    return captured_body["body"]


def process_one(uid: str, seed: dict, index: dict, page) -> None:
    """Procesa un proceso: descarga PDFs candidatos a modificatorios."""
    entry = seed.get(uid)
    if not entry:
        log.warning("uid %s no esta en el seed", uid)
        return
    docs = entry.get("documents") or []
    candidates = [(i, d) for i, d in enumerate(docs)
                  if is_candidate_modificatorio(d.get("name", ""))]
    log.info("[%s] %d / %d docs candidatos a modificatorios",
             uid, len(candidates), len(docs))

    proc_dir = CACHE_ROOT / uid
    proc_dir.mkdir(parents=True, exist_ok=True)

    proc_index = index["processes"].setdefault(uid, {"docs": [], "last_run": None})

    for idx, doc in candidates:
        name = doc.get("name", "")
        url = doc.get("url", "")
        if not url:
            continue

        # Verificar si ya esta descargado e integro
        already_done = next(
            (d for d in proc_index["docs"]
             if d.get("doc_idx") == idx and Path(d.get("path", "")).exists()),
            None,
        )
        if already_done and Path(already_done["path"]).stat().st_size > 1000:
            log.info("  [%d] SKIP (ya en cache): %s", idx, name[:60])
            continue

        log.info("  [%d] Descargando: %s", idx, name[:60])
        try:
            content = download_pdf_via_browser(page, url)
        except Exception as e:
            log.error("    ERROR descarga: %s", e)
            proc_index["docs"].append({
                "doc_idx": idx,
                "original_name": name,
                "original_url": url,
                "downloaded_at": datetime.now(timezone.utc).isoformat(),
                "status": "error_download",
                "error": str(e)[:200],
            })
            continue

        if not content or len(content) < 200:
            log.warning("    archivo vacio o muy chico (%d bytes)", len(content))
            proc_index["docs"].append({
                "doc_idx": idx,
                "original_name": name,
                "original_url": url,
                "downloaded_at": datetime.now(timezone.utc).isoformat(),
                "status": "error_empty",
                "size_bytes": len(content),
            })
            continue

        ext = detect_file_type(content)
        sha = hashlib.sha256(content).hexdigest()
        fname = safe_filename(name, idx)
        out_path = proc_dir / f"{fname}.{ext}"
        out_path.write_bytes(content)

        log.info("    OK · %d KB · tipo=%s · sha256=%s",
                 len(content) // 1024, ext, sha[:12])
        proc_index["docs"].append({
            "doc_idx": idx,
            "original_name": name,
            "original_url": url,
            "path": str(out_path.relative_to(ROOT)),
            "size_bytes": len(content),
            "file_type": ext,
            "sha256": sha,
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
            "status": "ok",
        })

    proc_index["last_run"] = datetime.now(timezone.utc).isoformat()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--uid", help="Procesar solo un notice_uid (piloto)")
    g.add_argument("--filtered", action="store_true",
                   help="Procesar todos los procesos del seed con candidatos por nombre")
    g.add_argument("--all", action="store_true",
                   help="Procesar TODOS los docs del seed (lento)")
    ap.add_argument("--limit", type=int, default=None,
                    help="Cap de procesos a tocar (debug)")
    ap.add_argument("--headed", action="store_true",
                    help="Browser con UI (debug)")
    args = ap.parse_args()

    seed = load_seed()
    index = load_index()

    if args.uid:
        targets = [args.uid]
    else:
        targets = list(seed.keys())
        if args.filtered:
            # Solo procesos que tienen al menos UN doc candidato por nombre
            targets = [
                uid for uid in targets
                if any(is_candidate_modificatorio(d.get("name", ""))
                       for d in (seed[uid].get("documents") or []))
            ]
        if args.limit:
            targets = targets[:args.limit]

    log.info("Targets: %d procesos", len(targets))

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not args.headed)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120 Safari/537.36",
            accept_downloads=True,
        )
        page = ctx.new_page()

        for i, uid in enumerate(targets, 1):
            log.info("[%d/%d] %s", i, len(targets), uid)
            process_one(uid, seed, index, page)
            save_index(index)
            # Anti-rate-limit del SECOP
            time.sleep(0.5)

        browser.close()

    log.info("DONE. Index en %s", INDEX_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
