"""Extraccion cardinal de detalles del modificatorio · subtipo + valor + plazo + fecha.

Sergio 2026-04-30: "toca entrar a cada documento para mirar que numero
de documento es y que es el modificatorio si es por ejemplo adicion,
prorroga y asi".

Filosofia cardinal:
  - El nombre del PDF NO es fuente. Solo el contenido manda.
  - 0 FP / 0 FN / 0 datos comidos · si no podemos extraer un campo,
    queda en None honesto · NO inventar.
  - Si hay ambiguedad o conflicto · flag needs_human_review = True.

Que se extrae:
  1. subtipos · lista de actos cardinales contenidos en el modificatorio
     (Adicion, Prorroga, Cesion, Suspension, etc). Un MOD puede tener N.
  2. valor_adicionado · int en pesos COP cuando hay subtipo Adicion.
  3. dias_prorrogados · int dias cuando hay subtipo Prorroga.
  4. fecha_documento · ISO YYYY-MM-DD cuando se puede leer.
  5. valor_total_actualizado · int cuando aparece como suma cardinal.

Validacion: este modulo se prueba contra los 12 PDFs del piloto antes
de integrarse al pipeline. Cada doc debe pasar criterio cardinal:
  - Si dice "ADICIONAR" en clausula -> subtipos contiene "Adicion".
  - Si dice "PRORROGAR" en clausula -> subtipos contiene "Prorroga".
  - Valor extraido coincide con el numero entre parentesis del cuerpo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from datetime import date


@dataclass
class ModificatorioDetails:
    """Detalles cardinales extraidos del cuerpo de un modificatorio."""

    subtipos: list[str] = field(default_factory=list)
    valor_adicionado_cop: int | None = None
    dias_prorrogados: int | None = None
    valor_total_actualizado_cop: int | None = None
    fecha_documento: str | None = None  # ISO YYYY-MM-DD
    extraction_warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# === Subtipos cardinales ===
# Verbos en clausulas resolutivas (PRIMERA:, SEGUNDA:, etc).
# Tolerantes a errores de OCR comunes ("Premagar"->"Prorrogar", "Praregar"->"Prorrogar").

_VERB_PRORROGAR = re.compile(
    # Forma canonica + flexiones
    r"\bprorrog(?:ar|uese|ase|ar(?:emos|an)?)\b"
    # Frase nominal "prorroga del plazo"
    r"|\bpr[oó]rroga\b\s+(?:del?\s+)?(?:plazo|t[eé]rmino|ejecuci)"
    # Tolerancia a typos OCR comunes: Pre/Pra/Pro + 0-3 chars + gar + " el plazo"
    # Ejemplos reales del SECOP: "Premagar", "Praregar", "Promogar", "Prerogar"
    r"|\bpr[aeéoó]\w{0,4}gar\s+el\s+plazo",
    re.IGNORECASE,
)

_VERB_ADICIONAR = re.compile(
    # CARDINAL ANTI-FP (Sergio 2026-04-30): "tu tienes que estar 100% seguro"
    # Solo el verbo ADICIONAR/ADICIONESE literal, NUNCA "modificar el valor"
    # ni "incrementar" ni "establecer en la suma de" (esos pueden ser
    # modificaciones de canon o actualizaciones del valor total).
    # 4 de 5 top valores eran FP por matchear "modificar el valor del contrato"
    # como Adicion. Refinamos: solo el verbo ADICIONAR vale.
    r"\badicion[ae]r\s+(?:el\s+)?(?:contrato|valor\s+(?:total\s+)?del\s+contrato|"
    r"la\s+(?:cuant[ií]a|suma)\s+(?:total\s+)?del\s+contrato|"
    r"plazo\s+del\s+contrato)"
    r"|\badici[oó]n[ae]se\s+(?:el\s+)?(?:contrato|la\s+suma|el\s+valor)",
    re.IGNORECASE,
)

_VERB_CEDER = re.compile(
    r"\bceder\s+el\s+contrato"
    r"|\bcesi[oó]n\s+del?\s+contrato"
    r"|\bcedente\b"
    r"|\bcesionario\b",
    re.IGNORECASE,
)

_VERB_SUSPENDER = re.compile(
    r"\bsuspend(?:er|ase|er\s+la\s+ejecuci)|\bacta\s+de\s+suspensi[oó]n",
    re.IGNORECASE,
)

_VERB_REANUDAR = re.compile(
    r"\breanud(?:ar|ase|aci[oó]n)|\bacta\s+de\s+reanudaci",
    re.IGNORECASE,
)

_VERB_LIQUIDAR = re.compile(
    r"\bliquid(?:ar|ase|aci[oó]n)|\bacta\s+de\s+liquidaci"
    r"|\bsaldo\s+a\s+(?:favor|cargo)\b"
    r"|\bbalance\s+(?:financiero|de\s+ejecuci)",
    re.IGNORECASE,
)

_VERB_TERMINAR = re.compile(
    r"\bterminaci[oó]n\s+anticipada"
    r"|\bdar\s+por\s+terminado",
    re.IGNORECASE,
)

# Mapping verbo -> subtipo cardinal
_VERB_RULES: list[tuple[str, re.Pattern]] = [
    ("Prorroga", _VERB_PRORROGAR),
    ("Adicion", _VERB_ADICIONAR),
    ("Cesion", _VERB_CEDER),
    ("Suspension", _VERB_SUSPENDER),
    ("Reanudacion", _VERB_REANUDAR),
    ("Liquidacion", _VERB_LIQUIDAR),
    ("Terminacion anticipada", _VERB_TERMINAR),
]


def detect_subtipos(text: str, tipo_primary: str | None = None) -> list[str]:
    """Detecta subtipos cardinales en el cuerpo del modificatorio.

    Cardinal anti-FP: si tipo_primary es ya especifico (Cesion, Liquidacion,
    Suspension, Reanudacion, Aclaratorio, Terminacion anticipada), NO buscar
    subtipos accesorios · tipo primary ya es el subtipo correcto. Razon:
    una "Acta de Liquidacion" NARRA toda la historia del contrato (incluye
    suspensiones, reanudaciones, modificatorios anteriores), pero el tipo
    cardinal del documento es Liquidacion · no es un combo.

    Cardinal anti-FP (Sergio 2026-04-30): si tipo_primary es None (el
    clasificador primario falló por OCR pobre o título ambiguo), TAMPOCO
    inferir subtipos · esos serían FP de extracción ciega. Mejor None
    honesto que Modificatorio/Adicion inferido del cuerpo de un doc que
    capaz no es modificatorio. Caso real: ACTA LIQUIDACION sin titulo
    clasificado capturaba "Adicion" y valor del cuerpo narrativo.

    Solo cuando tipo_primary es generico (Modificatorio, Otrosi, Adenda)
    tiene sentido buscar subtipos en el cuerpo.
    """
    if not text:
        return []
    GENERIC_TIPOS = {"Modificatorio", "Otrosi", "Adenda"}
    if tipo_primary not in GENERIC_TIPOS:
        # Tipo primary especifico O None · NO inferir subtipos accesorios
        return []
    found = []
    for tipo, pat in _VERB_RULES:
        if pat.search(text):
            found.append(tipo)
    return found


# === Extraccion de valor monetario ===
# Patron canonico colombiano: $X.XXX.XXX donde "." es separador de miles.
# Ejemplos reales del piloto:
#   "$18.000.000" -> 18000000
#   "DIECIOCHO MILLONES DE PESOS M/CTE ($18.000.000)" -> 18000000
#   "$1.052.000" -> 1052000

_VALOR_PESOS_RE = re.compile(
    r"\$\s*([\d]{1,3}(?:[.,][\d]{3}){1,4})",
)

# Patron alternativo "VALOR EN LETRAS DE $X" para validacion cruzada
_VALOR_FRASE_RE = re.compile(
    r"(?:suma\s+de|valor\s+de|por\s+(?:el\s+)?valor\s+de|cuant[ií]a\s+de|"
    r"asciende\s+a\s+la?\s+suma\s+de)"
    r"\s+(?:[A-ZÁÉÍÓÚÑ\s]+(?:DE\s+PESOS)?\s+M[/.]?CTE)?\s*"
    r"\(?\$\s*([\d]{1,3}(?:[.,][\d]{3}){1,4})",
    re.IGNORECASE,
)


def parse_pesos(s: str) -> int | None:
    """Convierte '$18.000.000' o '1.052.000' a 18000000 / 1052000."""
    if not s:
        return None
    cleaned = re.sub(r"[^\d]", "", s)
    if not cleaned:
        return None
    try:
        n = int(cleaned)
        # Sanity: rechazar valores absurdos (< $100k o > $10 billones)
        if n < 100_000:
            return None
        if n > 10_000_000_000_000:
            return None
        return n
    except ValueError:
        return None


# Patron preferente: "ADICIONAR EL CONTRATO EN LA SUMA DE" + valor
# Tiene prioridad sobre "incremento mensual del canon".
_ADICIONAR_CONTRATO_RE = re.compile(
    r"adicion[ae]r\s+(?:el\s+contrato|el\s+valor\s+(?:total\s+)?del\s+contrato|"
    r"la\s+(?:cuant[ií]a|suma)\s+(?:total\s+)?del\s+contrato)\s+"
    r"(?:en\s+(?:la\s+suma\s+de\s+)?)?"
    r"[A-ZÁÉÍÓÚÑa-zñáéíóú\s/.,]{0,200}?"
    r"\(\s*\$\s*([\d]{1,3}(?:[.,][\d]{3}){1,4})",
    re.IGNORECASE | re.DOTALL,
)

# Patron de FP que se debe IGNORAR · canon mensual / pago periodico no es valor adicionado
_CANON_MENSUAL_RE = re.compile(
    r"(?:canon\s+(?:mensual|de\s+arrendamiento)|"
    r"valor\s+(?:mensual|del\s+canon)|"
    r"pago\s+mensual|"
    r"valor\s+total\s+del?\s+canon|"
    r"se\s+incrementa\s+en\s+la\s+suma\s+de|"
    r"el\s+canon\s+(?:de\s+arrendamiento\s+)?(?:mensual|asciende|se))",
    re.IGNORECASE,
)


def extract_valor_adicionado(text: str, has_adicion: bool) -> tuple[int | None, list[str]]:
    """Extrae valor monetario adicionado · solo si subtipo Adicion presente.

    Estrategia cardinal (en orden):
      1. Patron preferente: "ADICIONAR EL CONTRATO EN LA SUMA DE ($X)".
      2. Si solo hay match cerca de "canon mensual" o "incremento" -> warning
         honesto · puede ser valor mensual no total adicionado.
      3. Fallback: primer valor cerca del verbo Adicionar.
    """
    warnings: list[str] = []
    if not has_adicion or not text:
        return None, warnings

    # 1. Patron preferente · clausula directa "ADICIONAR EL CONTRATO ... $X"
    m = _ADICIONAR_CONTRATO_RE.search(text)
    if m:
        val = parse_pesos(m.group(1))
        if val:
            return val, warnings

    # 2. Buscar valor cerca del verbo Adicionar pero EXCLUIR si esta cerca
    #    de "canon mensual" o "se incrementa" · esos son valores mensuales.
    candidates: list[tuple[int, int, bool]] = []  # (pos, valor, es_mensual)
    for m_verb in _VERB_ADICIONAR.finditer(text):
        start = m_verb.start()
        slice_text = text[max(0, start - 100):start + 400]
        for m_val in _VALOR_PESOS_RE.finditer(slice_text):
            val = parse_pesos(m_val.group(1))
            if not val:
                continue
            # Chequear contexto inmediato para "canon mensual"
            ctx_start = max(0, m_val.start() - 100)
            ctx_end = min(len(slice_text), m_val.end() + 100)
            context = slice_text[ctx_start:ctx_end]
            es_mensual = bool(_CANON_MENSUAL_RE.search(context))
            candidates.append((start, val, es_mensual))

    # Preferir el primer candidato NO-mensual; si todos son mensuales, marcar warning
    no_mensual = [c for c in candidates if not c[2]]
    if no_mensual:
        return no_mensual[0][1], warnings
    if candidates:
        warnings.append(
            "valor extraido cerca de 'canon mensual' o 'incremento' · "
            "puede ser valor periodico no total adicionado"
        )
        return candidates[0][1], warnings

    # 3. Fallback final · busca frase cardinal pero EXCLUYE canon mensual
    # CARDINAL ANTI-FP (Sergio 2026-04-30): "tu tienes que estar 100% seguro".
    # Si el match esta cerca de "canon mensual" o "se incrementa la suma de"
    # NO devolver valor · es canon periodico, no valor adicionado total.
    # Mejor None honesto que cifra incorrecta · Cami va al PDF y lee.
    m = _VALOR_FRASE_RE.search(text)
    if m:
        val = parse_pesos(m.group(1))
        if val:
            # Chequear contexto del match · 200 chars antes/despues
            ctx_start = max(0, m.start() - 200)
            ctx_end = min(len(text), m.end() + 200)
            context = text[ctx_start:ctx_end]
            if _CANON_MENSUAL_RE.search(context):
                warnings.append(
                    "valor cerca de 'canon mensual' · NO es valor adicionado "
                    "total · ver clausulas del PDF para cifra correcta"
                )
                return None, warnings
            warnings.append(
                "valor extraido por frase cardinal · no clausula directa · "
                "verificar contra PDF"
            )
            return val, warnings

    warnings.append("subtipo Adicion detectado pero no se pudo extraer valor numerico")
    return None, warnings


# === Extraccion de plazo prorrogado ===
# Patrones reales del piloto:
#   "por un (1) año mas" -> 365 dias
#   "por DOS (2) meses" -> 60 dias (aprox)
#   "60 dias adicionales" -> 60 dias
#   "hasta el 15 de diciembre de 2017" -> calculado contra fecha original (no facil)

_NUM_PALABRAS = {
    "un": 1, "uno": 1, "una": 1,
    "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6,
    "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
    "once": 11, "doce": 12,
}

_PRORROGA_PLAZO_RE = re.compile(
    r"(?:por|en)\s+"
    r"([a-zA-Záéíóú]+|\d{1,3})"
    r"\s*\(?(\d{1,3})?\)?\s*"
    r"(d[ií]as?|meses?|a[ñn]os?|semanas?)"
    r"(?:\s+(?:adicionales|m[aá]s|de\s+plazo|de\s+ejecuci))?",
    re.IGNORECASE,
)


def _palabra_a_num(s: str) -> int | None:
    """Convierte 'un', 'dos', 'tres' a 1, 2, 3."""
    s_lower = s.lower().strip()
    if s_lower.isdigit():
        try:
            return int(s_lower)
        except ValueError:
            return None
    return _NUM_PALABRAS.get(s_lower)


def extract_dias_prorrogados(text: str, has_prorroga: bool) -> tuple[int | None, list[str]]:
    """Extrae dias de prorroga · solo si subtipo Prorroga presente."""
    warnings: list[str] = []
    if not has_prorroga or not text:
        return None, warnings

    # Buscar cerca del verbo Prorrogar
    for m_verb in _VERB_PRORROGAR.finditer(text):
        start = m_verb.start()
        slice_text = text[start:start + 400]
        m_pl = _PRORROGA_PLAZO_RE.search(slice_text)
        if m_pl:
            num_word = m_pl.group(1)
            num_paren = m_pl.group(2)
            unidad = m_pl.group(3).lower()
            n = None
            if num_paren:
                try:
                    n = int(num_paren)
                except ValueError:
                    pass
            if n is None:
                n = _palabra_a_num(num_word)
            if n is None:
                continue
            if unidad.startswith("d"):
                return n, warnings
            if unidad.startswith("sem"):
                return n * 7, warnings
            if unidad.startswith("mes"):
                return n * 30, warnings
            if unidad.startswith("a"):
                return n * 365, warnings

    warnings.append("subtipo Prorroga detectado pero no se pudo extraer plazo numerico")
    return None, warnings


# === Extraccion de fecha del documento ===
# Patron tipico al pie: "Bogota D.C., 27 de enero de 2025"

_MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5,
    "junio": 6, "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9,
    "octubre": 10, "noviembre": 11, "diciembre": 12,
}

_FECHA_LARGA_RE = re.compile(
    r"\b(\d{1,2})\s+de\s+"
    r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
    r"sept(?:i|í)embre|setiembre|octubre|noviembre|diciembre)"
    r"\s+de\s+(\d{4})",
    re.IGNORECASE,
)

_FECHA_NUMERICA_RE = re.compile(
    r"\b(\d{1,2})[/\.\-](\d{1,2})[/\.\-](\d{4})\b",
)


def extract_fecha_documento(text: str) -> tuple[str | None, list[str]]:
    """Extrae la fecha de suscripcion del documento.

    Heuristica: la primera fecha del documento puede ser la del contrato
    original (en considerandos). La fecha cardinal del modificatorio
    suele estar al final ("Bogota DC, X de mes de YYYY"). Tomamos:
      1. La ultima fecha encontrada en los ultimos 1500 chars.
      2. Fallback: la mas reciente entre todas las encontradas.
    """
    warnings: list[str] = []
    if not text:
        return None, warnings

    # Buscar todas las fechas largas
    fechas_isoformat = []
    for m in _FECHA_LARGA_RE.finditer(text):
        try:
            dia = int(m.group(1))
            mes_str = m.group(2).lower().replace("í", "i")
            mes = _MESES.get(mes_str)
            if mes is None:
                # try without unicode normalization
                for k, v in _MESES.items():
                    if k.startswith(mes_str[:5]):
                        mes = v
                        break
            anio = int(m.group(3))
            if mes and 1 <= dia <= 31 and 1990 <= anio <= 2030:
                fechas_isoformat.append((m.start(), date(anio, mes, dia).isoformat()))
        except (ValueError, AttributeError):
            continue

    if not fechas_isoformat:
        warnings.append("no se encontro fecha larga (DD de mes de YYYY)")
        return None, warnings

    # Tomar la ultima (mas cerca del final del documento)
    fechas_isoformat.sort()
    ultimo_pos, ultimo_iso = fechas_isoformat[-1]
    return ultimo_iso, warnings


# === Extraccion principal ===

def extract_details(text: str, tipo_primary: str | None = None) -> ModificatorioDetails:
    """Pipeline cardinal: subtipos -> valor -> plazo -> fecha.

    tipo_primary viene de la clasificacion previa (header del documento).
    Usado para evitar FP en subtipos cuando tipo es ya especifico.
    """
    if not text or len(text.strip()) < 50:
        return ModificatorioDetails(
            extraction_warnings=["texto vacio o muy corto"],
        )

    subtipos = detect_subtipos(text, tipo_primary=tipo_primary)
    has_adicion = "Adicion" in subtipos
    has_prorroga = "Prorroga" in subtipos

    valor_adic, w1 = extract_valor_adicionado(text, has_adicion)
    dias_prorr, w2 = extract_dias_prorrogados(text, has_prorroga)
    fecha_doc, w3 = extract_fecha_documento(text)

    return ModificatorioDetails(
        subtipos=subtipos,
        valor_adicionado_cop=valor_adic,
        dias_prorrogados=dias_prorr,
        fecha_documento=fecha_doc,
        extraction_warnings=w1 + w2 + w3,
    )


if __name__ == "__main__":
    # Smoke test rapido contra texto del piloto
    sample_text_mod1 = """
    PRIMERA: Prorrogar el plazo de ejecucion del contrato hasta el 15 de diciembre de 2017.
    SEGUNDA: Adicionar el contrato en la suma de DIECIOCHO MILLONES DE PESOS M/CTE
    ($18.000.000), incluido IVA, asi como los demas costos directos e indirectos.
    Bogota D.C., 25 de octubre de 2017.
    """
    d = extract_details(sample_text_mod1)
    print("Sample MOD1:", d.to_dict())
    assert "Prorroga" in d.subtipos
    assert "Adicion" in d.subtipos
    assert d.valor_adicionado_cop == 18_000_000
    assert d.fecha_documento == "2017-10-25"
    print("✅ Smoke test pasa.")
