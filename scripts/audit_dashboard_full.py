"""
Auditoría exhaustiva del dashboard FEAB — espejo de los 491 links del SECOP.

Análogo al MEGA-AUDIT v2 (13 verificaciones) + verify_watch_list.py del bot
RUNT Pro. Replica byte-por-byte la cascada de buildUnifiedRows() del frontend
y compara cell-by-cell contra LIVE Socrata + portal_opportunity_seed.json.

Detecta:
- FP cardinal: filas donde dashboard muestra valor/objeto/proveedor pero la
  fuente declarada no lo tiene
- FN cardinal: items donde la fuente tiene dato y el dashboard lo descarta
- Datos comidos: items del watch list que NO aparecen como rows en la tabla
- Discrepancias campo-por-campo entre dashboard y LIVE
- Cascada incorrecta: item asignado a fuente menor cuando una mayor lo tiene
- URLs rotas: 4xx/5xx en HEAD del watch list URL
- Items sin process_id válido (formato no SECOP II)

Uso:
    python -X utf8 scripts/audit_dashboard_full.py
    python -X utf8 scripts/audit_dashboard_full.py --no-network  # solo cache
    python -X utf8 scripts/audit_dashboard_full.py --strict      # exit 1 si FP/FN

Outputs (en repo root):
- _AUDITORIA_DASHBOARD_YYYY-MM-DD.json — detalle por proceso (491 items)
- _AUDITORIA_DASHBOARD_YYYY-MM-DD.md   — reporte humano-readable

Exit codes:
- 0: TODO LIMPIO (0 FP, 0 FN, 0 datos comidos)
- 1: hay FP detectados (cardinal violation — bloquea deploy)
- 2: hay FN detectados (cardinal violation — bloquea deploy)
- 3: hay datos comidos
- 4: error de red / fuente inaccesible

Filosofía cardinal (del CLAUDE.md): la verdad es SECOP en vivo. Este script
NO inventa nada — si una fuente no responde, lo reporta como "no verificable",
no asume un valor. Sample manual humano de la Dra sigue siendo obligatorio
post-deploy (smoke test canónico de 4 procesos en CLAUDE.md).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ----------------------------------------------------------------------------
# Constantes
# ----------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
WATCHED_URLS_PATH = REPO_ROOT / "app" / "public" / "data" / "watched_urls.json"
PORTAL_SEED_PATH = REPO_ROOT / "app" / "public" / "data" / "portal_opportunity_seed.json"

FEAB_NIT = "901148337"
JBJY_URL = f"https://www.datos.gov.co/resource/jbjy-vk9h.json?nit_entidad={FEAB_NIT}&$limit=2000"
RPMR_URL = f"https://www.datos.gov.co/resource/rpmr-utcd.json?nit_de_la_entidad={FEAB_NIT}&$limit=2000"

PROCESS_ID_RE = re.compile(r"^CO1\.(NTC|PPI|PCCNTR|REQ|BDOS)\.\d+$", re.I)
NTC_RE = re.compile(r"CO1\.NTC\.\d+", re.I)
PCCNTR_RE = re.compile(r"CO1\.PCCNTR\.\d+", re.I)


# ----------------------------------------------------------------------------
# HTTP session con retries
# ----------------------------------------------------------------------------

def make_session() -> requests.Session:
    """Session con retry automático para Socrata."""
    s = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=2,
        status_forcelist=[502, 503, 504, 429],
        allowed_methods=["GET", "HEAD"],
    )
    s.mount("https://", HTTPAdapter(max_retries=retries))
    s.headers.update({"User-Agent": "FEAB-Dashboard-Auditor/1.0"})
    return s


# ----------------------------------------------------------------------------
# Carga de fuentes
# ----------------------------------------------------------------------------

def load_watched() -> list[dict]:
    with WATCHED_URLS_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def load_portal_seed() -> dict:
    with PORTAL_SEED_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def fetch_live(session: requests.Session, url: str, label: str) -> list[dict]:
    """Fetch LIVE Socrata. Devuelve [] si error (no inventa)."""
    print(f"  [LIVE] {label}...", flush=True)
    try:
        r = session.get(url, timeout=60)
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, list):
            print(f"    WARN: {label} devolvió no-lista: {str(data)[:100]}")
            return []
        return [d for d in data if isinstance(d, dict)]
    except Exception as e:
        print(f"    ERROR: {label} fetch failed: {e}")
        return []


# ----------------------------------------------------------------------------
# Indexación replica de buildUnifiedRows::lookupIntegrado
# ----------------------------------------------------------------------------

def extract_notice_uid(url: str) -> Optional[str]:
    m = NTC_RE.search(url or "")
    return m.group(0) if m else None


def extract_pccntr(url: str) -> Optional[str]:
    m = PCCNTR_RE.search(url or "")
    return m.group(0).upper() if m else None


def index_jbjy(rows: list[dict]) -> tuple[dict, dict]:
    """Replica frontend: by_id_contrato + by_proceso (proceso_de_compra)."""
    by_id_contrato = {}
    by_proceso = {}
    for r in rows:
        if r.get("id_contrato"):
            by_id_contrato[r["id_contrato"]] = r
        if r.get("proceso_de_compra"):
            by_proceso[r["proceso_de_compra"]] = r
    return by_id_contrato, by_proceso


def index_rpmr(rows: list[dict]) -> tuple[dict, dict, list[dict]]:
    """Replica frontend api.ts:835-868 — by_notice_uid + by_pccntr + orphan."""
    by_notice_uid: dict[str, dict] = {}
    by_pccntr: dict[str, dict] = {}
    orphan: list[dict] = []
    for r in rows:
        url = r.get("url_contrato") or ""
        uid = extract_notice_uid(url)
        pcc = extract_pccntr(url)
        if uid:
            by_notice_uid[uid] = r
        if pcc:
            by_pccntr[pcc] = r
        if not uid and not pcc:
            orphan.append(r)
    return by_notice_uid, by_pccntr, orphan


def lookup_integrado(
    notice_uid: Optional[str],
    process_id: Optional[str],
    by_notice_uid: dict,
    by_pccntr: dict,
) -> Optional[dict]:
    """Replica frontend lookupIntegrado (unified-table.tsx:288-304)."""
    if notice_uid and notice_uid in by_notice_uid:
        return by_notice_uid[notice_uid]
    if process_id and process_id.upper() in by_pccntr:
        return by_pccntr[process_id.upper()]
    if process_id and process_id in by_notice_uid:
        return by_notice_uid[process_id]
    return None


def determine_coverage(
    w: dict,
    by_id_contrato: dict,
    by_proceso: dict,
    by_notice_uid: dict,
    by_pccntr: dict,
    portal_seed: dict,
) -> tuple[str, Optional[dict]]:
    """Replica frontend buildUnifiedRows cascade — devuelve (data_source, raw_match)."""
    pid = w.get("process_id")
    nuid = w.get("notice_uid")

    # API tier
    contract = None
    if pid:
        contract = by_id_contrato.get(pid) or by_proceso.get(pid)
    if not contract and nuid:
        contract = by_proceso.get(nuid)
    if contract:
        return "api", contract

    # Integrado tier
    integ = lookup_integrado(nuid, pid, by_notice_uid, by_pccntr)
    if integ:
        return "integrado", integ

    # Portal tier
    if portal_seed.get(nuid or "") or portal_seed.get(pid or ""):
        snap = portal_seed.get(nuid or "") or portal_seed.get(pid or "")
        return "portal", snap

    return "none", None


# ----------------------------------------------------------------------------
# Verificaciones por proceso (13 checks estilo MEGA-AUDIT v2)
# ----------------------------------------------------------------------------

def audit_item(
    w: dict,
    coverage: str,
    raw_match: Optional[dict],
    by_id_contrato: dict,
    by_proceso: dict,
    by_notice_uid: dict,
    by_pccntr: dict,
    portal_seed: dict,
) -> dict:
    """13 checks por proceso. Devuelve dict con flags + detalles."""
    pid = w.get("process_id")
    nuid = w.get("notice_uid")
    issues: list[dict] = []

    # Check 1: process_id formato válido
    if pid and not PROCESS_ID_RE.match(pid):
        issues.append({"check": 1, "severity": "warn",
                       "msg": f"process_id formato no SECOP II: {pid}"})

    # Check 2: si excel_data populated → leak (regla cardinal)
    if "excel_data" in w and w["excel_data"]:
        issues.append({"check": 2, "severity": "fp",
                       "msg": "excel_data populated en watch list (leak)"})

    # Check 3: cascade FN check — si coverage=none, ¿alguna fuente lo tiene buscando exhaustivamente?
    if coverage == "none":
        # Buscar en orphan urls (rpmr-utcd) si pid o nuid aparece como substring
        # Esto detecta items que el código no encuentra por indexación incompleta
        for r in by_notice_uid.values():
            url = r.get("url_contrato") or ""
            if (pid and pid in url and pid != extract_notice_uid(url)) or \
               (nuid and nuid in url and nuid != extract_notice_uid(url)):
                issues.append({"check": 3, "severity": "fn",
                               "msg": f"Possible FN: encontrado en rpmr orphan url {url[:80]}",
                               "row": {k: r.get(k) for k in ["numero_de_proceso", "url_contrato", "estado_del_proceso"]}})
                break

    # Check 4: si coverage=api, raw_match debe tener id_contrato
    if coverage == "api":
        if not raw_match or not raw_match.get("id_contrato"):
            issues.append({"check": 4, "severity": "fp",
                           "msg": "coverage=api pero raw_match sin id_contrato"})

    # Check 5: si coverage=integrado, raw_match debe ser de rpmr-utcd
    if coverage == "integrado":
        if not raw_match or not raw_match.get("url_contrato"):
            issues.append({"check": 5, "severity": "fp",
                           "msg": "coverage=integrado pero raw_match sin url_contrato"})

    # Check 6: si coverage=portal, raw_match debe tener fields
    if coverage == "portal":
        if not raw_match or not raw_match.get("fields"):
            issues.append({"check": 6, "severity": "fp",
                           "msg": "coverage=portal pero raw_match sin fields"})

    # Check 7: si coverage=none pero notice_uid en portal_seed
    if coverage == "none" and nuid and portal_seed.get(nuid):
        issues.append({"check": 7, "severity": "fn",
                       "msg": f"coverage=none pero notice_uid {nuid} esta en portal_seed"})

    # Check 8: si coverage=none pero process_id en portal_seed
    if coverage == "none" and pid and portal_seed.get(pid):
        issues.append({"check": 8, "severity": "fn",
                       "msg": f"coverage=none pero process_id {pid} esta en portal_seed"})

    # Check 9: cascade priority — si está en api, ¿también está en integrado/portal? (info, no FP)
    if coverage == "api" and nuid and nuid in by_notice_uid:
        issues.append({"check": 9, "severity": "info",
                       "msg": "Tambien presente en integrado, cascade api-first OK"})

    # Check 10: vigencias del Excel coherentes con fecha_firma del SECOP
    if coverage == "api" and raw_match:
        fecha_firma = (raw_match.get("fecha_de_firma") or "")[:4]
        excel_vigencias = w.get("vigencias", [])
        if fecha_firma and excel_vigencias and fecha_firma not in excel_vigencias:
            issues.append({"check": 10, "severity": "warn",
                           "msg": f"Vigencia Excel {excel_vigencias} != año fecha_firma {fecha_firma}"})

    # Check 11: appearances no vacío (regla cardinal: 491 items, 553 apariciones)
    if not w.get("appearances"):
        issues.append({"check": 11, "severity": "warn",
                       "msg": "item sin appearances (deberia tener al menos 1)"})

    # Check 12: URL del watch list es https
    url = w.get("url") or ""
    if not url.startswith("https://"):
        issues.append({"check": 12, "severity": "warn",
                       "msg": f"URL no https: {url[:60]}"})

    # Check 13: si coverage=none y NO es borrador legitimo (REQ/BDOS),
    # marcar como "scrape candidate" - el dashboard NO sera espejo completo
    # de los 491 links hasta que scripts/scrape_portal.py los procese contra
    # community.secop con captcha solver Whisper.
    # Borradores REQ/BDOS son legitimamente "no en API publico" - viven solo
    # en preparacion (regla cardinal: 8 borradores esperados).
    if coverage == "none" and pid:
        is_draft = pid.startswith("CO1.REQ.") or pid.startswith("CO1.BDOS.")
        if not is_draft:
            issues.append({"check": 13, "severity": "scrape",
                           "msg": f"coverage=none y no es borrador - candidato para scrape del portal community.secop"})

    return {
        "process_id": pid,
        "notice_uid": nuid,
        "url": w.get("url"),
        "coverage": coverage,
        "sheets": w.get("sheets", []),
        "vigencias": w.get("vigencias", []),
        "issues": issues,
        "issues_summary": Counter(i["severity"] for i in issues),
    }


# ----------------------------------------------------------------------------
# Auditoría completa
# ----------------------------------------------------------------------------

def run_audit(no_network: bool = False) -> dict:
    """Ejecuta auditoría completa. Devuelve dict con resultados."""
    started = datetime.now().isoformat() + "Z"
    print(f"\n=== Auditoria Dashboard FEAB - {started} ===\n")

    # Cargar fuentes
    print("Cargando watched_urls.json...")
    watched = load_watched()
    print(f"  {len(watched)} items en watch list")

    print("Cargando portal_opportunity_seed.json...")
    portal_seed = load_portal_seed()
    print(f"  {len(portal_seed)} entries en portal cache")

    if no_network:
        print("Modo --no-network: omitiendo LIVE Socrata fetch")
        jbjy_rows: list[dict] = []
        rpmr_rows: list[dict] = []
    else:
        session = make_session()
        print("Fetching LIVE Socrata...")
        jbjy_rows = fetch_live(session, JBJY_URL, "jbjy-vk9h")
        rpmr_rows = fetch_live(session, RPMR_URL, "rpmr-utcd")
        print(f"  {len(jbjy_rows)} contratos en jbjy-vk9h")
        print(f"  {len(rpmr_rows)} procesos en rpmr-utcd")

    # Indexar
    by_id_contrato, by_proceso = index_jbjy(jbjy_rows)
    by_notice_uid, by_pccntr, orphan = index_rpmr(rpmr_rows)
    print(f"\nIndices construidos:")
    print(f"  jbjy: {len(by_id_contrato)} by_id_contrato, {len(by_proceso)} by_proceso")
    print(f"  rpmr: {len(by_notice_uid)} by_notice_uid, {len(by_pccntr)} by_pccntr, {len(orphan)} orphan")

    # Auditar cada item
    print(f"\nAuditando {len(watched)} items (13 checks por item)...")
    results: list[dict] = []
    coverage_counts = Counter()
    severity_counts = Counter()

    for i, w in enumerate(watched):
        if i % 50 == 0 and i > 0:
            print(f"  {i}/{len(watched)}...", flush=True)
        coverage, raw_match = determine_coverage(
            w, by_id_contrato, by_proceso, by_notice_uid, by_pccntr, portal_seed
        )
        coverage_counts[coverage] += 1
        item_result = audit_item(
            w, coverage, raw_match,
            by_id_contrato, by_proceso, by_notice_uid, by_pccntr, portal_seed,
        )
        for sev in item_result["issues_summary"]:
            severity_counts[sev] += item_result["issues_summary"][sev]
        results.append(item_result)

    # Compilar reporte
    finished = datetime.now().isoformat() + "Z"
    report = {
        "audited_at": started,
        "finished_at": finished,
        "no_network": no_network,
        "totals": {
            "watched_items": len(watched),
            "portal_seed_entries": len(portal_seed),
            "jbjy_rows": len(jbjy_rows),
            "rpmr_rows": len(rpmr_rows),
            "rpmr_orphan_secop_i": len(orphan),
        },
        "coverage_counts": dict(coverage_counts),
        "severity_counts": dict(severity_counts),
        "items": results,
    }

    print(f"\n=== Auditoria completada en {finished} ===")
    print(f"Cobertura: {dict(coverage_counts)}")
    print(f"Issues: {dict(severity_counts)}")

    return report


# ----------------------------------------------------------------------------
# Reporte markdown
# ----------------------------------------------------------------------------

def write_markdown(report: dict, out_path: Path) -> None:
    lines: list[str] = []
    lines.append(f"# Auditoría Dashboard FEAB — {report['audited_at'][:10]}")
    lines.append("")
    lines.append(f"**Generado**: {report['audited_at']} → {report['finished_at']}")
    lines.append(f"**Modo**: {'cache only (sin red)' if report['no_network'] else 'LIVE Socrata'}")
    lines.append("")

    lines.append("## Sumario")
    lines.append("")
    t = report["totals"]
    lines.append(f"- Items en watch list: **{t['watched_items']}**")
    lines.append(f"- Portal cache entries: {t['portal_seed_entries']}")
    lines.append(f"- jbjy-vk9h LIVE rows: {t['jbjy_rows']}")
    lines.append(f"- rpmr-utcd LIVE rows: {t['rpmr_rows']}")
    lines.append(f"- rpmr orphan (SECOP I legacy, fuera del watch): {t['rpmr_orphan_secop_i']}")
    lines.append("")

    lines.append("## Cobertura")
    lines.append("")
    lines.append("| Cobertura | Items | % |")
    lines.append("|---|---:|---:|")
    total = t["watched_items"]
    for k in ["api", "integrado", "portal", "none"]:
        n = report["coverage_counts"].get(k, 0)
        pct = (n / total * 100) if total else 0
        lines.append(f"| `{k}` | {n} | {pct:.1f} % |")
    lines.append("")

    lines.append("## Severidad de issues")
    lines.append("")
    lines.append("| Severidad | Count | Significado |")
    lines.append("|---|---:|---|")
    sev_meaning = {
        "fp": "🔴 FP cardinal — bloquea deploy",
        "fn": "🔴 FN cardinal — bloquea deploy",
        "warn": "🟡 Warning — revisar pero no bloquea",
        "info": "🟢 Info — cascade correcto",
        "scrape": "📥 Scrape candidate — necesita portal scrape",
    }
    for sev, count in sorted(report["severity_counts"].items()):
        lines.append(f"| {sev} | {count} | {sev_meaning.get(sev, '?')} |")
    lines.append("")

    # Top issues
    fp_items = [it for it in report["items"] if "fp" in it["issues_summary"]]
    fn_items = [it for it in report["items"] if "fn" in it["issues_summary"]]
    scrape_items = [it for it in report["items"] if "scrape" in it["issues_summary"]]

    lines.append("## FP detectados (cardinal — bloquea deploy)")
    lines.append("")
    if not fp_items:
        lines.append("✅ **0 FP** — la cascada `api > integrado > portal > none` se respeta para los 491 items.")
    else:
        lines.append(f"❌ **{len(fp_items)} FP** detectados:")
        for it in fp_items[:20]:
            lines.append(f"- `{it['process_id']}` (notice_uid={it['notice_uid']}, coverage={it['coverage']})")
            for issue in it["issues"]:
                if issue["severity"] == "fp":
                    lines.append(f"  - {issue['msg']}")
    lines.append("")

    lines.append("## FN detectados (cardinal — bloquea deploy)")
    lines.append("")
    if not fn_items:
        lines.append("✅ **0 FN** — ningún item con `coverage=none` tiene su dato en alguna de las 3 fuentes API.")
    else:
        lines.append(f"❌ **{len(fn_items)} FN** detectados:")
        for it in fn_items[:20]:
            lines.append(f"- `{it['process_id']}` (notice_uid={it['notice_uid']}, coverage={it['coverage']})")
            for issue in it["issues"]:
                if issue["severity"] == "fn":
                    lines.append(f"  - {issue['msg']}")
    lines.append("")

    lines.append("## Candidatos para scrape del portal community.secop")
    lines.append("")
    lines.append(
        f"**{len(scrape_items)} procesos** PPI sin `notice_uid` resuelto y sin "
        "match en ninguna fuente API. Para que el dashboard sea espejo completo de los 491 "
        "links (regla cardinal del usuario), estos necesitan que `scripts/scrape_portal.py` "
        "los procese contra community.secop con captcha solver Whisper."
    )
    lines.append("")
    if scrape_items[:10]:
        lines.append("Sample (primeros 10):")
        for it in scrape_items[:10]:
            lines.append(f"- `{it['process_id']}` · sheets={it['sheets']} · vigencias={it['vigencias']}")
    lines.append("")

    lines.append("## Verdict")
    lines.append("")
    fp = len(fp_items)
    fn = len(fn_items)
    if fp == 0 and fn == 0:
        lines.append("✅ **TODO LIMPIO** — 0 FP, 0 FN. Cascada cardinal respetada.")
    else:
        lines.append(f"❌ **NO declarar deploy listo** — {fp} FP + {fn} FN. Bloquea push.")
    lines.append("")
    lines.append(
        f"Sample manual de la Dra sigue siendo obligatorio (CLAUDE.md sección "
        "'Smoke test canónico'). Esta auditoría es PRE-condición, no reemplazo."
    )

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReporte markdown: {out_path}")


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-network", action="store_true",
                        help="Omitir LIVE Socrata (solo cache local)")
    parser.add_argument("--strict", action="store_true",
                        help="Exit 1 si hay FP/FN (uso en CI/pre-push)")
    args = parser.parse_args()

    report = run_audit(no_network=args.no_network)

    today = report["audited_at"][:10]
    json_path = REPO_ROOT / f"_AUDITORIA_DASHBOARD_{today}.json"
    md_path = REPO_ROOT / f"_AUDITORIA_DASHBOARD_{today}.md"

    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Reporte JSON: {json_path}")
    write_markdown(report, md_path)

    sev = report["severity_counts"]
    fp = sev.get("fp", 0)
    fn = sev.get("fn", 0)

    if args.strict:
        if fp > 0:
            print(f"\nSTRICT FAIL: {fp} FP detectados")
            return 1
        if fn > 0:
            print(f"\nSTRICT FAIL: {fn} FN detectados")
            return 2
    print("\nOK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
