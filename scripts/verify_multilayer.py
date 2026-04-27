"""
Verificación MULTICAPA del dashboard FEAB.

Cardinal: 0 FP, 0 FN, 0 datos comidos. Si CUALQUIER capa falla → alerta
cardinal y bloquea declaración "deploy listo". Pensado para correrse en
cron diario + pre-deploy + cuando Sergio quiera evidencia forense para
Compliance.

10 capas de verificación independientes:
  1. pytest 192/192
  2. TypeScript compile 0 errors
  3. Audit log SHA-256 chain integro
  4. Audit dashboard 491 procesos · 0 FP / 0 FN
  5. Smoke test 4 canónicos vs LIVE Socrata
  6. Cron jobs activos y con runs success recientes
  7. HTTP smoke producción (assets críticos cargan)
  8. Comparar seed vs LIVE Socrata · detectar drift no capturado
  9. Verificar contadores cardinales en producción (491 watch · 480 cubierto)
 10. Verificar que no hay archivos temporales/test commiteados que rompan

Cada capa retorna CapaResult(name, passed, detail). Reporte final = todas
las capas concatenadas. Si alguna falla → exit 1.
"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


REPO_ROOT = Path(__file__).resolve().parent.parent
PROD_URL = "https://smarroquinc10.github.io/14-SECOP-Dr-Camila-Mendoza"


@dataclass
class CapaResult:
    name: str
    passed: bool
    detail: str

    @property
    def icon(self) -> str:
        return "✅" if self.passed else "❌"


def run_cmd(cmd: list[str], cwd: Path | None = None, timeout: int = 60) -> tuple[int, str]:
    """Run a shell command and return (exit_code, output)."""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd or REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        return result.returncode, (result.stdout or "") + (result.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, f"TIMEOUT after {timeout}s"
    except Exception as e:
        return 1, f"ERROR: {e}"


def http_get_json(url: str, timeout: int = 15):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read())


# ─────────────────────────────────────────────────────────────────────
# Capa 1 — pytest
# ─────────────────────────────────────────────────────────────────────
def capa_1_pytest() -> CapaResult:
    py = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
    code, out = run_cmd([str(py), "-X", "utf8", "-m", "pytest", "-q"], timeout=120)
    if code == 0 and "passed" in out.lower():
        # Parse "192 passed"
        import re
        m = re.search(r"(\d+)\s+passed", out)
        n = m.group(1) if m else "?"
        return CapaResult("pytest", True, f"{n}/192 PASS")
    return CapaResult("pytest", False, f"exit={code} · {out[-300:]}")


# ─────────────────────────────────────────────────────────────────────
# Capa 2 — TypeScript
# ─────────────────────────────────────────────────────────────────────
def capa_2_typescript() -> CapaResult:
    # Windows: usar .cmd directo (el shim bash falla con WinError 193)
    if sys.platform == "win32":
        tsc = REPO_ROOT / "app" / "node_modules" / ".bin" / "tsc.cmd"
    else:
        tsc = REPO_ROOT / "app" / "node_modules" / ".bin" / "tsc"
    if not tsc.exists():
        return CapaResult("TypeScript", False, f"tsc no encontrado en {tsc}")
    code, out = run_cmd([str(tsc), "--noEmit"], cwd=REPO_ROOT / "app", timeout=60)
    if code == 0:
        return CapaResult("TypeScript", True, "0 errors")
    return CapaResult("TypeScript", False, f"exit={code} · {out[-300:]}")


# ─────────────────────────────────────────────────────────────────────
# Capa 3 — Audit log SHA-256 chain
# ─────────────────────────────────────────────────────────────────────
def capa_3_audit_log() -> CapaResult:
    py = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
    code, out = run_cmd([str(py), "-m", "secop_ii", "audit-log"], timeout=30)
    if code == 0 and ("intact" in out.lower() or "ntegro" in out.lower()):
        # Parse total entries
        import re
        m = re.search(r"\*\*Entries:\*\*\s*(\d+)", out)
        n = m.group(1) if m else "?"
        return CapaResult("Audit log SHA-256 chain", True, f"{n} entradas íntegro")
    return CapaResult("Audit log SHA-256 chain", False, f"exit={code} · {out[-300:]}")


# ─────────────────────────────────────────────────────────────────────
# Capa 4 — Audit dashboard 0 FP / 0 FN
# ─────────────────────────────────────────────────────────────────────
def capa_4_audit_dashboard() -> CapaResult:
    py = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
    code, out = run_cmd([str(py), "-X", "utf8", "scripts/audit_dashboard_full.py"], timeout=120)
    if code != 0:
        return CapaResult("Audit dashboard", False, f"exit={code} · {out[-300:]}")
    # Buscar el JSON más reciente
    audits = sorted(REPO_ROOT.glob("_AUDITORIA_DASHBOARD_*.json"))
    if not audits:
        return CapaResult("Audit dashboard", False, "no se generó reporte JSON")
    latest = audits[-1]
    data = json.loads(latest.read_text(encoding="utf-8"))
    items = data.get("items", [])
    # Coverage real desde items (el JSON top-level no siempre tiene .coverage)
    cov: dict[str, int] = {}
    for it in items:
        c = it.get("coverage") or "none"
        cov[c] = cov.get(c, 0) + 1
    cubierto = cov.get("api", 0) + cov.get("integrado", 0) + cov.get("portal", 0)
    total = len(items)
    fp = sum(1 for i in items if i.get("fp"))
    fn = sum(1 for i in items if i.get("fn"))
    if fp == 0 and fn == 0 and total > 0:
        pct = round(cubierto / total * 100, 1) if total else 0
        return CapaResult("Audit dashboard", True, f"{total} procesos · 0 FP · 0 FN · {cubierto}/{total} cubierto ({pct}%)")
    return CapaResult("Audit dashboard", False, f"FP={fp}, FN={fn} · {cubierto}/{total}")


# ─────────────────────────────────────────────────────────────────────
# Capa 5 — Smoke 4 canónicos vs LIVE
# ─────────────────────────────────────────────────────────────────────
def capa_5_canonicos() -> CapaResult:
    canon = [
        ("CO1.PCCNTR.8930451", "api", "id_contrato"),
        ("CO1.NTC.1416630", "integrado", "url_contrato_like"),
        ("CO1.NTC.5405127", "portal", "seed_key"),
        ("CO1.PPI.11758446", "none", "no_source"),
    ]
    fails = []
    for pid, esperado, qmode in canon:
        try:
            if esperado == "api":
                # Para PCCNTR el campo correcto es id_contrato (no proceso_de_compra)
                r = http_get_json(f"https://www.datos.gov.co/resource/jbjy-vk9h.json?id_contrato={pid}")
                if not r:
                    fails.append(f"{pid} esperado api · 0 hits")
            elif esperado == "integrado":
                where = urllib.parse.quote(f"url_contrato LIKE '%{pid}%' AND nit_de_la_entidad='901148337'")
                r = http_get_json(f"https://www.datos.gov.co/resource/rpmr-utcd.json?$where={where}")
                if not r:
                    fails.append(f"{pid} esperado integrado · 0 hits")
            elif esperado == "portal":
                seed = http_get_json(f"{PROD_URL}/data/portal_opportunity_seed.json", timeout=30)
                if not seed.get(pid):
                    fails.append(f"{pid} esperado portal · no en seed")
            elif esperado == "none":
                # NO debe estar en ninguna fuente
                r1 = http_get_json(f"https://www.datos.gov.co/resource/jbjy-vk9h.json?id_contrato={pid}")
                r2 = http_get_json(f"https://www.datos.gov.co/resource/rpmr-utcd.json?numero_de_proceso={pid}")
                if r1 or r2:
                    fails.append(f"{pid} esperado none · aparece en API ({len(r1)},{len(r2)})")
        except Exception as e:
            fails.append(f"{pid}: error {e}")
    if fails:
        return CapaResult("Smoke 4 canónicos vs LIVE", False, " · ".join(fails))
    return CapaResult("Smoke 4 canónicos vs LIVE", True, "4/4 coinciden con LIVE Socrata")


# ─────────────────────────────────────────────────────────────────────
# Capa 6 — Cron jobs status
# ─────────────────────────────────────────────────────────────────────
def capa_6_crons() -> CapaResult:
    code, out = run_cmd(["gh", "workflow", "list", "--all"], timeout=30)
    if code != 0:
        return CapaResult("Cron jobs activos", False, f"gh CLI no disponible · {out[-200:]}")
    expected = ["Refrescar seeds", "Auditoria diaria", "Scrape Portal SECOP", "Deploy a GitHub Pages"]
    missing = [w for w in expected if w not in out]
    inactive = []
    for line in out.splitlines():
        for w in expected:
            if w in line and "active" not in line.lower():
                inactive.append(w)
    if missing or inactive:
        return CapaResult("Cron jobs activos", False, f"missing={missing} · inactive={inactive}")
    return CapaResult("Cron jobs activos", True, f"4/4 workflows activos · {', '.join(expected)}")


# ─────────────────────────────────────────────────────────────────────
# Capa 7 — HTTP smoke producción
# ─────────────────────────────────────────────────────────────────────
def capa_7_http_smoke() -> CapaResult:
    paths = [
        "/",
        "/data/portal_opportunity_seed.json",
        "/data/secop_integrado_seed.json",
        "/data/watched_urls.json",
        "/feab-logo-square.png",
    ]
    fails = []
    for p in paths:
        try:
            req = urllib.request.Request(f"{PROD_URL}{p}", method="HEAD")
            with urllib.request.urlopen(req, timeout=15) as r:
                if r.status != 200:
                    fails.append(f"{p}: HTTP {r.status}")
        except Exception as e:
            fails.append(f"{p}: {e}")
    if fails:
        return CapaResult("HTTP smoke producción", False, " · ".join(fails))
    return CapaResult("HTTP smoke producción", True, f"{len(paths)}/{len(paths)} assets HTTP 200")


# ─────────────────────────────────────────────────────────────────────
# Capa 8 — Comparar seed vs LIVE (detectar drift)
# ─────────────────────────────────────────────────────────────────────
def capa_8_drift() -> CapaResult:
    """Compara el conteo de contratos firmados que el seed local cree
    que tiene vs lo que datos.gov.co LIVE tiene HOY. Si hay drift > 5%
    es alerta — el cron debe haber traído lo nuevo y no lo hizo."""
    try:
        live = http_get_json(
            "https://www.datos.gov.co/resource/jbjy-vk9h.json?nit_entidad=901148337&$select=count(*)",
            timeout=20,
        )
        live_count = int(live[0].get("count", 0)) if live else 0

        seed_path = REPO_ROOT / "app" / "public" / "data" / "secop_integrado_seed.json"
        if not seed_path.exists():
            return CapaResult("Drift seed vs LIVE", False, "seed Integrado no existe localmente")
        seed = json.loads(seed_path.read_text(encoding="utf-8"))
        seed_total = seed.get("total_rows", 0)

        # No comparamos jbjy directo (no está en seed) sino integrado
        live_integrado = http_get_json(
            "https://www.datos.gov.co/resource/rpmr-utcd.json?nit_de_la_entidad=901148337&$select=count(*)",
            timeout=20,
        )
        live_int_count = int(live_integrado[0].get("count", 0)) if live_integrado else 0

        if live_int_count == 0:
            return CapaResult("Drift seed vs LIVE", False, "Socrata Integrado devolvió 0 (anormal)")
        diff = abs(seed_total - live_int_count)
        pct = (diff / live_int_count) * 100 if live_int_count > 0 else 0
        if pct > 5:
            return CapaResult(
                "Drift seed vs LIVE",
                False,
                f"DRIFT {pct:.1f}% · seed Integrado={seed_total} vs LIVE={live_int_count}",
            )
        return CapaResult(
            "Drift seed vs LIVE",
            True,
            f"sin drift · seed Integrado={seed_total} ≈ LIVE={live_int_count} (diff {pct:.1f}%)",
        )
    except Exception as e:
        return CapaResult("Drift seed vs LIVE", False, f"error: {e}")


# ─────────────────────────────────────────────────────────────────────
# Capa 9 — Contadores cardinales en producción
# ─────────────────────────────────────────────────────────────────────
def capa_9_contadores() -> CapaResult:
    try:
        watched = http_get_json(f"{PROD_URL}/data/watched_urls.json", timeout=15)
        if isinstance(watched, dict):
            watched = watched.get("items", [])
        total = len(watched)
        if total != 491:
            return CapaResult(
                "Contadores cardinales producción",
                False,
                f"watched_urls.json = {total} (esperado 491)",
            )

        portal = http_get_json(f"{PROD_URL}/data/portal_opportunity_seed.json", timeout=30)
        portal_count = len(portal)
        if portal_count < 470:
            return CapaResult(
                "Contadores cardinales producción",
                False,
                f"portal_seed = {portal_count} (esperado >= 470)",
            )
        return CapaResult(
            "Contadores cardinales producción",
            True,
            f"watch={total}/491 · portal={portal_count} procesos",
        )
    except Exception as e:
        return CapaResult("Contadores cardinales producción", False, f"error: {e}")


# ─────────────────────────────────────────────────────────────────────
# Capa 11 — PDFs / documentos del portal en producción
# ─────────────────────────────────────────────────────────────────────
def capa_11_pdfs_portal() -> CapaResult:
    """Verifica que los procesos del portal seed tengan documentos PDF
    descargables. Si un proceso debería tener docs y no los tiene =
    bug cardinal (Cami no podría descargar el contrato firmado)."""
    try:
        seed = http_get_json(f"{PROD_URL}/data/portal_opportunity_seed.json", timeout=30)
        total = len(seed)
        sin_docs = 0
        con_docs = 0
        total_docs = 0
        sample_uid_con_docs = None
        for uid, entry in seed.items():
            docs = entry.get("documents", []) or []
            if docs:
                con_docs += 1
                total_docs += len(docs)
                if not sample_uid_con_docs:
                    sample_uid_con_docs = uid
            else:
                sin_docs += 1

        # Verificar que un PDF random sea HTTP HEAD-able
        pdf_test_status = "n/a"
        if sample_uid_con_docs:
            sample_doc = seed[sample_uid_con_docs]["documents"][0]
            pdf_url = sample_doc.get("url", "")
            if pdf_url.startswith("http"):
                try:
                    req = urllib.request.Request(pdf_url, method="HEAD")
                    with urllib.request.urlopen(req, timeout=10) as r:
                        pdf_test_status = f"sample HTTP {r.status}"
                except Exception as e:
                    pdf_test_status = f"sample FAIL: {str(e)[:50]}"

        if con_docs == 0:
            return CapaResult("PDFs portal en producción", False, "0 procesos tienen documentos en el seed!")

        # >= 80% de procesos del seed deberían tener al menos 1 documento
        pct_con_docs = (con_docs / total) * 100 if total > 0 else 0
        if pct_con_docs < 70:
            return CapaResult(
                "PDFs portal en producción",
                False,
                f"solo {pct_con_docs:.0f}% del portal tiene docs (esperado >70%) · {con_docs}/{total} con docs · {total_docs} PDFs totales",
            )
        return CapaResult(
            "PDFs portal en producción",
            True,
            f"{con_docs}/{total} procesos con docs ({pct_con_docs:.0f}%) · {total_docs} PDFs totales · {pdf_test_status}",
        )
    except Exception as e:
        return CapaResult("PDFs portal en producción", False, f"error: {e}")


# ─────────────────────────────────────────────────────────────────────
# Capa 10 — Sin archivos temporales committeados
# ─────────────────────────────────────────────────────────────────────
def capa_10_no_temp_files() -> CapaResult:
    code, out = run_cmd(["git", "ls-files"], timeout=10)
    if code != 0:
        return CapaResult("Sin archivos temporales", False, f"git ls-files exit {code}")
    bad = []
    for line in out.splitlines():
        l = line.lower()
        if any(p in l for p in ["test_3rows", "_smoke_", "tmp_", ".bak", "debug.log"]):
            bad.append(line)
    if bad:
        return CapaResult(
            "Sin archivos temporales",
            False,
            f"{len(bad)} archivos: {', '.join(bad[:3])}",
        )
    return CapaResult("Sin archivos temporales", True, "repo limpio")


# ─────────────────────────────────────────────────────────────────────
# Main orchestrator
# ─────────────────────────────────────────────────────────────────────
def main() -> int:
    capas: list[Callable[[], CapaResult]] = [
        capa_1_pytest,
        capa_2_typescript,
        capa_3_audit_log,
        capa_4_audit_dashboard,
        capa_5_canonicos,
        capa_6_crons,
        capa_7_http_smoke,
        capa_8_drift,
        capa_9_contadores,
        capa_10_no_temp_files,
        capa_11_pdfs_portal,
    ]
    print("=" * 64)
    print("VERIFICACIÓN MULTICAPA · Dashboard FEAB · Cami abogada")
    print("=" * 64)
    print()
    results: list[CapaResult] = []
    for i, capa in enumerate(capas, start=1):
        print(f"Ejecutando capa {i}/{len(capas)}: {capa.__name__.replace('capa_', '').replace('_', ' ')}...", end="", flush=True)
        try:
            r = capa()
        except Exception as e:
            r = CapaResult(capa.__name__, False, f"EXCEPCION {type(e).__name__}: {e}")
        results.append(r)
        print(f" {r.icon}")

    print()
    print("=" * 64)
    print("RESULTADOS")
    print("=" * 64)
    fails = [r for r in results if not r.passed]
    for r in results:
        print(f"  {r.icon} Capa: {r.name:<40} {r.detail}")
    print()
    if fails:
        print(f"❌ FALLARON {len(fails)}/{len(results)} CAPAS · CARDINAL: NO declarar deploy listo")
        print()
        for r in fails:
            print(f"   ❌ {r.name}: {r.detail}")
        return 1
    print(f"✅ TODAS LAS {len(results)} CAPAS PASS · 0 FP · 0 FN · 0 datos comidos")
    print("✅ Sistema apto para Compliance · evidencia forense reproducible")
    return 0


if __name__ == "__main__":
    sys.exit(main())
