"""TAREA 4 · Genera app/public/data/modificatorios_classified.json desde el cache.

Toma el output del pipeline OCR (.cache/modificatorios_pdfs/ocr_classified.json
+ .cache/modificatorios_pdfs/index.json) y produce un JSON consumible por
el frontend con:

  - Shape por proceso · una entrada por process_id con resumen + lista de docs.
  - Sumas cardinales: valor_adicionado_total_cop, dias_prorrogados_total.
  - Solo los docs con clasificacion cardinal (excluye Aclaratorio, Legalizacion,
    docs que son solo soporte) cuentan para totales.
  - URL original del PDF en community.secop · NO path local (no se sube cache).
  - Warnings preservados para honestidad cardinal en UI.
  - Metadata: code_version (git SHA), generated_at, stats globales.

Uso:
    python scripts/generate_modificatorios_classified.py

Output:
    app/public/data/modificatorios_classified.json
"""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE_ROOT = ROOT / ".cache" / "modificatorios_pdfs"
INDEX_PATH = CACHE_ROOT / "index.json"
OCR_RESULTS_PATH = CACHE_ROOT / "ocr_classified.json"
OUT_PATH = ROOT / "app" / "public" / "data" / "modificatorios_classified.json"

log = logging.getLogger("gen-mods")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

# Tipos cardinales que cuentan como "acto contractual modificatorio" para
# las sumas. Aclaratorio y Legalizacion son SOPORTE · no cuentan.
TIPOS_CARDINALES = {
    "Modificatorio", "Adicion", "Prorroga", "Otrosi", "Adenda",
    "Cesion", "Suspension", "Reanudacion", "Terminacion anticipada",
    "Liquidacion", "Novacion",
}

# Tipos que son "soporte" · se preservan en el listado pero no suman al total
TIPOS_SOPORTE = {"Aclaratorio", "Legalizacion (soporte)"}


def _git_short_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def main() -> int:
    if not OCR_RESULTS_PATH.exists():
        log.error("no hay ocr_classified.json · correr OCR primero")
        return 1
    if not INDEX_PATH.exists():
        log.error("no hay index.json · correr download primero")
        return 1

    ocr_results = json.loads(OCR_RESULTS_PATH.read_text(encoding="utf-8"))
    index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))

    # Mapear url original por (uid, doc_idx) desde el index
    url_map: dict[tuple[str, int], dict] = {}
    for uid, p in index.get("processes", {}).items():
        for d in p.get("docs", []):
            url_map[(uid, d.get("doc_idx"))] = d

    output_processes: dict[str, dict] = {}
    totals_global = {
        "procesos_con_modificatorios": 0,
        "total_actos_cardinales": 0,
        "total_modificatorios_genericos": 0,
        "total_adiciones": 0,
        "total_prorrogas": 0,
        "total_cesiones": 0,
        "total_liquidaciones": 0,
        "total_otros": 0,
        "valor_adicionado_global_cop": 0,
        "dias_prorrogados_global": 0,
        "docs_needs_review": 0,
        "docs_con_warnings": 0,
    }

    for uid, p_data in ocr_results.get("processes", {}).items():
        docs_out: list[dict] = []
        valor_total_proc = 0
        dias_total_proc = 0

        for doc in p_data.get("docs", []):
            tipo = doc.get("tipo")
            subtipos = doc.get("subtipos", []) or []
            valor_adic = doc.get("valor_adicionado_cop")
            dias_prorr = doc.get("dias_prorrogados")
            fecha = doc.get("fecha_documento")
            warnings_doc = doc.get("extraction_warnings", []) or []

            # Lookup URL original
            idx = doc.get("doc_idx")
            url_meta = url_map.get((uid, idx), {})
            pdf_url = url_meta.get("original_url", "")
            pdf_name = url_meta.get("original_name", "")

            is_cardinal = tipo in TIPOS_CARDINALES
            is_soporte = tipo in TIPOS_SOPORTE

            doc_out = {
                "doc_idx": idx,
                "tipo": tipo,
                "subtipos": subtipos,
                "numero": doc.get("numero"),
                "valor_adicionado_cop": valor_adic,
                "dias_prorrogados": dias_prorr,
                "fecha_documento": fecha,
                "pdf_url": pdf_url,
                "pdf_name": pdf_name,
                "is_cardinal": is_cardinal,
                "is_soporte": is_soporte,
                "needs_human_review": doc.get("needs_human_review", False),
                "warnings": warnings_doc,
                "confidence": doc.get("confidence"),
            }
            docs_out.append(doc_out)

            # Contadores
            if is_cardinal:
                totals_global["total_actos_cardinales"] += 1
                if tipo == "Modificatorio":
                    totals_global["total_modificatorios_genericos"] += 1
                elif tipo == "Adicion":
                    totals_global["total_adiciones"] += 1
                elif tipo == "Prorroga":
                    totals_global["total_prorrogas"] += 1
                elif tipo == "Cesion":
                    totals_global["total_cesiones"] += 1
                elif tipo == "Liquidacion":
                    totals_global["total_liquidaciones"] += 1
                else:
                    totals_global["total_otros"] += 1

                # Acumular valor / dias del proceso (solo cardinal)
                if valor_adic:
                    valor_total_proc += valor_adic
                    totals_global["valor_adicionado_global_cop"] += valor_adic
                if dias_prorr:
                    dias_total_proc += dias_prorr
                    totals_global["dias_prorrogados_global"] += dias_prorr

            if doc.get("needs_human_review"):
                totals_global["docs_needs_review"] += 1
            if warnings_doc:
                totals_global["docs_con_warnings"] += 1

        # Solo persistir procesos con al menos UN doc cardinal o soporte
        if any(d["is_cardinal"] or d["is_soporte"] for d in docs_out):
            modif_count = sum(1 for d in docs_out if d["is_cardinal"])
            output_processes[uid] = {
                "process_id": uid,
                "modificatorios_count": modif_count,
                "valor_adicionado_total_cop": valor_total_proc or None,
                "dias_prorrogados_total": dias_total_proc or None,
                "docs": docs_out,
            }
            if modif_count > 0:
                totals_global["procesos_con_modificatorios"] += 1

    output = {
        "version": 3,
        "schema": "modificatorios_classified.v3",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "code_version": _git_short_sha(),
        "stats": totals_global,
        "by_process": output_processes,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    log.info("=" * 60)
    log.info("Output: %s", OUT_PATH.relative_to(ROOT))
    log.info("Stats globales:")
    for k, v in totals_global.items():
        if "valor" in k:
            log.info("  %-40s $ %s", k, format(v, ","))
        else:
            log.info("  %-40s %s", k, v)
    log.info("Procesos con docs persistidos: %d", len(output_processes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
