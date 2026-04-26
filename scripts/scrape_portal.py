"""Orquestador batch para scrapear el portal SECOP de los procesos que el
API público de datos.gov.co no expone.

Uso típico (la Dra hace doble-click en ``ejecutar_scraper.bat``):

    python scripts/scrape_portal.py
        # Scrapea todos los notice_uid del watch list que NO están aún
        # en .cache/portal_opportunity.json. Reporta progreso por consola
        # y persiste cada resultado en el cache compartido.

Otros modos:

    python scripts/scrape_portal.py --uid CO1.NTC.5405127
        # Scrapea uno solo (forzar refresh).

    python scripts/scrape_portal.py --limit 10
        # Solo los primeros 10 faltantes (útil para probar).

    python scripts/scrape_portal.py --uids-file uids.txt
        # Lista explícita, un notice_uid por línea.

    python scripts/scrape_portal.py --progress-file .cache/portal_progress.jsonl
        # Escribe una línea JSON por proceso para que la UI siga el avance
        # vía /portal-progress (igual que /verify-progress).

Filosofía cardinal: la verdad vive en SECOP. Si el API público no expone
un proceso, lo leemos directo del portal — pero NUNCA lo inventamos del
Excel. Si el portal tampoco responde, el cache queda con status =
``error_red`` o ``bloqueado_captcha`` y la UI muestra "—" honesto + el
motivo del fallo.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# Cargar .env del repo - necesario para que portal_scraper.py vea
# CAPSOLVER_API_KEY (cuando esta configurado, el solver lib pasa los
# captchas que falla automaticamente al servicio CapSolver, ~$0.001/captcha,
# 99.9% exito). Si .env no existe o no tiene la key, el solver opera en
# modo gratuito (cookies + Whisper + manual). Ver SCRAPER_SETUP.md.
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass  # python-dotenv no instalado - operacion sin .env

from secop_ii.paths import state_path  # noqa: E402  (post-sys.path setup)
from secop_ii.portal_scraper import (  # noqa: E402  (post-sys.path setup)
    PortalScraper,
    STATUS_NETWORK_ERROR,
)

log = logging.getLogger("scrape-portal")

WATCH_PATH = state_path("watched_urls.json")
PORTAL_CACHE_PATH = state_path("portal_opportunity.json")


def _load_watch_list() -> list[dict]:
    if not WATCH_PATH.exists():
        return []
    return json.loads(WATCH_PATH.read_text(encoding="utf-8"))


def _load_portal_cache() -> dict[str, dict]:
    if not PORTAL_CACHE_PATH.exists():
        return {}
    try:
        return json.loads(PORTAL_CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _candidate_uids(args: argparse.Namespace) -> list[str]:
    """Decide qué notice_uids scrapear según flags + cache."""
    if args.uid:
        return [args.uid]
    if args.uids_file:
        return [
            line.strip()
            for line in Path(args.uids_file).read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        ]
    watched = _load_watch_list()
    cache = _load_portal_cache()
    pending: list[str] = []
    seen: set[str] = set()
    for it in watched:
        uid = (it.get("notice_uid") or "").strip()
        if not uid or uid in seen:
            continue
        seen.add(uid)
        if uid in cache and not args.force:
            cached = cache[uid]
            # Re-scrapear si quedó parcial / errored / sin status (cache viejo)
            if cached.get("status") in (None, "ok_completo"):
                continue
        pending.append(uid)
    if args.limit:
        pending = pending[: args.limit]
    return pending


def _write_progress(path: Path, payload: dict) -> None:
    """Append-only progress log, JSONL — paralelo al verify_watch_list."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError as exc:
        log.warning("No pude escribir progress %s: %s", path, exc)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--uid", help="Un solo notice_uid (CO1.NTC.X)")
    parser.add_argument("--uids-file", help="Archivo con notice_uids, uno por línea")
    parser.add_argument("--limit", type=int, help="Máximo de procesos a scrapear")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-scrapea aunque ya estén completos en cache",
    )
    parser.add_argument(
        "--progress-file",
        type=Path,
        default=state_path("portal_progress.jsonl"),
        help="Archivo JSONL donde escribir progreso (UI lo lee)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s · %(message)s",
    )

    pending = _candidate_uids(args)
    if not pending:
        print("✓ No hay procesos pendientes — todo el watch list ya está scrapeado.")
        return 0

    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(
        f"→ Scraper portal SECOP — {len(pending)} procesos pendientes "
        f"(ETA estimado ~{len(pending) * 45 // 60} min)\n"
        f"  Cache:    {PORTAL_CACHE_PATH}\n"
        f"  Progreso: {args.progress_file}\n"
    )

    # Header del progress file: total + timestamp inicio. La UI lo lee
    # para pintar la barra y calcular ETA igual que /verify-progress.
    if args.progress_file:
        # Reset progress: nueva corrida = nuevo archivo. Mantenemos el
        # anterior con sufijo .bak por si el usuario quiere rastrear.
        if args.progress_file.exists():
            backup = args.progress_file.with_suffix(
                f".jsonl.bak.{int(time.time())}"
            )
            try:
                args.progress_file.rename(backup)
            except OSError:
                pass
        _write_progress(
            args.progress_file,
            {
                "event": "start",
                "total": len(pending),
                "started_at": started_at,
            },
        )

    ok = 0
    partial = 0
    errored = 0
    started_mono = time.monotonic()

    with PortalScraper() as scraper:
        for idx, uid in enumerate(pending, 1):
            elapsed = time.monotonic() - started_mono
            avg = elapsed / max(idx - 1, 1) if idx > 1 else 45.0
            eta = avg * (len(pending) - idx + 1)
            print(
                f"[{idx:>3}/{len(pending)}] {uid}  "
                f"(elapsed {elapsed:5.0f}s · ETA ~{eta / 60:4.1f} min)",
                flush=True,
            )
            # Timeout duro per-item con concurrent.futures (Errores #7 + #8):
            # garantiza que NUNCA un item cuelgue silenciosamente al batch.
            # Si supera 5 min, marcamos timeout y seguimos con el siguiente.
            # Esto cumple la regla cardinal "el bot nunca muere" del RUNT.
            from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
            ITEM_TIMEOUT_S = 300  # 5 min hard cap per item
            try:
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(scraper.fetch, uid)
                    try:
                        data = future.result(timeout=ITEM_TIMEOUT_S)
                    except FutTimeout:
                        log.warning(
                            "Timeout duro %ds excedido para %s — kill + next",
                            ITEM_TIMEOUT_S, uid
                        )
                        future.cancel()
                        errored += 1
                        _write_progress(
                            args.progress_file,
                            {
                                "event": "item",
                                "idx": idx,
                                "uid": uid,
                                "status": "timeout_hard",
                                "documents": 0,
                                "missing": [],
                                "scraped_at": None,
                            },
                        )
                        print(f"     status=timeout_hard  (excedio {ITEM_TIMEOUT_S}s)", flush=True)
                        continue
            except KeyboardInterrupt:
                print("\n✗ Interrumpido por el usuario.")
                _write_progress(
                    args.progress_file,
                    {"event": "interrupted", "uid": uid, "idx": idx},
                )
                return 130
            except Exception as exc:  # noqa: BLE001 — broad pero loggeada
                log.exception("Error inesperado scrapeando %s", uid)
                errored += 1
                _write_progress(
                    args.progress_file,
                    {
                        "event": "error",
                        "uid": uid,
                        "idx": idx,
                        "message": str(exc)[:300],
                    },
                )
                continue

            status = (data.status if data else STATUS_NETWORK_ERROR)
            missing = data.missing_fields if data else []
            doc_count = len(data.documents) if data else 0
            if data is None:
                errored += 1
            elif status == "ok_completo":
                ok += 1
            else:
                partial += 1

            print(
                f"     status={status}  docs={doc_count}  "
                f"missing={','.join(missing) if missing else '—'}",
                flush=True,
            )
            _write_progress(
                args.progress_file,
                {
                    "event": "item",
                    "idx": idx,
                    "uid": uid,
                    "status": status,
                    "documents": doc_count,
                    "missing": missing,
                    "scraped_at": data.scraped_at if data else None,
                },
            )

    total_elapsed = time.monotonic() - started_mono
    summary = {
        "event": "done",
        "total": len(pending),
        "ok": ok,
        "partial": partial,
        "errored": errored,
        "elapsed_seconds": round(total_elapsed, 1),
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    _write_progress(args.progress_file, summary)

    print(
        f"\n✓ Listo. {ok} completos · {partial} parciales · {errored} errores · "
        f"{total_elapsed / 60:.1f} min totales."
    )
    return 0 if errored == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
