"""Sesion 2 del pipeline OCR · descarga de PDFs candidatos a modificatorios.

Estrategia cardinal:
  1. Para cada doc candidato, probar primero requests directo con
     followredirects=True. El SECOP a veces redirige con HTML+JS pero
     a veces devuelve el archivo en el primer hit.
  2. Si requests devuelve un HTML con redirect JS, parsear el target
     y reintentar (por eso pasamos por /Archive/RetrieveFile).
  3. Detectar magic bytes para determinar tipo real (PDF/DOCX/XLSX/error).
  4. Si nada funciona, marcar como error · NO inventar.

Uso:
    python scripts/download_modificatorios_pdfs.py --uid CO1.NTC.5405127
        Piloto · descarga TODOS los candidatos del proceso.

    python scripts/download_modificatorios_pdfs.py --filtered --limit 5
        Sample · primeros 5 procesos con candidatos.

    python scripts/download_modificatorios_pdfs.py --filtered
        Procesar TODOS los procesos del seed con candidatos por nombre.

Filosofia cardinal: 0 datos comidos. Si la descarga falla por error
del SECOP (ID muerto, archivo movido), queda en index.json con status
y motivo · NO se descarta silenciosamente.
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

import requests

ROOT = Path(__file__).resolve().parent.parent
CACHE_ROOT = ROOT / ".cache" / "modificatorios_pdfs"
INDEX_PATH = CACHE_ROOT / "index.json"
SEED_PATH = ROOT / "app" / "public" / "data" / "portal_opportunity_seed.json"

log = logging.getLogger("download-mods")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

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

FALSE_POSITIVE_PATTERNS = re.compile(
    r"p[oó]liza\s+adicional"
    r"|poliza\s+actualizada\s+de\s+meses\s+adicional"
    r"|\bmodulo\b"
    r"|carta\s+autorizaci[oó]n\s+cesi[oó]n.*libertad",
    re.IGNORECASE,
)

MAGIC_TO_EXT = [
    (b"%PDF-", "pdf"),
    (b"PK\x03\x04", "zip"),  # DOCX, XLSX, PPTX (ZIP-based)
    (b"\xff\xd8\xff", "jpg"),
    (b"\x89PNG", "png"),
    (b"GIF8", "gif"),
    (b"BM", "bmp"),
]

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
    ),
}


def detect_file_type(content: bytes) -> str:
    if not content:
        return "empty"
    head = content[:32]
    for magic, ext in MAGIC_TO_EXT:
        if head.startswith(magic):
            return ext
    head_str = content[:200].decode("latin-1", errors="replace").lower()
    if "displayalert" in head_str and "error" in head_str:
        return "error_secop"  # "An error occorred" del SECOP
    if "<html" in head_str or "<!doctype" in head_str:
        return "html"
    if "window.location.href" in head_str:
        return "html_redirect"
    return "unknown"


def safe_filename(name: str, idx: int) -> str:
    safe = re.sub(r"[^\w.-]", "_", name)
    safe = safe[:80]
    return f"{idx:03d}_{safe}"


def is_candidate_modificatorio(doc_name: str) -> bool:
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


# Regex para extraer redirect JS del SECOP
REDIRECT_RE = re.compile(
    r"window\.location\.href\s*=\s*['\"]([^'\"]+)['\"]",
    re.IGNORECASE,
)


def download_with_requests(url: str, max_redirects: int = 3) -> bytes:
    """Descarga con requests siguiendo redirects (incluyendo JS-based).

    Si el SECOP devuelve <script>window.location.href = '...'</script>,
    parsea el destino y reintenta. Hasta max_redirects niveles.
    """
    sess = requests.Session()
    sess.headers.update(UA)
    current_url = url
    for attempt in range(max_redirects + 1):
        r = sess.get(current_url, timeout=60, allow_redirects=True)
        r.raise_for_status()
        body = r.content
        # Si es archivo binario válido, devolver
        ext = detect_file_type(body)
        if ext in ("pdf", "zip", "jpg", "png", "gif", "bmp"):
            return body
        if ext == "error_secop":
            return body  # devolvemos para que el caller marque error
        # Si es HTML con redirect JS, parsear
        if ext in ("html_redirect", "html"):
            text = body.decode("latin-1", errors="replace")
            m = REDIRECT_RE.search(text)
            if m:
                target = m.group(1)
                if target.startswith("/"):
                    from urllib.parse import urlparse
                    parsed = urlparse(current_url)
                    target = f"{parsed.scheme}://{parsed.netloc}{target}"
                current_url = target
                continue
        # Algo distinto · devolvemos como está y dejamos al caller decidir
        return body
    return b""


def process_one(uid: str, seed: dict, index: dict) -> dict:
    """Procesa un proceso: descarga PDFs candidatos a modificatorios.
    Devuelve stats {ok, error_secop, error_other, skipped}."""
    entry = seed.get(uid)
    if not entry:
        log.warning("uid %s no esta en el seed", uid)
        return {"ok": 0, "error": 0, "skipped": 0}
    docs = entry.get("documents") or []
    candidates = [
        (i, d) for i, d in enumerate(docs)
        if is_candidate_modificatorio(d.get("name", ""))
    ]

    proc_dir = CACHE_ROOT / uid
    proc_dir.mkdir(parents=True, exist_ok=True)

    proc_index = index["processes"].setdefault(
        uid, {"docs": [], "last_run": None},
    )
    existing_idx = {d.get("doc_idx"): d for d in proc_index["docs"]}

    stats = {"ok": 0, "error_secop": 0, "error_other": 0, "skipped": 0}

    log.info("[%s] %d / %d docs candidatos", uid, len(candidates), len(docs))
    for idx, doc in candidates:
        name = doc.get("name", "")
        url = doc.get("url", "")
        if not url:
            continue

        # Skip si ya fue descargado correctamente
        prev = existing_idx.get(idx)
        if prev and prev.get("status") == "ok":
            path = ROOT / prev.get("path", "")
            if path.exists() and path.stat().st_size > 1000:
                stats["skipped"] += 1
                continue

        log.info("  [%d] %s", idx, name[:70])
        try:
            content = download_with_requests(url)
        except Exception as e:
            log.error("    ERROR red: %s", str(e)[:100])
            entry_idx = {
                "doc_idx": idx,
                "original_name": name,
                "original_url": url,
                "downloaded_at": datetime.now(timezone.utc).isoformat(),
                "status": "error_red",
                "error": str(e)[:200],
            }
            _replace_or_append(proc_index["docs"], entry_idx, idx)
            stats["error_other"] += 1
            continue

        ext = detect_file_type(content)
        if ext == "error_secop":
            log.warning("    SECOP devolvió error · ID muerto")
            entry_idx = {
                "doc_idx": idx,
                "original_name": name,
                "original_url": url,
                "downloaded_at": datetime.now(timezone.utc).isoformat(),
                "status": "error_secop",
                "size_bytes": len(content),
            }
            _replace_or_append(proc_index["docs"], entry_idx, idx)
            stats["error_secop"] += 1
            continue

        if ext in ("html", "html_redirect", "unknown") or not content:
            log.warning(
                "    descarga inválida · ext=%s · size=%d", ext, len(content),
            )
            entry_idx = {
                "doc_idx": idx,
                "original_name": name,
                "original_url": url,
                "downloaded_at": datetime.now(timezone.utc).isoformat(),
                "status": "error_invalid",
                "detected_type": ext,
                "size_bytes": len(content),
            }
            _replace_or_append(proc_index["docs"], entry_idx, idx)
            stats["error_other"] += 1
            continue

        sha = hashlib.sha256(content).hexdigest()
        fname = safe_filename(name, idx)
        out_path = proc_dir / f"{fname}.{ext}"
        out_path.write_bytes(content)

        log.info(
            "    OK · %d KB · tipo=%s · sha=%s",
            len(content) // 1024, ext, sha[:12],
        )
        entry_idx = {
            "doc_idx": idx,
            "original_name": name,
            "original_url": url,
            "path": str(out_path.relative_to(ROOT)).replace("\\", "/"),
            "size_bytes": len(content),
            "file_type": ext,
            "sha256": sha,
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
            "status": "ok",
        }
        _replace_or_append(proc_index["docs"], entry_idx, idx)
        stats["ok"] += 1

    proc_index["last_run"] = datetime.now(timezone.utc).isoformat()
    return stats


def _replace_or_append(items: list, new_entry: dict, doc_idx: int) -> None:
    for i, e in enumerate(items):
        if e.get("doc_idx") == doc_idx:
            items[i] = new_entry
            return
    items.append(new_entry)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--uid", help="Procesar solo un notice_uid (piloto)")
    g.add_argument("--filtered", action="store_true",
                   help="Procesar todos los procesos con candidatos")
    g.add_argument("--all", action="store_true",
                   help="Procesar TODOS los docs del seed (lento)")
    ap.add_argument("--limit", type=int, default=None,
                    help="Cap de procesos a tocar (debug)")
    args = ap.parse_args()

    seed = load_seed()
    index = load_index()

    if args.uid:
        targets = [args.uid]
    else:
        targets = list(seed.keys())
        if args.filtered:
            targets = [
                uid for uid in targets
                if any(
                    is_candidate_modificatorio(d.get("name", ""))
                    for d in (seed[uid].get("documents") or [])
                )
            ]
        if args.limit:
            targets = targets[:args.limit]

    log.info("Targets: %d procesos", len(targets))

    totals = {"ok": 0, "error_secop": 0, "error_other": 0, "skipped": 0}
    for i, uid in enumerate(targets, 1):
        log.info("[%d/%d] %s", i, len(targets), uid)
        stats = process_one(uid, seed, index)
        for k, v in stats.items():
            totals[k] = totals.get(k, 0) + v
        save_index(index)
        time.sleep(0.3)  # Anti-rate-limit del SECOP

    log.info("=" * 60)
    log.info("DONE. Totales: %s", totals)
    log.info("Index: %s", INDEX_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
