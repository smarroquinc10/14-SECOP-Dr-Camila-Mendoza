"""Backfill `scraped_at` y `status` en portal_opportunity_seed.json.

El seed bakeado pre-databa el campo `scraped_at` de PortalScraper, así que
las 66 entries que la app sirve hoy aparecen sin metadata de antigüedad.
La UI las renderiza con badge verde "Proceso verificado" sin pista de
cuán viejas son. Cardinal violation menor (provenance ambigua).

Este script es idempotente:

  - Si la entry NO tiene `scraped_at`, lo setea al mtime del archivo seed
    (mejor estimación que tenemos para entradas legacy).
  - Si la entry NO tiene `status`, lo setea a `ok_completo` (porque la
    entry existe en cache, eso significa que el scraper logró completarla).
  - Si AMBOS ya están, no toca nada.

Después de correr esto, refresh-seeds.ps1 + update.bat publica el cambio
y la UI puede renderizar la antigüedad real con el bug-004 fix.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED_PATH = ROOT / "app" / "public" / "data" / "portal_opportunity_seed.json"


def main() -> int:
    if not SEED_PATH.exists():
        print(f"✗ Seed no existe: {SEED_PATH}")
        return 2

    seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    if not isinstance(seed, dict):
        print(f"✗ Seed no es un dict (shape inesperado)")
        return 2

    # mtime del archivo como floor — sabemos que el scrape se hizo antes
    # o en ese momento. ISO con segundos.
    mtime = datetime.fromtimestamp(SEED_PATH.stat().st_mtime, tz=timezone.utc)
    fallback_ts = mtime.isoformat(timespec="seconds")

    stamped = 0
    untouched = 0
    for uid, entry in seed.items():
        if not isinstance(entry, dict):
            continue
        changed = False
        if not entry.get("scraped_at"):
            entry["scraped_at"] = fallback_ts
            changed = True
        if not entry.get("status"):
            entry["status"] = "ok_completo"
            changed = True
        if changed:
            stamped += 1
        else:
            untouched += 1

    SEED_PATH.write_text(
        json.dumps(seed, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(
        f"✓ Stamped {stamped} entries con scraped_at={fallback_ts} y/o status=ok_completo. "
        f"{untouched} ya tenían ambos."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
