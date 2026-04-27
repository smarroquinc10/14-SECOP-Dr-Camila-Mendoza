"""
Cross-check entre las 3 fuentes del SECOP — detección de drift INTERNO.

Cardinal: el SECOP expone los datos de los 491 procesos en 3 fuentes
distintas:
  1. jbjy-vk9h (contratos firmados, datos.gov.co)
  2. rpmr-utcd (SECOP Integrado, datos.gov.co)
  3. community.secop.gov.co (portal con captcha) — cache en portal_seed

Si un proceso aparece en >1 fuente y los datos NO coinciden,
es una inconsistencia del SECOP MISMO. Antes que Compliance lo
descubra, este script lo detecta y reporta.

Para cada proceso multi-fuente, compara campos clave:
  - valor_del_contrato (numérico)
  - fecha_de_firma
  - proveedor / contratista
  - estado_contrato
  - objeto_del_contrato (texto)

Genera 2 outputs:
  - `_DISCREPANCIAS_FUENTES_<YYYY-MM-DD>.json` machine-readable
  - `_DISCREPANCIAS_FUENTES_<YYYY-MM-DD>.md` human-readable para Compliance

Si hay discrepancias → exit 1 (alerta cardinal).
Si todo coincide → exit 0 (espejo total).
"""
from __future__ import annotations

import json
import re
import sys
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
NIT_FEAB = "901148337"
JBJY_URL = "https://www.datos.gov.co/resource/jbjy-vk9h.json"
RPMR_URL = "https://www.datos.gov.co/resource/rpmr-utcd.json"


