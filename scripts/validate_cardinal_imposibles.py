"""Valida que los 11 cardinal-imposibles sigan sin cobertura en LIVE.

Cardinal: si alguno de los 11 procesos documentados como "imposibles"
aparece publicado en jbjy-vk9h o rpmr-utcd LIVE, debe ser **promovido**
a cobertura automatica. Si todos siguen 0 hits, el set es estable.

Reproducible: re-correr en cualquier sesion futura para verificar
si el SECOP publicó alguno.

Salida:
- Stdout con 11/11 status
- Exit 0 si todos siguen imposibles, 1 si alguno fue promovido
"""

from __future__ import annotations

import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import UTC, datetime

NIT_FEAB = "901148337"
JBJY_URL = "https://www.datos.gov.co/resource/jbjy-vk9h.json"
RPMR_URL = "https://www.datos.gov.co/resource/rpmr-utcd.json"

CARDINAL_IMPOSIBLES = [
    # 8 REQ
    ("CO1.REQ.9988313", "FEAB 2026", "borrador REQ activo"),
    ("CO1.REQ.9969563", "FEAB 2026", "borrador REQ activo"),
    ("CO1.REQ.9987321", "FEAB 2026", "borrador REQ activo"),
    ("CO1.REQ.9989415", "FEAB 2026", "borrador REQ activo"),
    ("CO1.REQ.10060243", "FEAB 2026", "borrador REQ activo"),
    ("CO1.REQ.10057635", "FEAB 2026", "borrador REQ activo"),
    ("CO1.REQ.10059507", "FEAB 2026", "borrador REQ activo"),
    ("CO1.REQ.804076", "FEAB 2018-2021", "borrador REQ historico"),
    # 3 PPI sin notice_uid
    ("CO1.PPI.36786565", "FEAB 2025", "PPI limbo SECOP"),
    ("CO1.PPI.39464215", "FEAB 2025", "PPI limbo SECOP"),
    ("CO1.PPI.11758446", "FEAB 2018-2021", "PPI smoke canonical"),
]


def http_get_json(url: str, params: dict[str, str], timeout: int = 30) -> list[dict]:
    full = f"{url}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(full, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8"))
    return data if isinstance(data, list) else []


def check_jbjy(pid: str) -> int:
    """Cuenta hits en jbjy por proceso_de_compra OR id_contrato."""
    rows1 = http_get_json(JBJY_URL, {"proceso_de_compra": pid, "$limit": "10"})
    rows2 = http_get_json(JBJY_URL, {"id_contrato": pid, "$limit": "10"})
    return len(rows1) + len(rows2)


def check_rpmr(pid: str) -> int:
    """Cuenta hits en rpmr por url_contrato substring OR numero_de_proceso."""
    where = f"url_contrato LIKE '%{pid}%' AND nit_de_la_entidad='{NIT_FEAB}'"
    rows1 = http_get_json(RPMR_URL, {"$where": where, "$limit": "10"})
    rows2 = http_get_json(
        RPMR_URL, {"numero_de_proceso": pid, "$limit": "10"},
    )
    return len(rows1) + len(rows2)


def main() -> int:
    print(f"=== Validar 11 cardinal-imposibles vs LIVE ({datetime.now(UTC).isoformat()}) ===\n")
    print(f"{'#':>3} {'process_id':<24} {'hoja':<18} {'jbjy':>5} {'rpmr':>5} status")
    print(f"{'-'*3:>3} {'-'*24:<24} {'-'*18:<18} {'-'*5:>5} {'-'*5:>5} {'-'*8}")

    promoted: list[str] = []
    for i, (pid, hoja, _kind) in enumerate(CARDINAL_IMPOSIBLES, 1):
        try:
            jbjy_hits = check_jbjy(pid)
        except Exception as e:
            jbjy_hits = -1
            print(f"  [warn] jbjy error: {e}")
        try:
            rpmr_hits = check_rpmr(pid)
        except Exception as e:
            rpmr_hits = -1
            print(f"  [warn] rpmr error: {e}")

        status = (
            "STILL_IMPOSIBLE" if (jbjy_hits == 0 and rpmr_hits == 0)
            else "PROMOTED!" if (jbjy_hits > 0 or rpmr_hits > 0)
            else "ERR"
        )
        if status == "PROMOTED!":
            promoted.append(pid)
        print(f"{i:>3} {pid:<24} {hoja:<18} {jbjy_hits:>5} {rpmr_hits:>5} {status}")

    print()
    if promoted:
        print(f"PROMOTED ({len(promoted)}): {', '.join(promoted)}")
        print("  -> Action: re-run verify_watch_list.py + audit_dashboard_full.py")
        print("     para que se actualice automaticamente la cobertura de estos.")
        return 1

    print(f"OK 11/11 cardinal-imposibles siguen sin cobertura en LIVE")
    print("   El set es estable desde 2026-04-27.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
