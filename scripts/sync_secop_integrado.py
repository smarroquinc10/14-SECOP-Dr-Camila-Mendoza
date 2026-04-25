"""Sincroniza el dataset SECOP Integrado (rpmr-utcd) para FEAB.

Este dataset combina SECOP I + SECOP II + procesos finalizados y expone
~382 procesos del FEAB con sus campos clave (numero_del_contrato,
numero_de_proceso, valor_contrato, estado_del_proceso, url_contrato con
notice_uid, fechas, contratista, etc.) — TODO sin captcha, vía API
pública de datos.gov.co.

Estrategia: este endpoint resuelve la MAYORÍA de los 201 procesos que
``p6dx-8zbt`` (Procesos) + ``jbjy-vk9h`` (Contratos) no exponen, sin
necesidad de scrapear el portal community.secop.gov.co. El scraper queda
como fallback para los pocos que ni rpmr-utcd tenga.

Uso:
    python scripts/sync_secop_integrado.py
        # Descarga TODOS los procesos del FEAB (NIT 901148337) y los
        # persiste en .cache/secop_integrado.json indexado por
        # notice_uid extraído de url_contrato.

    python scripts/sync_secop_integrado.py --nit 901148337
        # Otro NIT (por si la Dra tiene otra entidad).

Filosofía cardinal: ESPEJO del SECOP. Estos campos vienen 1:1 del API
público — no inventamos nada. Si rpmr-utcd no tiene un proceso, el
cache no lo guarda y la UI sigue mostrando "—" honesto.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
# In dev ROOT/src is on sys.path via the editable install; in a frozen
# bundle the package is already importable. This insertion is a no-op
# in both contexts but lets the script work when invoked directly with
# a bare ``python scripts/sync_secop_integrado.py`` from the repo.
sys.path.insert(0, str(ROOT / "src"))

from secop_ii.paths import state_path  # noqa: E402  (post-sys.path setup)

# Cache is written to a per-environment state directory (see paths.py).
# In dev this is ``<repo>/.cache/secop_integrado.json``; in the MSI it
# lives under ``%LOCALAPPDATA%\Dra Cami Contractual\.cache\``.
CACHE_PATH = state_path("secop_integrado.json")

# NIT del FEAB (Fondo Especial para la Administración de Bienes,
# Fiscalía General de la Nación) — el filtro por defecto.
DEFAULT_NIT = "901148337"

DATASET_URL = "https://www.datos.gov.co/resource/rpmr-utcd.json"
PAGE_SIZE = 1000  # Socrata cap por request

# Campos que sí guardamos. Toda metadata cruda — NUNCA derivamos campos
# del Excel para llenar gaps. Si un campo viene null/vacío del API,
# queda null/vacío (la UI muestra "—" honesto).
KEEP_FIELDS = (
    "nivel_entidad",
    "codigo_entidad_en_secop",
    "nombre_de_la_entidad",
    "nit_de_la_entidad",
    "departamento_entidad",
    "municipio_entidad",
    "estado_del_proceso",
    "modalidad_de_contrataci_n",
    "objeto_a_contratar",
    "objeto_del_proceso",
    "tipo_de_contrato",
    "fecha_de_firma_del_contrato",
    "fecha_inicio_ejecuci_n",
    "fecha_fin_ejecuci_n",
    "numero_del_contrato",
    "numero_de_proceso",
    "valor_contrato",
    "nom_raz_social_contratista",
    "url_contrato",
    "origen",
    "tipo_documento_proveedor",
    "documento_proveedor",
)

_NOTICE_RE = re.compile(r"noticeUID=(CO1\.NTC\.\d+)", re.IGNORECASE)
_PCCNTR_RE = re.compile(r"(CO1\.PCCNTR\.\d+)", re.IGNORECASE)


def _extract_notice_uid(url: str | None) -> str | None:
    if not url:
        return None
    m = _NOTICE_RE.search(url)
    return m.group(1) if m else None


def _fetch_all(nit: str) -> list[dict]:
    """Pagina rpmr-utcd hasta agotar resultados para un NIT."""
    out: list[dict] = []
    offset = 0
    while True:
        params = {
            "nit_de_la_entidad": nit,
            "$limit": PAGE_SIZE,
            "$offset": offset,
            "$order": "fecha_de_firma_del_contrato DESC",
        }
        resp = requests.get(DATASET_URL, params=params, timeout=30)
        resp.raise_for_status()
        chunk = resp.json()
        if not chunk:
            break
        out.extend(chunk)
        if len(chunk) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--nit",
        default=DEFAULT_NIT,
        help=f"NIT de la entidad (default: {DEFAULT_NIT} = FEAB)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s · %(message)s",
    )

    print(f"→ Sincronizando rpmr-utcd (SECOP Integrado) para NIT {args.nit}…")
    started = time.monotonic()
    try:
        rows = _fetch_all(args.nit)
    except requests.HTTPError as exc:
        print(f"✗ Error HTTP del API: {exc}", file=sys.stderr)
        return 2

    print(f"  ↳ {len(rows)} procesos descargados en {time.monotonic()-started:.1f}s")

    # Index by notice_uid extracted from url_contrato. If url has no
    # noticeUID we index by numero_del_contrato as fallback (CO1.PCCNTR).
    indexed: dict[str, dict] = {}
    by_pccntr: dict[str, dict] = {}
    no_key = 0
    for row in rows:
        kept = {k: row.get(k) for k in KEEP_FIELDS}
        notice_uid = _extract_notice_uid(kept.get("url_contrato"))
        if notice_uid:
            kept["_notice_uid"] = notice_uid
            indexed[notice_uid] = kept
        pccntr = kept.get("numero_del_contrato") or ""
        if pccntr.startswith("CO1.PCCNTR."):
            by_pccntr[pccntr] = kept
        if not notice_uid and not pccntr:
            no_key += 1

    payload = {
        "synced_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": DATASET_URL,
        "nit": args.nit,
        "total_rows": len(rows),
        "by_notice_uid": indexed,
        "by_pccntr": by_pccntr,
        "no_key_count": no_key,
    }

    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(
        f"✓ Persistido en {CACHE_PATH}\n"
        f"  · indexado por notice_uid: {len(indexed)}\n"
        f"  · indexado por PCCNTR:     {len(by_pccntr)}\n"
        f"  · sin key:                  {no_key}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
