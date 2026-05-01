"""Sesion 3 v3 · Clasificacion cardinal POR CONTENIDO + extraccion de detalles.

Sergio 2026-04-28: "los pdfs son la verdad y toca mirarlos no nos guiemos
para nada en el nombre del pdf".
Sergio 2026-04-30: "toca entrar a cada documento para mirar que numero
de documento es y que es el modificatorio si es por ejemplo adicion,
prorroga y asi".

Cambios v3 respecto a v2:
  - Despues de la clasificacion primaria, se llama a extract_details para
    sacar subtipos cardinales (Adicion, Prorroga, etc), valor adicionado,
    dias prorrogados, fecha del documento.
  - Se usa el tipo primary para evitar FP en subtipos (una Liquidacion
    no debe detectar Suspension+Reanudacion accesorios).
  - Bumpea version del JSON a 3 · forza re-procesamiento.
  - Total de paginas leidas pasa de 3 a 8 para alcanzar clausulas resolutivas.

Uso:
    python scripts/ocr_classify_modificatorios.py --uid CO1.NTC.5405127
    python scripts/ocr_classify_modificatorios.py --all-cached --force
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pdfplumber
import pytesseract
import spacy

# Modulo cardinal de extraccion de detalles · validado en piloto
sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_modificatorio_details import extract_details  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CACHE_ROOT = ROOT / ".cache" / "modificatorios_pdfs"
INDEX_PATH = CACHE_ROOT / "index.json"
OCR_RESULTS_PATH = CACHE_ROOT / "ocr_classified.json"

log = logging.getLogger("ocr-classify")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

# Carga modelo spaCy una vez (reusable). es_core_news_md es 42 MB.
# CARDINAL: dejamos POS tagger habilitado (para identificar sustantivos
# principales del titulo). Deshabilitamos solo NER y parser (innecesarios).
log.info("Cargando spaCy es_core_news_md...")
NLP = spacy.load("es_core_news_md", disable=["ner", "parser"])
log.info("spaCy listo · POS tagger habilitado para análisis cardinal")


def find_principal_noun_in_title(title: str) -> tuple[str | None, int]:
    """Usa spaCy POS tagger para encontrar el sustantivo cardinal principal
    del titulo. Devuelve (lemma, pos_inicio_en_titulo) o (None, -1).

    Cardinal: el primer NOUN del titulo cuyo lemma esté en nuestro set
    cardinal es probablemente el TIPO del documento. Esto desambigua
    casos donde varias keywords aparecen (ej. "ACTA DE LIQUIDACIÓN"
    tiene "ACTA" + "LIQUIDACIÓN" · ambas son sustantivos pero el
    cardinal es "liquidación").
    """
    if not title:
        return None, -1
    all_lemmas = {l for lemmas in LEMMAS_BY_TYPE.values() for l in lemmas}
    doc = NLP(title[:200])
    for token in doc:
        if token.pos_ in ("NOUN", "PROPN"):
            lem = token.lemma_.lower()
            # Match exacto
            if lem in all_lemmas:
                return lem, token.idx
            # Match permitiendo accent variants
            for known in all_lemmas:
                if lem == known or lem.replace("ó", "o").replace("í", "i") == known:
                    return known, token.idx
    return None, -1


def lemma_to_tipo(lemma: str) -> str | None:
    """Mapea un lemma cardinal a su Tipo."""
    for tipo, lemmas_list in LEMMAS_BY_TYPE.items():
        for l in lemmas_list:
            if l == lemma or l.replace("ó", "o").replace("í", "i") == lemma:
                return tipo
    return None


# Lemas cardinales por tipo. Cada tipo asocia a un lema raiz que spaCy
# normaliza desde flexiones ("modificatorios" -> "modificatorio").
LEMMAS_BY_TYPE: dict[str, list[str]] = {
    "Modificatorio": ["modificatorio"],
    "Adicion": ["adicion", "adición"],
    "Prorroga": ["prorroga", "prórroga"],
    "Otrosi": ["otrosi", "otrosí"],
    "Adenda": ["adenda", "adendo"],
    "Cesion": ["cesion", "cesión"],
    "Suspension": ["suspension", "suspensión"],
    "Reanudacion": ["reanudacion", "reanudación"],
    "Terminacion anticipada": ["terminacion anticipada", "terminación anticipada"],
    "Liquidacion": ["liquidacion", "liquidación"],
    "Novacion": ["novacion", "novación"],
    "Aclaratorio": ["aclaratorio", "aclaratoria"],
    "Legalizacion (soporte)": ["legalizacion", "legalización"],
}

# Palabras de "scope" que NO son tipo principal · si aparecen seguidas
# de un sustantivo cardinal, ellas mandan (ej. "ACLARATORIO A LA CESION"
# es Aclaratorio, no Cesion).
SCOPE_PREFIXES = {"aclaratorio", "aclaratoria", "soporte", "anexo"}

# Boilerplate del SECOP para limpiar antes de buscar titulo
SECOP_BOILERPLATE_PATTERNS = [
    re.compile(r"radicado\s+no[.:\s]*\d+", re.IGNORECASE),
    re.compile(r"p[aá]gina\s+\d+\s+de\s+\d+", re.IGNORECASE),
    re.compile(r"\d{1,2}/\d{1,2}/\d{2,4}\s+\d{1,2}[:.]\d{2}\s*(?:am|pm)?",
               re.IGNORECASE),
    re.compile(r"colombia\s+compra\s+eficiente", re.IGNORECASE),
    re.compile(r"^\s*\d{10,}\s*$", re.MULTILINE),  # IDs de radicado largos
]


def clean_secop_boilerplate(text: str) -> str:
    """Quita header/footer del SECOP que ensucia la busqueda del titulo."""
    cleaned = text
    for pat in SECOP_BOILERPLATE_PATTERNS:
        cleaned = pat.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def extract_text(pdf_path: Path, max_pages: int = 8) -> tuple[str, str, str]:
    """Extrae texto · pdfplumber primero, OCR Tesseract spa fallback.

    Devuelve `(full_text, header_text, method)`:
      - `full_text`: hasta `max_pages` paginas · usado para extract_details
        (necesita ver clausulas resolutivas que estan en pag 2-4 despues
        de los considerandos).
      - `header_text`: SOLO pagina 1 · usado para classify_with_spacy.
        Cardinal: el TITULO del documento esta SIEMPRE en la primera
        pagina · si subimos max_pages a 8 y dejamos que classify use
        todo, agarra titulos de anexos posteriores (ej: "Reporte Relacion
        de Pagos" del acta de liquidacion) y rompe la clasificacion.
    """
    try:
        with pdfplumber.open(pdf_path) as pdf:
            n_pages = len(pdf.pages)
            native_parts = []
            for p in pdf.pages[:max_pages]:
                t = p.extract_text() or ""
                native_parts.append(t)
            native = "\n".join(native_parts)
            header_native = native_parts[0] if native_parts else ""

            if len(native.strip()) >= 100:
                # CARDINAL FIX (2026-04-30): si la pag 1 NATIVA esta vacia
                # (PDF mixto · pag 1 es imagen escaneada, pag 2-N tiene
                # texto nativo), OCRear pag 1 forzosamente para tener
                # header valido para clasificacion. Sin esto, el
                # classify cae a confidence 0.0 aunque el resto del
                # documento sea legible.
                if len(header_native.strip()) < 50 and pdf.pages:
                    img0 = pdf.pages[0].to_image(resolution=200)
                    header_native = pytesseract.image_to_string(
                        img0.original, lang="spa",
                    )
                return native, header_native, "pdfplumber"

            ocr_parts = []
            for page in pdf.pages[:max_pages]:
                img = page.to_image(resolution=200)
                t = pytesseract.image_to_string(img.original, lang="spa")
                ocr_parts.append(t)
            full_ocr = "\n".join(ocr_parts)
            header_ocr = ocr_parts[0] if ocr_parts else ""
            return full_ocr, header_ocr, f"tesseract-{n_pages}p"
    except Exception as e:
        return f"[ERROR: {e}]", "", "error"


def extract_title_candidates(cleaned_text: str) -> list[str]:
    """Devuelve lineas candidatas a ser el TITULO del documento.

    Heuristica cardinal:
      - Primeras lineas con MAYUSCULAS y > 20 chars
      - Lineas que contengan al menos 2 keywords cardinales
      - Tope a 5 candidatos
    """
    lines = [ln.strip() for ln in cleaned_text.split("\n") if ln.strip()]
    candidates = []
    for ln in lines[:30]:  # solo primeras 30 lineas
        # Skip si es muy corto
        if len(ln) < 15:
            continue
        # Es candidato si tiene mayoria mayusculas o contiene keyword
        upper_ratio = sum(1 for c in ln if c.isupper()) / max(len(ln), 1)
        has_keyword = any(
            re.search(r"\b" + lemma.replace(" ", r"\s+") + r"\b", ln, re.IGNORECASE)
            for lemmas in LEMMAS_BY_TYPE.values()
            for lemma in lemmas
        )
        if upper_ratio > 0.5 or has_keyword:
            candidates.append(ln)
        if len(candidates) >= 5:
            break
    if not candidates and lines:
        candidates = [lines[0]]
    return candidates


def classify_with_spacy(cleaned_text: str) -> dict[str, Any]:
    """Clasifica el documento usando spaCy lemmatization sobre los primeros
    1500 chars del texto limpio. Reglas cardinales:

      1. Si en los primeros 100 tokens aparece "legalizacion" + "asunto"
         o "oficio remisorio" -> tipo = Legalizacion (soporte).
      2. Si el TITULO (primera linea cardinal con keyword) contiene
         claramente UN tipo + numero -> ese tipo con confidence 0.95.
      3. Si en primeras 500 chars aparece keyword cardinal sin "asunto"
         ni "legalizacion" como prefijo -> ese tipo con confidence 0.85.
      4. Else -> "Por revisar manualmente" con confidence 0.3.
    """
    head = cleaned_text[:1500]
    if not head.strip():
        return {"tipo": None, "numero": None, "confidence": 0.0,
                "reason": "texto vacio", "title_used": ""}

    doc = NLP(head)
    lemmas_lower = [t.lemma_.lower() for t in doc]
    text_lower = head.lower()

    # Detectar legalizacion vs modificatorio real
    has_legalizacion = "legalizacion" in lemmas_lower or "legalización" in text_lower
    has_asunto = re.search(r"asunto[:\s]", text_lower[:200])
    is_oficio = re.search(
        r"oficio\s+remisorio|me\s+permito\s+informarle|respetad[oa]\s+(?:funcionari|señor)",
        text_lower[:500],
    )

    # CARDINAL ANTI-FP (Sergio 2026-04-30): detectar SOPORTES PRESUPUESTALES
    # (CDPs / Compromiso Presupuestal) y POLIZAS de garantia. Estos son
    # documentos asociados al modificatorio · NO son actos contractuales.
    # 8/8 docs tipo=Adicion eran FP por matchear "ADICIÓN" en titulos de
    # CDPs/polizas que mencionan "adicion y prorroga" como referencia.
    is_cdp = re.search(
        r"compromiso\s+presupuestal\s+de\s+gasto|"
        r"reporte\s+compromiso\s+presupuestal|"
        r"certificado\s+de\s+disponibilidad\s+presupuestal|"
        r"\bcdp\s+(?:n[oº°]|numero)",
        text_lower[:600],
    )
    if is_cdp:
        num_m = re.search(r"n[°ºo]\s*(\d{1,5})", text_lower[:500])
        return {
            "tipo": "Compromiso (soporte)",
            "numero": num_m.group(1) if num_m else None,
            "confidence": 0.95,
            "reason": "doc es CDP/Compromiso Presupuestal · soporte presupuestal del modificatorio",
            "title_used": text_lower[:200],
        }

    # Polizas y seguros · pueden tener encabezado OCR ruidoso ("re eeec...")
    # antes de las palabras cardinales · permitir hasta 800 chars de busqueda
    # y match en cualquier posicion (no anchored al inicio).
    is_poliza = re.search(
        r"\b(?:seguro\s+de\s+cumplimiento|aprobaci[oó]n\s+p[oó]liza|"
        r"compa[ñn][ií]a\s+(?:mundial\s+)?de\s+seguros|"
        r"aseguradora\s+\w+|"
        r"p[oó]liza\s+de\s+(?:cumplimiento|seriedad|garant[ií]a|responsabilidad))",
        text_lower[:800],
        re.IGNORECASE,
    )
    if is_poliza:
        num_m = re.search(r"n[°ºo]\s*(\d{1,5})", text_lower[:500])
        return {
            "tipo": "Poliza (soporte)",
            "numero": num_m.group(1) if num_m else None,
            "confidence": 0.95,
            "reason": "doc es Poliza/Seguro · soporte de garantia del modificatorio",
            "title_used": text_lower[:200],
        }

    # Reglas tempranas anti-FP
    if has_legalizacion and (has_asunto or is_oficio):
        num_m = re.search(r"n[°ºo]\s*(\d{1,3})", text_lower[:500])
        return {
            "tipo": "Legalizacion (soporte)",
            "numero": num_m.group(1) if num_m else None,
            "confidence": 0.92,
            "reason": "doc tiene 'legalizacion' + ASUNTO/oficio remisorio",
            "title_used": text_lower[:200],
        }

    # Buscar candidatos de titulo
    titles = extract_title_candidates(cleaned_text)
    primary_title = titles[0] if titles else ""

    # CARDINAL ANALYSIS (Sergio "tienes que analizar contexto"):
    # Usar spaCy POS tagger para encontrar el SUSTANTIVO PRINCIPAL del
    # titulo (primer NOUN con lemma cardinal). Este metodo es robusto
    # contra keywords que aparecen como adjetivos o en frases secundarias.
    primary_lemma, pos_in_title = find_principal_noun_in_title(primary_title)

    # Detectar prefix de scope: si "ACLARATORIO A LA CESION", el aclaratorio
    # manda. Buscamos en los primeros tokens del titulo.
    title_lower = primary_title.lower()
    scope_match = None
    for scope_word in SCOPE_PREFIXES:
        if title_lower.startswith(scope_word) or f" {scope_word} " in title_lower[:60]:
            scope_match = scope_word
            break
    if scope_match == "aclaratorio" or scope_match == "aclaratoria":
        num_m = re.search(r"n[°ºo]\s*(\d{1,3})", primary_title.lower())
        return {
            "tipo": "Aclaratorio",
            "numero": num_m.group(1) if num_m else None,
            "confidence": 0.93,
            "reason": "titulo empieza con 'aclaratorio' · scope manda sobre keywords secundarias",
            "title_used": primary_title[:150],
        }

    if primary_lemma:
        tipo = lemma_to_tipo(primary_lemma)
        if tipo:
            num_m = re.search(r"n[°ºo]\s*(\d{1,3})", primary_title.lower())
            return {
                "tipo": tipo,
                "numero": num_m.group(1) if num_m else None,
                "confidence": 0.96,
                "reason": (
                    f"spaCy POS · sustantivo cardinal '{primary_lemma}' en "
                    f"pos {pos_in_title} del titulo (NOUN/PROPN)"
                ),
                "title_used": primary_title[:150],
            }

    # Fallback regex · misma logica position-based pero con todos los tipos
    matches = []
    for tipo, lemmas_list in LEMMAS_BY_TYPE.items():
        if tipo == "Legalizacion (soporte)":
            continue
        for lemma in lemmas_list:
            pat = re.compile(r"\b" + lemma.replace(" ", r"\s+") + r"\b",
                             re.IGNORECASE)
            m = pat.search(primary_title)
            if m:
                matches.append((m.start(), tipo, lemma))
                break
    if matches:
        matches.sort()
        pos, tipo, lemma = matches[0]
        num_m = re.search(r"n[°ºo]\s*(\d{1,3})", primary_title.lower())
        return {
            "tipo": tipo,
            "numero": num_m.group(1) if num_m else None,
            "confidence": 0.90,
            "reason": (
                f"regex fallback · keyword '{lemma}' en pos {pos} del titulo "
                "(spaCy POS no encontró sustantivo cardinal)"
            ),
            "title_used": primary_title[:150],
        }

    # Si el titulo no tiene keyword cardinal, buscar en cuerpo · misma logica
    body = head[:500]
    body_matches = []
    for tipo, lemmas_list in LEMMAS_BY_TYPE.items():
        if tipo == "Legalizacion (soporte)":
            continue
        for lemma in lemmas_list:
            pat = re.compile(r"\b" + lemma.replace(" ", r"\s+") + r"\b",
                             re.IGNORECASE)
            m = pat.search(body)
            if m:
                body_matches.append((m.start(), tipo, lemma))
                break
    if body_matches:
        body_matches.sort()
        pos, tipo, lemma = body_matches[0]
        num_m = re.search(r"n[°ºo]\s*(\d{1,3})", body.lower())
        return {
            "tipo": tipo,
            "numero": num_m.group(1) if num_m else None,
            "confidence": 0.85,
            "reason": f"keyword '{lemma}' en pos {pos} del cuerpo",
            "title_used": primary_title[:150],
        }

    return {
        "tipo": None,
        "numero": None,
        "confidence": 0.3,
        "reason": "sin keywords cardinales · revision humana necesaria",
        "title_used": primary_title[:150],
    }


def process_pdf(pdf_path: Path, original_name: str) -> dict:
    """Procesa un PDF · clasificacion cardinal POR CONTENIDO + extraccion v3.

    Pipeline cardinal de 2 pasadas:
      1. CLASIFICAR con texto de la pagina 1 (header del documento) ·
         evita FP de anexos posteriores que rompen find_principal_noun.
      2. EXTRAER DETALLES con texto completo (8 paginas) · necesita ver
         clausulas resolutivas (PRIMERA: Prorrogar, SEGUNDA: Adicionar)
         que estan despues de los considerandos.
    """
    full_text, header_text, method = extract_text(pdf_path)
    cleaned_full = clean_secop_boilerplate(full_text)
    cleaned_header = clean_secop_boilerplate(header_text)
    cls = classify_with_spacy(cleaned_header)
    tipo = cls.get("tipo")

    # v3: extraer detalles cardinales (subtipos, valor, plazo, fecha)
    # · usa texto completo porque las clausulas resolutivas estan en pag 2-4
    details = extract_details(cleaned_full, tipo_primary=tipo)

    return {
        "pdf_name_audit": original_name,  # solo audit · no usado para clasificar
        "pdf_path": str(pdf_path.relative_to(ROOT)).replace("\\", "/"),
        "extraction_method": method,
        "raw_text_chars": len(full_text),
        "cleaned_text_chars": len(cleaned_full),
        "title_used": cls.get("title_used", "")[:200],
        "tipo": tipo,
        "numero": cls.get("numero"),
        "confidence": cls.get("confidence"),
        "classification_reason": cls.get("reason"),
        "needs_human_review": (
            cls.get("confidence", 0) < 0.8 or tipo is None
        ),
        "is_modificatorio_cardinal": tipo in {
            "Modificatorio", "Adicion", "Prorroga", "Otrosi", "Adenda",
            "Cesion", "Suspension", "Reanudacion", "Terminacion anticipada",
            "Liquidacion", "Novacion",
        },
        # v3: detalles cardinales extraidos del cuerpo
        "subtipos": details.subtipos,
        "valor_adicionado_cop": details.valor_adicionado_cop,
        "dias_prorrogados": details.dias_prorrogados,
        "fecha_documento": details.fecha_documento,
        "extraction_warnings": details.extraction_warnings,
        "processed_at": datetime.now(timezone.utc).isoformat(),
    }


def load_ocr_results() -> dict:
    if not OCR_RESULTS_PATH.exists():
        return {"version": 3, "processes": {}}
    return json.loads(OCR_RESULTS_PATH.read_text(encoding="utf-8"))


def save_ocr_results(results: dict) -> None:
    OCR_RESULTS_PATH.write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--uid", help="Procesar solo PDFs de un proceso")
    g.add_argument("--all-cached", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--force", action="store_true",
                    help="Re-procesar incluso si ya esta clasificado")
    args = ap.parse_args()

    if not INDEX_PATH.exists():
        log.error("No hay index.json · correr download primero")
        return 1

    index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    results = load_ocr_results()
    # Bump version si formato antiguo (limpieza) · v3 incluye detalles cardinales
    if results.get("version") != 3 or args.force:
        results = {"version": 3, "processes": {}}

    targets = []
    if args.uid:
        targets = [args.uid] if args.uid in index["processes"] else []
    else:
        targets = list(index["processes"].keys())
    if args.limit:
        targets = targets[:args.limit]

    log.info("Targets: %d procesos", len(targets))
    totals = {"ok_high_conf": 0, "needs_review": 0, "no_match": 0,
              "is_modif": 0, "is_legalizacion": 0}

    for uid in targets:
        proc = index["processes"][uid]
        # CARDINAL idempotente (Sergio 2026-04-30): si NO hay --force y el
        # uid ya está procesado en results, skip. Permite reanudar runs
        # cortados sin re-procesar lo ya hecho. Con --force re-procesa todo.
        if not args.force and uid in results.get("processes", {}):
            existing_docs = results["processes"][uid].get("docs", [])
            if existing_docs:
                log.info("=== %s · SKIP (ya procesado · %d docs)", uid, len(existing_docs))
                continue
        log.info("=== %s · %d docs", uid, len(proc.get("docs", [])))
        out_proc = results["processes"].setdefault(uid, {"docs": []})
        out_proc["docs"] = []  # limpiar y re-procesar

        for doc_meta in proc.get("docs", []):
            if doc_meta.get("status") != "ok":
                continue
            doc_idx = doc_meta.get("doc_idx")
            path = ROOT / doc_meta["path"]
            if not path.exists() or doc_meta.get("file_type") != "pdf":
                continue

            log.info("  [%d] %s", doc_idx,
                     doc_meta.get("original_name", "")[:60])
            r = process_pdf(path, doc_meta.get("original_name", ""))
            r["doc_idx"] = doc_idx
            log.info(
                "      tipo=%s · num=%s · conf=%.2f%s · titulo=\"%s\"",
                r["tipo"], r["numero"], r["confidence"],
                " ⚠️ REVIEW" if r["needs_human_review"] else " ✅",
                r["title_used"][:80],
            )
            out_proc["docs"].append(r)

            if r["needs_human_review"]:
                totals["needs_review"] += 1
            else:
                totals["ok_high_conf"] += 1
            if r["is_modificatorio_cardinal"]:
                totals["is_modif"] += 1
            if r["tipo"] == "Legalizacion (soporte)":
                totals["is_legalizacion"] += 1

        save_ocr_results(results)

    log.info("=" * 60)
    log.info("DONE. Totales: %s", totals)
    log.info("Resultado: %s", OCR_RESULTS_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