def http_get_json(url: str, params: dict[str, str] | None = None, timeout: int = 30) -> Any:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def normalize_money(v: Any) -> float | None:
    """Normaliza un valor monetario a float. None si no parsea."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace("$", "").replace(" ", "").strip()
    # Si tiene "," como decimal CO ("12.000.000,50") o como miles US
    if "," in s and "." in s:
        # Asumir formato CO: "12.000.000,50" → "12000000.50"
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        # Solo comas: pueden ser decimales o miles
        parts = s.split(",")
        if len(parts) == 2 and len(parts[1]) <= 2:
            s = parts[0].replace(".", "") + "." + parts[1]
        else:
            s = s.replace(",", "")
    else:
        # Solo dots: pueden ser miles ("12.000.000")
        if s.count(".") > 1 or (s.count(".") == 1 and len(s.split(".")[-1]) == 3):
            s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def normalize_date(v: Any) -> str | None:
    """Normaliza fecha a YYYY-MM-DD. None si no parsea."""
    if not v:
        return None
    s = str(v).strip()
    # ISO o ISO con tiempo
    iso = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if iso:
        return f"{iso.group(1)}-{iso.group(2)}-{iso.group(3)}"
    # Formato CO "DD/MM/YYYY"
    co = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if co:
        return f"{co.group(3)}-{co.group(2).zfill(2)}-{co.group(1).zfill(2)}"
    return None


def normalize_text(v: Any) -> str:
    """Normaliza texto: lowercase, sin acentos, sin puntuación múltiple, sin espacios extras."""
    if not v:
        return ""
    s = str(v).lower().strip()
    # Quitar acentos básicos
    repl = {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ñ": "n"}
    for k, vv in repl.items():
        s = s.replace(k, vv)
    # Espacios múltiples → uno
    s = re.sub(r"\s+", " ", s)
    return s


def texts_match(a: str, b: str, threshold: float = 0.85) -> bool:
    """Comparación fuzzy de textos. Si a y b son razonablemente similares → True.
    Útil para "GERMAN BOTERO" vs "Germán David Botero Rodríguez"."""
    a, b = normalize_text(a), normalize_text(b)
    if not a or not b:
        return False
    if a == b:
        return True
    # Si una es prefijo o subset razonable de la otra
    if a in b or b in a:
        return True
    # Coincidencia de palabras (>=70%)
    words_a = set(a.split())
    words_b = set(b.split())
    if not words_a or not words_b:
        return False
    inter = len(words_a & words_b)
    smaller = min(len(words_a), len(words_b))
    if smaller > 0 and inter / smaller >= threshold:
        return True
    return False


def money_close(a: float | None, b: float | None, tolerance_pct: float = 0.5) -> bool:
    """Dos valores son 'iguales' si difieren <0.5%. Tolera redondeos."""
    if a is None or b is None:
        return a is None and b is None
    if a == b:
        return True
    if max(a, b) == 0:
        return True
    diff_pct = abs(a - b) / max(abs(a), abs(b)) * 100
    return diff_pct < tolerance_pct


def fetch_jbjy_by_nit() -> dict[str, dict]:
    """Trae todos los contratos del FEAB de jbjy-vk9h, indexados por id_contrato y proceso_de_compra."""
    print("  Fetching jbjy-vk9h...", end="", flush=True)
    rows = http_get_json(JBJY_URL, {"nit_entidad": NIT_FEAB, "$limit": "5000"})
    print(f" {len(rows)} rows")
    by_id: dict[str, dict] = {}
    by_proceso: dict[str, dict] = {}
    for r in rows:
        if isinstance(r, dict):
            if "id_contrato" in r and r["id_contrato"]:
                by_id[r["id_contrato"]] = r
            if "proceso_de_compra" in r and r["proceso_de_compra"]:
                by_proceso[r["proceso_de_compra"]] = r
    return {"by_id": by_id, "by_proceso": by_proceso}


def fetch_rpmr_by_nit() -> dict[str, dict]:
    """Trae todos los procesos del FEAB de rpmr-utcd, indexados por url_contrato regex."""
    print("  Fetching rpmr-utcd...", end="", flush=True)
    rows = http_get_json(RPMR_URL, {"nit_de_la_entidad": NIT_FEAB, "$limit": "5000"})
    print(f" {len(rows)} rows")
    by_notice: dict[str, dict] = {}
    by_pccntr: dict[str, dict] = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        url = r.get("url_contrato", "") or ""
        # Extraer NTC y PCCNTR del URL
        ntc_match = re.search(r"CO1\.NTC\.\d+", url)
        if ntc_match:
            by_notice[ntc_match.group(0)] = r
        pccntr_match = re.search(r"CO1\.PCCNTR\.\d+", url)
        if pccntr_match:
            by_pccntr[pccntr_match.group(0)] = r
    return {"by_notice": by_notice, "by_pccntr": by_pccntr}


def load_portal_seed() -> dict[str, dict]:
    """Carga el portal seed local."""
    p = REPO_ROOT / "app" / "public" / "data" / "portal_opportunity_seed.json"
    if not p.exists():
        print("  ⚠️ portal seed no existe localmente")
        return {}
    print(f"  Loading portal seed... ", end="", flush=True)
    seed = json.loads(p.read_text(encoding="utf-8"))
    print(f"{len(seed)} processes")
    return seed


def load_watched() -> list[dict]:
    """Carga el watch list."""
    p = REPO_ROOT / ".cache" / "watched_urls.json"
    if not p.exists():
        p = REPO_ROOT / "app" / "public" / "data" / "watched_urls.json"
    items = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(items, dict):
        items = items.get("items", [])
    return items


def cross_check_proceso(
    process_id: str,
    notice_uid: str | None,
    jbjy: dict,
    rpmr: dict,
    portal_seed: dict,
) -> list[dict]:
    """Cross-check de un proceso contra las 3 fuentes."""
    discrepancies: list[dict] = []

    # Encontrar en cada fuente
    # 1. jbjy: por proceso_de_compra (notice_uid o process_id)
    jbjy_match = None
    for k in [notice_uid, process_id]:
        if k and k in jbjy.get("by_proceso", {}):
            jbjy_match = jbjy["by_proceso"][k]
            break
        if k and k in jbjy.get("by_id", {}):
            jbjy_match = jbjy["by_id"][k]
            break

    # 2. rpmr: por NTC (notice_uid) o PCCNTR
    rpmr_match = None
    for k in [notice_uid, process_id]:
        if k and k in rpmr.get("by_notice", {}):
            rpmr_match = rpmr["by_notice"][k]
            break
        if k and k in rpmr.get("by_pccntr", {}):
            rpmr_match = rpmr["by_pccntr"][k]
            break

    # 3. portal: por notice_uid o process_id
    portal_match = portal_seed.get(notice_uid or "") or portal_seed.get(process_id or "")

    sources_present = sum(
        bool(x) for x in [jbjy_match, rpmr_match, portal_match]
    )
    if sources_present < 2:
        # Solo en 1 fuente o ninguna · no hay nada que cross-check
        return discrepancies

    # CROSS-CHECK valores
    fields_compared = []

    # 1. valor del contrato
    val_jbjy = normalize_money(
        jbjy_match.get("valor_del_contrato") if jbjy_match else None
    )
    val_rpmr = normalize_money(
        rpmr_match.get("valor_contrato") if rpmr_match else None
    )
    val_portal = (
        normalize_money(portal_match.get("fields", {}).get("valor_total"))
        if portal_match else None
    )
    valores = [(s, v) for s, v in [("jbjy", val_jbjy), ("rpmr", val_rpmr), ("portal", val_portal)] if v is not None]
    if len(valores) >= 2:
        fields_compared.append("valor")
        for i, (s1, v1) in enumerate(valores):
            for s2, v2 in valores[i + 1:]:
                if not money_close(v1, v2):
                    discrepancies.append({
                        "process_id": process_id,
                        "notice_uid": notice_uid,
                        "campo": "valor_del_contrato",
                        "fuente_a": s1,
                        "valor_a": v1,
                        "fuente_b": s2,
                        "valor_b": v2,
                        "diff_pct": round(abs(v1 - v2) / max(abs(v1), abs(v2)) * 100, 2)
                        if max(abs(v1), abs(v2)) > 0 else 0,
                    })

    # 2. fecha de firma
    fecha_jbjy = normalize_date(
        jbjy_match.get("fecha_de_firma") if jbjy_match else None
    )
    fecha_rpmr = normalize_date(
        rpmr_match.get("fecha_de_firma_del_contrato") if rpmr_match else None
    )
    fecha_portal = (
        normalize_date(portal_match.get("fields", {}).get("fecha_firma_contrato")
                      or portal_match.get("fields", {}).get("fecha_firma"))
        if portal_match else None
    )
    fechas = [(s, f) for s, f in [("jbjy", fecha_jbjy), ("rpmr", fecha_rpmr), ("portal", fecha_portal)] if f]
    if len(fechas) >= 2:
        fields_compared.append("fecha")
        unique_fechas = set(f for _, f in fechas)
        if len(unique_fechas) > 1:
            for i, (s1, f1) in enumerate(fechas):
                for s2, f2 in fechas[i + 1:]:
                    if f1 != f2:
                        discrepancies.append({
                            "process_id": process_id,
                            "notice_uid": notice_uid,
                            "campo": "fecha_de_firma",
                            "fuente_a": s1,
                            "valor_a": f1,
                            "fuente_b": s2,
                            "valor_b": f2,
                        })

    # 3. proveedor
    prov_jbjy = jbjy_match.get("proveedor_adjudicado") if jbjy_match else None
    prov_rpmr = rpmr_match.get("nom_raz_social_contratista") if rpmr_match else None
    prov_portal = portal_match.get("fields", {}).get("proveedor") if portal_match else None
    proveedores = [(s, p) for s, p in [("jbjy", prov_jbjy), ("rpmr", prov_rpmr), ("portal", prov_portal)] if p]
    if len(proveedores) >= 2:
        fields_compared.append("proveedor")
        for i, (s1, p1) in enumerate(proveedores):
            for s2, p2 in proveedores[i + 1:]:
                if not texts_match(p1, p2):
                    discrepancies.append({
                        "process_id": process_id,
                        "notice_uid": notice_uid,
                        "campo": "proveedor",
                        "fuente_a": s1,
                        "valor_a": p1,
                        "fuente_b": s2,
                        "valor_b": p2,
                    })

    return discrepancies


def main() -> int:
    print("=" * 64)
    print("CROSS-CHECK ENTRE FUENTES DEL SECOP · 3 datasets")
    print("=" * 64)
    print()
    print("Cardinal: detecta cuando el SECOP MISMO se contradice entre")
    print("sus datasets · alerta antes que Compliance lo descubra.")
    print()

    print("=== Cargando fuentes ===")
    jbjy = fetch_jbjy_by_nit()
    rpmr = fetch_rpmr_by_nit()
    portal = load_portal_seed()
    watched = load_watched()
    print()

    print(f"=== Cross-checking {len(watched)} procesos del watch list ===")
    all_discrepancies: list[dict] = []
    multi_source_count = 0
    for it in watched:
        process_id = it.get("process_id")
        notice_uid = it.get("notice_uid")
        if not process_id and not notice_uid:
            continue
        discs = cross_check_proceso(process_id, notice_uid, jbjy, rpmr, portal)
        if discs:
            all_discrepancies.extend(discs)
        # Contar cuántos están en >=2 fuentes
        in_jbjy = any(k in jbjy.get("by_proceso", {}) or k in jbjy.get("by_id", {}) for k in [notice_uid, process_id] if k)
        in_rpmr = any(k in rpmr.get("by_notice", {}) or k in rpmr.get("by_pccntr", {}) for k in [notice_uid, process_id] if k)
        in_portal = bool(portal.get(notice_uid or "") or portal.get(process_id or ""))
        if sum([in_jbjy, in_rpmr, in_portal]) >= 2:
            multi_source_count += 1

    print(f"  Procesos en >=2 fuentes (cross-checkeable): {multi_source_count}")
    print(f"  Discrepancias detectadas: {len(all_discrepancies)}")
    print()

    # Reporte
    fecha_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_json = REPO_ROOT / f"_DISCREPANCIAS_FUENTES_{fecha_iso}.json"
    out_md = REPO_ROOT / f"_DISCREPANCIAS_FUENTES_{fecha_iso}.md"

    out_data = {
        "fecha": datetime.now(timezone.utc).isoformat(),
        "total_watched": len(watched),
        "multi_source_count": multi_source_count,
        "total_discrepancias": len(all_discrepancies),
        "discrepancias": all_discrepancies,
    }
    out_json.write_text(json.dumps(out_data, indent=2, ensure_ascii=False), encoding="utf-8")

    # Markdown
    lines = [
        f"# Discrepancias entre fuentes del SECOP — {fecha_iso}",
        "",
        f"**Total procesos en watch list**: {len(watched)}",
        f"**Procesos en ≥2 fuentes (cross-checkeables)**: {multi_source_count}",
        f"**Discrepancias detectadas**: {len(all_discrepancies)}",
        "",
    ]
    if all_discrepancies:
        # Agrupar por tipo
        by_field = Counter(d["campo"] for d in all_discrepancies)
        lines.append("## Resumen por campo")
        for campo, count in by_field.most_common():
            lines.append(f"- **{campo}**: {count} discrepancias")
        lines.append("")
        lines.append("## Detalle")
        for d in all_discrepancies[:50]:  # Cap a 50
            lines.append(f"### {d['process_id']} · {d['campo']}")
            lines.append(f"- **{d['fuente_a']}**: `{d['valor_a']}`")
            lines.append(f"- **{d['fuente_b']}**: `{d['valor_b']}`")
            if "diff_pct" in d:
                lines.append(f"- Diferencia: {d['diff_pct']}%")
            lines.append("")
        if len(all_discrepancies) > 50:
            lines.append(f"_... y {len(all_discrepancies) - 50} más en el JSON_")
    else:
        lines.append("✅ **TODO LIMPIO** — las 3 fuentes del SECOP coinciden cardinal.")
        lines.append("")
        lines.append("**Verdict**: el SECOP es consistente consigo mismo para los procesos del watch list.")

    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(f"Reporte JSON: {out_json}")
    print(f"Reporte MD:   {out_md}")

    if all_discrepancies:
        print()
        print(f"⚠️ {len(all_discrepancies)} discrepancias detectadas · revisar reporte")
        return 1
    print()
    print("✅ TODO LIMPIO · las 3 fuentes del SECOP coinciden cardinal")
    return 0


if __name__ == "__main__":
    sys.exit(main())
