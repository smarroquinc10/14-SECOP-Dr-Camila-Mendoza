"""Declarative mapping: SECOP fields -> Dra. Camila's exact 77 columns.

The Dra.'s workbook has 77 numbered columns plus auxiliary tool data.
This module knows:

* the EXACT header strings she uses (with tildes, spaces, punctuation)
* which columns can be filled from SECOP data automatically
* which are internal FEAB data (CDP, Orfeo, Abogado, etc.) — never touch
* how to derive each one from contract + process data with confidence

Cardinal rule: never overwrite existing manual data silently. If SECOP
disagrees with a non-empty cell, log a discrepancy and leave the cell.

Confidence levels:
    HIGH    — direct SECOP field, no ambiguity
    MEDIUM  — derived (sum, year extraction, percentage)
    LOW     — inferred from indirect signals
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

# ---- Her column names (exactly as they appear in the workbook) ---------------

COL_NUMERO_CONTRATO = "2. NÚMERO DE CONTRATO"
COL_VIGENCIA = "3.VIGENCIA"
COL_OBJETO = "4. OBJETO"
COL_FECHA_SUSCRIPCION = "5. FECHA SUSCRIPCIÓN"
COL_PLAZO = "6. PLAZO"
COL_REQUIERE_ACTA_INICIO = "7. REQUIERE ACTA DE INICIO"
COL_FECHA_INICIO = "8. FECHA INICIO"
COL_FECHA_TERMINACION = "9. FECHA TERMINACIÓN"
COL_ESTADO_CONTRATO = "10.ESTADO DEL CONTRATO"
COL_LUGAR_EJECUCION = "11.LUGAR DE EJECUCIÓN"
COL_MODALIDAD_SELECCION = "12. MODALIDAD DE SELECCIÓN"
COL_CLASE_CONTRATO = "13. CLASE DE CONTRATO"
COL_DESCRIBA_OTRA_CLASE = "14. DESCRIBA OTRA CLASE DE CONTRATO"
COL_VECES_SIRECI = "15. CANTIDAD DE VECES REGISTRADO EN EL SIRECI"
COL_TIPO_ORDEN = "16. TIPO DE ORDEN"
COL_ES_CONVENIO = "17.ES CONVENIO DE ASOCIACIÓN?"
COL_CLASE_CONVENIO = "18. CLASE DE CONVENIO"
COL_RECURSOS_CONVENIO = "19. RECURSOS PROVIENEN DE CONTRATO o CONVENIO INTERADTIVO?"
COL_ENTIDAD_RECURSOS_NIT = "20. ENTIDAD DE DONDE PROVIENEN LOS RECURSOS : NIT"
COL_ENTIDAD_RECURSOS_DV = "21. ENTIDAD DE DONDE PROVIENEN LOS RECURSOS : DÍGITO DE VERIFICACIÓN DEL NIT"
COL_ENTIDAD_RECURSOS_NOMBRE = "22. ENTIDAD DE DONDE PROVIENEN LOS RECURSOS : NOMBRE"
COL_FUENTE_RECURSOS = "23. FUENTE DE RECURSOS"
COL_RUBRO_PRESUPUESTAL = "24.RUBRO PRESUPUESTAL AFECTADO"
COL_NO_CDP = "25. No. CDP"
COL_FECHA_CDP = "25A. FECHA CDP"
COL_NO_RP = "26. N° REGISTRO PRESUPUESTAL"
COL_FECHA_RP = "26A. FECHA REGISTRO PRESUPUESTAL"
COL_CODIGO_SECOP_SIRECI = "27. CÓDIGO SECOP           SIRECI"
COL_VALOR_INICIAL = "28.VALOR INICIAL DEL CONTRATO (INCLUIDAS VIGENCIA ACTUAL Y FUTURAS)"
COL_VALOR_INICIAL_VIGENCIA_ACTUAL = "29. VALOR INICIAL DEL CONTRATO VIGENCIA ACTUAL"
COL_VIGENCIA_FUTURA_1 = "30. VALOR VIGENCIA FUTURA AÑO +1"
COL_VIGENCIA_FUTURA_2 = "31. VALOR VIGENCIA FUTURA AÑO +2"
COL_VIGENCIA_FUTURA_3 = "32. VALOR VIGENCIA FUTURA AÑO +3"
COL_TIPO_ANTICIPOS = "33. TIPO DE ANTICIPOS o PAGO ANTICIPADO"
COL_VALOR_ANTICIPOS = "34. ANTICIPOS o PAGO ANTICIPADO : VALOR TOTAL"
COL_TIPO_ADICIONES = "35. TIPO DE ADICIONES"
COL_REDUCCIONES = "35A. REDUCCIONES VALOR TOTAL"
COL_ADICIONES = "35A. ADICIONES VALOR TOTAL"
COL_VALOR_TOTAL = "36. VALOR TOTAL"
COL_PRORROGAS_DIAS = "37. PRÓRROGAS : NÚMERO DE DÍAS"
COL_CONTRATISTA_NATURALEZA = "38. CONTRATISTA : NATURALEZA"
COL_CONSORCIO = "39. CONSORCIO O UNIÓN TEMPORAL"
COL_CONTRATISTA_TIPO_ID = "40. CONTRATISTA : TIPO IDENTIFICACIÓN"
COL_CONTRATISTA_NUM_ID = "41. CONTRATISTA : NÚMERO DE IDENTIFICACIÓN CC, NIT O CEDULA DE EXTRANJERIA"
COL_CONTRATISTA_DV = "42. CONTRATISTA : DÍGITO DE VERIFICACIÓN NIT"
COL_CONTRATISTA_NOMBRE = "43. CONTRATISTA : NOMBRE COMPLETO"
COL_CONTRATISTA_DIRECCION = "44. DIRECCIÓN CONTRATISTA"
COL_CONTRATISTA_TELEFONO = "45. TELEFONO CONTRATISTA"
COL_CONTRATISTA_CORREO = "46.CORREO ELECTRÓNICO CONTRATISTA"
COL_GARANTIA_TIPO = "47. GARANTÍAS : TIPO DE GARANTÍA"
COL_GARANTIA_RIESGOS = "48. GARANTÍAS : RIESGOS"
COL_GARANTIA_FECHA_EXPED = "49. GARANTÍAS : FECHA DE EXPEDICIÓN DE GARANTÍAS"
COL_TIPO_SEGUIMIENTO = "50. TIPO DE SEGUIMIENTO"
COL_INTERVENTOR = "51.NOMBRE DEL INTERVENTOR (CUANDO APLIQUE)"
COL_SUPERVISOR_ID = "52. SUPERVISOR : NÚMERO DE IDENTIFICACIÓN CC, NIT O CEDULA"
COL_SUPERVISOR_NOMBRE = "53. SUPERVISOR : NOMBRE COMPLETO"
COL_SUPERVISOR_VINCULACION = "54.TIPO DE VINCULACIÓN DEL SUPERVISOR"
COL_DEPENDENCIA = "55. DEPENDENCIA SOLICITANTE"
COL_PERIOD_INFORMES_TIPO = "56.TIPO DE PERIODICIDAD EN INFORMES DE SUPERVISIÓN"
COL_PERIOD_INFORMES_DIAS = "57.PERIODICIDAD EN LA PRESENTACIÓN DE INFORMES (EN DIAS)"
COL_NUM_ULTIMO_INFORME = "58.NÚMERO DEL ULTIMO INFORME  DE SUPERVISION PRESENTADO"
COL_RADICADOS_ORFEO = "59.RADICADOS DE PRESENTACIÓN DE INFORMES (ORFEO)"
COL_FECHA_ULTIMO_INFORME = "60.FECHA DE RADICADO DE ÚLTIMO INFORME DE SUPERVISION PRESENTADO"
COL_FECHA_PROXIMO_INFORME = "61.FECHA ESTIMADA DE PRESENTACIÓN PRÓXIMO INFORME  DE SUPERVISION"
COL_ESTADO_INFORMES = "62.ESTADO DE PRESENTACIÓN DE INFORMES DE SUPERVISIÓN"
COL_AVANCE_FISICO_PROG = "63. PORCENTAJE DE AVANCE FÍSICO PROGRAMADO"
COL_AVANCE_FISICO_REAL = "64. PORCENTAJE DE AVANCE FÍSICO REAL"
COL_AVANCE_PRESUP_PROG = "65. PORCENTAJE AVANCE PRESUPUESTAL PROGRAMADO"
COL_AVANCE_PRESUP_REAL = "66. PORCENTAJE AVANCE PRESUPUESTAL REAL"
COL_REQUIERE_LIQUIDACION = "67.REQUIERE LIQUIDACIÓN?"
COL_FECHA_LIQUIDACION = "68. FECHA LIQUIDACIÓN"
COL_ABOGADO = "69. ABOGADO RESPONSABLE"
COL_NUM_PROCESO_ASOCIADO = "70. NÚMERO DE PROCESO ASOCIADO AL CONTRATO"
COL_LINK = "LINK"
COL_OBSERVACIONES = "72. OBSERVACIONES"
COL_VALOR_TOTAL_INGRESO = "VALOR TOTAL INGRESO"
COL_NOMBRE_SUPERVISOR_ACTUAL = "NOMBRE SUPERVISOR ACTUAL"


# ---- Categorize columns ------------------------------------------------------

INTERNAL_ONLY: frozenset[str] = frozenset({
    COL_REQUIERE_ACTA_INICIO,       # internal flag, FEAB decides
    COL_DESCRIBA_OTRA_CLASE,        # only filled when "Otra"
    COL_VECES_SIRECI,               # internal SIRECI counter
    COL_CODIGO_SECOP_SIRECI,        # observed: Dra uses UNSPSC not NTC here
    COL_ES_CONVENIO,                # internal classification
    COL_CLASE_CONVENIO,             # internal classification
    COL_RECURSOS_CONVENIO,          # internal classification
    COL_RUBRO_PRESUPUESTAL,         # internal accounting code
    COL_NO_CDP,                     # internal CDP number
    COL_FECHA_CDP,                  # internal CDP date
    COL_NO_RP,                      # internal Registro Presupuestal
    COL_FECHA_RP,                   # internal RP date
    COL_VIGENCIA_FUTURA_1,          # internal accounting
    COL_VIGENCIA_FUTURA_2,          # internal accounting
    COL_VIGENCIA_FUTURA_3,          # internal accounting
    COL_TIPO_SEGUIMIENTO,           # internal classification
    COL_INTERVENTOR,                # rarely in SECOP
    COL_SUPERVISOR_VINCULACION,     # internal HR data
    COL_DEPENDENCIA,                # internal org structure
    COL_PERIOD_INFORMES_TIPO,       # internal supervision tracking
    COL_PERIOD_INFORMES_DIAS,       # internal supervision tracking
    COL_NUM_ULTIMO_INFORME,         # internal Orfeo
    COL_RADICADOS_ORFEO,            # internal Orfeo
    COL_FECHA_ULTIMO_INFORME,       # internal Orfeo
    COL_FECHA_PROXIMO_INFORME,      # internal supervision tracking
    COL_ESTADO_INFORMES,            # internal supervision tracking
    COL_AVANCE_FISICO_PROG,         # SECOP rarely populates this
    COL_AVANCE_FISICO_REAL,         # SECOP rarely populates this
    COL_AVANCE_PRESUP_PROG,         # internal accounting
    COL_ABOGADO,                    # internal HR
    COL_OBSERVACIONES,              # Dra notes — read-only
    COL_NOMBRE_SUPERVISOR_ACTUAL,   # internal supervisor change tracking
})


# All her columns in exact order (used to validate Excel structure).
FEAB_COLUMNS_ORDERED: tuple[str, ...] = (
    COL_NUMERO_CONTRATO, COL_VIGENCIA, COL_OBJETO, COL_FECHA_SUSCRIPCION,
    COL_PLAZO, COL_REQUIERE_ACTA_INICIO, COL_FECHA_INICIO, COL_FECHA_TERMINACION,
    COL_ESTADO_CONTRATO, COL_LUGAR_EJECUCION, COL_MODALIDAD_SELECCION,
    COL_CLASE_CONTRATO, COL_DESCRIBA_OTRA_CLASE, COL_VECES_SIRECI, COL_TIPO_ORDEN,
    COL_ES_CONVENIO, COL_CLASE_CONVENIO, COL_RECURSOS_CONVENIO,
    COL_ENTIDAD_RECURSOS_NIT, COL_ENTIDAD_RECURSOS_DV, COL_ENTIDAD_RECURSOS_NOMBRE,
    COL_FUENTE_RECURSOS, COL_RUBRO_PRESUPUESTAL, COL_NO_CDP, COL_FECHA_CDP,
    COL_NO_RP, COL_FECHA_RP, COL_CODIGO_SECOP_SIRECI,
    COL_VALOR_INICIAL, COL_VALOR_INICIAL_VIGENCIA_ACTUAL,
    COL_VIGENCIA_FUTURA_1, COL_VIGENCIA_FUTURA_2, COL_VIGENCIA_FUTURA_3,
    COL_TIPO_ANTICIPOS, COL_VALOR_ANTICIPOS,
    COL_TIPO_ADICIONES, COL_REDUCCIONES, COL_ADICIONES, COL_VALOR_TOTAL,
    COL_PRORROGAS_DIAS, COL_CONTRATISTA_NATURALEZA, COL_CONSORCIO,
    COL_CONTRATISTA_TIPO_ID, COL_CONTRATISTA_NUM_ID, COL_CONTRATISTA_DV,
    COL_CONTRATISTA_NOMBRE, COL_CONTRATISTA_DIRECCION, COL_CONTRATISTA_TELEFONO,
    COL_CONTRATISTA_CORREO, COL_GARANTIA_TIPO, COL_GARANTIA_RIESGOS,
    COL_GARANTIA_FECHA_EXPED, COL_TIPO_SEGUIMIENTO, COL_INTERVENTOR,
    COL_SUPERVISOR_ID, COL_SUPERVISOR_NOMBRE, COL_SUPERVISOR_VINCULACION,
    COL_DEPENDENCIA, COL_PERIOD_INFORMES_TIPO, COL_PERIOD_INFORMES_DIAS,
    COL_NUM_ULTIMO_INFORME, COL_RADICADOS_ORFEO, COL_FECHA_ULTIMO_INFORME,
    COL_FECHA_PROXIMO_INFORME, COL_ESTADO_INFORMES,
    COL_AVANCE_FISICO_PROG, COL_AVANCE_FISICO_REAL,
    COL_AVANCE_PRESUP_PROG, COL_AVANCE_PRESUP_REAL,
    COL_REQUIERE_LIQUIDACION, COL_FECHA_LIQUIDACION, COL_ABOGADO,
    COL_NUM_PROCESO_ASOCIADO, COL_LINK, COL_OBSERVACIONES,
    COL_VALOR_TOTAL_INGRESO, COL_NOMBRE_SUPERVISOR_ACTUAL,
)


# ---- Helpers -----------------------------------------------------------------

def nit_dv(nit: str | int | None) -> str:
    """Compute the Colombian DIAN check digit for a NIT.

    Delegates to ``python-stdnum.co.nit`` (the DIAN-aligned reference
    implementation) so we never drift from official Colombian rules.
    Falls back to "" for empty/invalid input — the cell stays clean
    instead of holding a wrong value.
    """
    if nit is None:
        return ""
    s = str(nit).strip().replace("-", "").replace(".", "").replace(" ", "")
    if not s.isdigit() or len(s) < 6:
        return ""
    try:
        # python-stdnum is the DIAN-canonical algorithm.
        from stdnum.co import nit as _co_nit
        return _co_nit.calc_check_digit(s)
    except Exception:
        return ""


def _date(value: Any) -> str:
    """Return YYYY-MM-DD or empty."""
    if not value:
        return ""
    return str(value)[:10]


def _flatten_url(value: Any) -> str:
    """SECOP returns URL fields as dicts ``{'url': '...'}``. Flatten to string."""
    if value is None:
        return ""
    if isinstance(value, dict):
        return str(value.get("url") or "").strip()
    return str(value).strip()


def _year(value: Any) -> str:
    """Extract the year from a date-ish value."""
    d = _date(value)
    if len(d) >= 4 and d[:4].isdigit():
        return d[:4]
    return ""


def _money(value: Any) -> Decimal | str:
    """Convert a SECOP money value to Decimal — never float.

    Float can introduce IEEE 754 rounding errors that turn $62832000
    into $62832000.000001 — unacceptable in compliance. Decimal keeps
    arbitrary precision so what SECOP says is what we write.
    """
    if value is None or value == "":
        return ""
    try:
        s = str(value).replace(",", "").replace("$", "").strip()
        if not s:
            return ""
        return Decimal(s)
    except (InvalidOperation, ValueError, TypeError):
        return ""


def _num(value: Any) -> int | float | str:
    """Numeric value for non-money fields (counts, percentages)."""
    if value is None or value == "":
        return ""
    try:
        n = float(str(value).replace(",", ""))
        return int(n) if n.is_integer() else n
    except (ValueError, TypeError):
        return ""


def _sum_money(values) -> Decimal | str:
    """Sum monetary values using Decimal arithmetic."""
    total = Decimal("0")
    found = False
    for v in values:
        d = _money(v)
        if isinstance(d, Decimal):
            total += d
            found = True
    if not found:
        return ""
    return total


def _money_to_excel(value: Any) -> int | float | str:
    """Convert Decimal back to int/float for Excel cell write."""
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    return value


def _sum_num(values) -> int | float | str:
    total = 0.0
    found = False
    for v in values:
        n = _num(v)
        if n != "":
            total += float(n)
            found = True
    if not found:
        return ""
    return int(total) if total.is_integer() else round(total, 2)


def _join_unique(values, sep: str = " | ") -> str:
    seen: list[str] = []
    for v in values:
        if v in (None, "", "No definido", "No Definido", "No Definida"):
            continue
        s = str(v).strip()
        if s and s not in seen:
            seen.append(s)
    return sep.join(seen)


def _naturaleza_from_doc(tipodoc: str | None) -> str:
    """Map SECOP tipodocproveedor -> "Natural" / "Jurídica"."""
    if not tipodoc:
        return ""
    t = str(tipodoc).strip().upper()
    if t in {"NIT"}:
        return "Jurídica"
    if t in {"CC", "C.C.", "CÉDULA DE CIUDADANÍA", "CEDULA DE CIUDADANIA",
             "CE", "C.E.", "PASAPORTE", "PA"}:
        return "Natural"
    return ""


def _consorcio_from_proveedor(proveedor: str | None) -> str:
    """Heuristic: name contains 'CONSORCIO' or 'UNION TEMPORAL'."""
    if not proveedor:
        return ""
    s = str(proveedor).upper()
    if "CONSORCIO" in s:
        return "Consorcio"
    if "UNION TEMPORAL" in s or "UNIÓN TEMPORAL" in s or "U.T." in s:
        return "Unión Temporal"
    return "No"


def _liquidacion_flag(liq: Any) -> str:
    """Normalize liquidacion field to Sí/No."""
    if liq is None or liq == "":
        return ""
    s = str(liq).strip().lower()
    if s in {"si", "sí", "true", "1"}:
        return "Sí"
    if s in {"no", "false", "0"}:
        return "No"
    return str(liq)


# ---- Main computation --------------------------------------------------------

@dataclass
class FillResult:
    """What the filler computed for one row."""
    values: dict[str, Any]                  # column_name -> value (only fillable ones)
    confidence: dict[str, str]              # column_name -> HIGH/MEDIUM/LOW
    sources: dict[str, str]                 # column_name -> human-readable provenance


def compute_feab_fill(
    *,
    proceso: dict | None,
    contratos: list[dict],
    notice_uid: str | None,
    source_url: str | None,
    adiciones_by_contrato: dict[str, list[dict]] | None = None,
    garantias_by_contrato: dict[str, list[dict]] | None = None,
    ejecucion_by_contrato: dict[str, list[dict]] | None = None,
) -> FillResult:
    """Map all available SECOP data to the Dra.'s 77 columns.

    Returns only columns that can be derived. Empty values aren't included
    so the filler can decide whether to leave the cell alone.
    """
    proceso = proceso or {}
    contratos = contratos or []
    adiciones_by_contrato = adiciones_by_contrato or {}
    garantias_by_contrato = garantias_by_contrato or {}
    ejecucion_by_contrato = ejecucion_by_contrato or {}

    out: dict[str, Any] = {}
    conf: dict[str, str] = {}
    src: dict[str, str] = {}

    def put(col: str, value: Any, confidence: str, source: str) -> None:
        # Reject empty AND SECOP "No Definido" placeholder. A placeholder
        # is not data — propagating it would be a false positive that
        # makes the cell look populated when it isn't.
        if value in (None, "", []):
            return
        if isinstance(value, str) and value.strip().lower() in {
            "no definido", "no definida", "no aplica", "n/a",
            "sin descripcion", "sin descripción",
        }:
            return
        out[col] = value
        conf[col] = confidence
        src[col] = source

    # --- Columns that come from the PROCESO (always present, even when no contract) ---

    put(COL_NUM_PROCESO_ASOCIADO, notice_uid or proceso.get("id_del_proceso"),
        "HIGH", "proceso.id_del_proceso")
    put(COL_LINK, _flatten_url(proceso.get("urlproceso")) or source_url,
        "HIGH", "proceso.urlproceso")
    put(COL_MODALIDAD_SELECCION, proceso.get("modalidad_de_contratacion"),
        "HIGH", "proceso.modalidad_de_contratacion")
    put(COL_TIPO_ORDEN, proceso.get("ordenentidad"),
        "HIGH", "proceso.ordenentidad")
    put(COL_OBJETO, proceso.get("descripci_n_del_procedimiento"),
        "HIGH", "proceso.descripci_n_del_procedimiento")

    # CÓDIGO SECOP SIRECI is INTENTIONALLY NOT FILLED. Observed FEAB use:
    # the Dra. types the UNSPSC category code (e.g. 80131500) here, not
    # the SECOP II NTC. Filling it from id_del_proceso would generate
    # false positives because the two codes mean different things.

    # --- Columns from the CONTRATOS (when adjudicated) ---

    if not contratos:
        # Process exists but no contract yet — that's all we can derive.
        return FillResult(values=out, confidence=conf, sources=src)

    # Multi-contract processes: prefer the most recent firmed one as the
    # "main" contract for single-value cells (NÚMERO, FECHA SUSCRIPCIÓN
    # etc.) and aggregate amounts across all of them.
    contratos_sorted = sorted(
        contratos,
        key=lambda c: (c.get("fecha_de_firma") or ""),
        reverse=True,
    )
    main = contratos_sorted[0]

    # 2. NÚMERO DE CONTRATO — referencia is the FEAB-readable label
    # (CONTRATO-FEAB-0006-2023); id_contrato is the SECOP UUID. Prefer
    # the human one and fall back.
    numero = main.get("referencia_del_contrato") or main.get("id_contrato")
    if len(contratos_sorted) > 1:
        # Multiple contracts — show all references joined.
        all_refs = _join_unique(c.get("referencia_del_contrato") or c.get("id_contrato")
                                for c in contratos_sorted)
        numero = all_refs or numero
    put(COL_NUMERO_CONTRATO, numero, "HIGH", "contrato.referencia_del_contrato")

    # 3. VIGENCIA (year of fecha_de_firma)
    put(COL_VIGENCIA, _year(main.get("fecha_de_firma")),
        "HIGH", "year(contrato.fecha_de_firma)")

    # 4. OBJETO — contract objeto is more specific than proceso descripción
    objeto = main.get("objeto_del_contrato")
    if objeto:
        out[COL_OBJETO] = objeto
        conf[COL_OBJETO] = "HIGH"
        src[COL_OBJETO] = "contrato.objeto_del_contrato"

    put(COL_FECHA_SUSCRIPCION, _date(main.get("fecha_de_firma")),
        "HIGH", "contrato.fecha_de_firma")
    put(COL_PLAZO, main.get("duraci_n_del_contrato"),
        "HIGH", "contrato.duraci_n_del_contrato")
    put(COL_FECHA_INICIO, _date(main.get("fecha_de_inicio_del_contrato")),
        "HIGH", "contrato.fecha_de_inicio_del_contrato")
    put(COL_FECHA_TERMINACION, _date(main.get("fecha_de_fin_del_contrato")),
        "HIGH", "contrato.fecha_de_fin_del_contrato")

    # Estado: if multiple contracts, join. If any "En ejecución" wins.
    estados = sorted({c.get("estado_contrato") or "" for c in contratos_sorted
                     if c.get("estado_contrato")})
    if estados:
        put(COL_ESTADO_CONTRATO, " | ".join(estados),
            "HIGH", "contrato.estado_contrato")

    # 11. LUGAR DE EJECUCIÓN: localizaci_n is "Colombia, Bogotá, Bogotá"
    # — clean it up
    loc = main.get("localizaci_n") or main.get("ciudad") or ""
    if loc:
        put(COL_LUGAR_EJECUCION, loc, "HIGH", "contrato.localizaci_n")

    # 12 already filled from proceso, but contrato.modalidad is more specific
    contrato_modalidad = main.get("modalidad_de_contratacion")
    if contrato_modalidad:
        out[COL_MODALIDAD_SELECCION] = contrato_modalidad
        conf[COL_MODALIDAD_SELECCION] = "HIGH"
        src[COL_MODALIDAD_SELECCION] = "contrato.modalidad_de_contratacion"

    # 13. CLASE DE CONTRATO
    put(COL_CLASE_CONTRATO, main.get("tipo_de_contrato"),
        "HIGH", "contrato.tipo_de_contrato")

    # 16. TIPO DE ORDEN — contract has 'orden' = "Nacional"/"Territorial"
    contrato_orden = main.get("orden")
    if contrato_orden:
        out[COL_TIPO_ORDEN] = contrato_orden
        conf[COL_TIPO_ORDEN] = "HIGH"
        src[COL_TIPO_ORDEN] = "contrato.orden"

    # 20-22. ENTIDAD DE DONDE PROVIENEN LOS RECURSOS — for FEAB self-funded
    # this is FEAB itself (NIT 901148337). When recursos are external, the
    # cell may differ. Default = FEAB unless we can detect otherwise.
    entidad_nit = main.get("nit_entidad")
    entidad_nombre = main.get("nombre_entidad")
    if entidad_nit:
        put(COL_ENTIDAD_RECURSOS_NIT, str(entidad_nit), "MEDIUM",
            "contrato.nit_entidad (assumes self-funded)")
        put(COL_ENTIDAD_RECURSOS_DV, nit_dv(entidad_nit), "HIGH",
            "computed DV (DIAN algorithm)")
    if entidad_nombre:
        put(COL_ENTIDAD_RECURSOS_NOMBRE, entidad_nombre, "MEDIUM",
            "contrato.nombre_entidad (assumes self-funded)")

    # 23. FUENTE DE RECURSOS
    put(COL_FUENTE_RECURSOS, main.get("origen_de_los_recursos"),
        "HIGH", "contrato.origen_de_los_recursos")

    # 28-29. VALOR INICIAL — contracts in Colombia don't separate vigencias
    # in this dataset; we mirror the same value to both. Use Decimal
    # to avoid IEEE 754 rounding (compliance requirement).
    valor_inicial_d = _sum_money(c.get("valor_del_contrato") for c in contratos_sorted)
    if valor_inicial_d != "":
        put(COL_VALOR_INICIAL, _money_to_excel(valor_inicial_d), "HIGH",
            "sum(contrato.valor_del_contrato) [Decimal]")
        put(COL_VALOR_INICIAL_VIGENCIA_ACTUAL, _money_to_excel(valor_inicial_d), "MEDIUM",
            "sum(contrato.valor_del_contrato) [Decimal] (same as 28)")

    # 33-34. ANTICIPOS — derive from habilita_pago_adelantado / valor_de_pago_adelantado
    anticipo_flag = main.get("habilita_pago_adelantado") or ""
    if str(anticipo_flag).strip().lower() in {"si", "sí"}:
        put(COL_TIPO_ANTICIPOS, "Pago anticipado", "MEDIUM",
            "contrato.habilita_pago_adelantado=Si")
        valor_ant_d = _sum_money(c.get("valor_de_pago_adelantado") for c in contratos_sorted)
        if valor_ant_d != "":
            put(COL_VALOR_ANTICIPOS, _money_to_excel(valor_ant_d), "HIGH",
                "sum(contrato.valor_de_pago_adelantado) [Decimal]")
    elif str(anticipo_flag).strip().lower() == "no":
        put(COL_TIPO_ANTICIPOS, "Sin anticipo", "MEDIUM",
            "contrato.habilita_pago_adelantado=No")

    # 35A. ADICIONES / REDUCCIONES — sum positive vs negative adiciones
    # using Decimal arithmetic so peso-cents don't drift.
    add_total = Decimal("0")
    red_total = Decimal("0")
    add_tipos: list[str] = []
    for c in contratos_sorted:
        cid = c.get("id_contrato")
        if not cid:
            continue
        for a in adiciones_by_contrato.get(cid, []):
            valor_d = _money(a.get("valor"))
            if not isinstance(valor_d, Decimal):
                continue
            if valor_d > 0:
                add_total += valor_d
            else:
                red_total += abs(valor_d)
            tipo = a.get("tipo") or a.get("tipo_modificacion") or "Adición"
            if tipo and tipo not in add_tipos:
                add_tipos.append(tipo)
    if add_total > 0:
        put(COL_ADICIONES, _money_to_excel(add_total),
            "HIGH", "sum(adiciones.valor>0) [Decimal]")
    if red_total > 0:
        put(COL_REDUCCIONES, _money_to_excel(red_total),
            "HIGH", "sum(adiciones.valor<0) [Decimal]")
    if add_tipos:
        put(COL_TIPO_ADICIONES, " | ".join(add_tipos), "MEDIUM",
            "adiciones.tipo")

    # 36. VALOR TOTAL = valor inicial + adiciones - reducciones (Decimal)
    if valor_inicial_d != "":
        valor_total_d = valor_inicial_d + add_total - red_total
        put(COL_VALOR_TOTAL, _money_to_excel(valor_total_d), "HIGH",
            "valor_inicial + adiciones - reducciones [Decimal]")

    # 37. PRÓRROGAS DÍAS = sum of dias_adicionados across contratos
    prorrogas = _sum_num(c.get("dias_adicionados") for c in contratos_sorted)
    if prorrogas != "" and prorrogas != 0:
        put(COL_PRORROGAS_DIAS, prorrogas, "HIGH", "sum(contrato.dias_adicionados)")

    # 38-46. CONTRATISTA
    naturaleza = _naturaleza_from_doc(main.get("tipodocproveedor"))
    if naturaleza:
        put(COL_CONTRATISTA_NATURALEZA, naturaleza, "MEDIUM",
            "inferred from contrato.tipodocproveedor")

    consorcio = _consorcio_from_proveedor(main.get("proveedor_adjudicado"))
    if consorcio:
        put(COL_CONSORCIO, consorcio, "LOW",
            "inferred from contrato.proveedor_adjudicado name")

    put(COL_CONTRATISTA_TIPO_ID, main.get("tipodocproveedor"),
        "HIGH", "contrato.tipodocproveedor")
    put(COL_CONTRATISTA_NUM_ID, main.get("documento_proveedor"),
        "HIGH", "contrato.documento_proveedor")

    # 42. DV NIT — only for NIT, not for CC
    if (main.get("tipodocproveedor") or "").strip().upper() == "NIT":
        put(COL_CONTRATISTA_DV, nit_dv(main.get("documento_proveedor")),
            "HIGH", "computed DV (DIAN algorithm)")

    put(COL_CONTRATISTA_NOMBRE, main.get("proveedor_adjudicado"),
        "HIGH", "contrato.proveedor_adjudicado")

    # 44. DIRECCIÓN: domicilio_representante_legal is the rep's address —
    # same as contractor's in most SECOP records. Use with MEDIUM confidence.
    domicilio = main.get("domicilio_representante_legal")
    if domicilio and domicilio.lower() != "sin descripcion":
        put(COL_CONTRATISTA_DIRECCION, domicilio, "MEDIUM",
            "contrato.domicilio_representante_legal")

    # 47-49. GARANTÍAS
    all_polizas: list[dict] = []
    for c in contratos_sorted:
        cid = c.get("id_contrato")
        if cid:
            all_polizas.extend(garantias_by_contrato.get(cid, []))
    if all_polizas:
        tipos = _join_unique(p.get("tipopoliza") for p in all_polizas)
        if tipos:
            put(COL_GARANTIA_TIPO, tipos, "HIGH", "garantias.tipopoliza")
        riesgos = _join_unique(p.get("riesgoasegurado") for p in all_polizas)
        if riesgos:
            put(COL_GARANTIA_RIESGOS, riesgos, "HIGH",
                "garantias.riesgoasegurado")
        fechas_exp = [p.get("fechaexpedicionpoliza") for p in all_polizas
                     if p.get("fechaexpedicionpoliza")]
        if fechas_exp:
            put(COL_GARANTIA_FECHA_EXPED, _date(min(fechas_exp)),
                "HIGH", "min(garantias.fechaexpedicionpoliza)")

    # 52-53. SUPERVISOR
    sup_id = main.get("n_mero_de_documento_supervisor")
    if sup_id and str(sup_id).lower() != "no definido":
        put(COL_SUPERVISOR_ID, sup_id, "HIGH",
            "contrato.n_mero_de_documento_supervisor")
    sup_nombre = main.get("nombre_supervisor")
    if sup_nombre and str(sup_nombre).lower() != "no definido":
        put(COL_SUPERVISOR_NOMBRE, sup_nombre, "HIGH",
            "contrato.nombre_supervisor")

    # 64. AVANCE FÍSICO REAL — from ejecucion data when available
    real_pcts: list[float] = []
    for c in contratos_sorted:
        cid = c.get("id_contrato")
        if cid:
            for e in ejecucion_by_contrato.get(cid, []):
                v = _num(e.get("porcentaje_de_avance_real"))
                if v != "":
                    real_pcts.append(float(v))
    if real_pcts:
        put(COL_AVANCE_FISICO_REAL, max(real_pcts), "HIGH",
            "max(ejecucion.porcentaje_de_avance_real)")

    # 66. AVANCE PRESUPUESTAL REAL = valor_pagado / valor_total (Decimal,
    # then 2-decimal percentage for display).
    valor_pagado_d = _sum_money(c.get("valor_pagado") for c in contratos_sorted)
    if (isinstance(valor_pagado_d, Decimal) and isinstance(valor_inicial_d, Decimal)
            and valor_inicial_d > 0):
        denom = valor_inicial_d + add_total - red_total
        if denom > 0:
            pct = (Decimal("100") * valor_pagado_d / denom).quantize(Decimal("0.01"))
            put(COL_AVANCE_PRESUP_REAL, float(pct), "HIGH",
                "100 * sum(valor_pagado) / valor_total [Decimal]")

    # 67. REQUIERE LIQUIDACIÓN
    liq = _liquidacion_flag(main.get("liquidaci_n"))
    if liq:
        put(COL_REQUIERE_LIQUIDACION, liq, "HIGH", "contrato.liquidaci_n")

    # 68. FECHA LIQUIDACIÓN
    put(COL_FECHA_LIQUIDACION, _date(main.get("fecha_fin_liquidacion")),
        "HIGH", "contrato.fecha_fin_liquidacion")

    # VALOR TOTAL INGRESO — when the contract is enajenación (sale of
    # FEAB-managed property) the contract value IS income. Use same as
    # COL_VALOR_TOTAL with LOW confidence (the FEAB team may interpret
    # this differently — leave room for manual override).
    objeto_lower = (objeto or "").lower()
    if "enajenaci" in objeto_lower or "venta" in objeto_lower:
        if COL_VALOR_TOTAL in out:
            put(COL_VALOR_TOTAL_INGRESO, out[COL_VALOR_TOTAL], "LOW",
                "inferred: enajenación contract -> ingreso = valor total")

    return FillResult(values=out, confidence=conf, sources=src)


def source_fingerprint(
    *,
    proceso: dict | None,
    contratos: list[dict],
    notice_uid: str | None,
) -> str:
    """SHA-256 hash of the SECOP raw payload for this process.

    Lets the Dra. prove "this is what SECOP returned on day X" — useful
    if she has to defend a value in compliance/audit. The hash changes
    only when SECOP itself changes, never from our derivations.
    """
    payload = {
        "notice_uid": notice_uid,
        "proceso": proceso,
        "contratos": contratos,
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


__all__ = [
    # Column-name constants (exported so other modules can reference them)
    "COL_NUMERO_CONTRATO", "COL_VIGENCIA", "COL_OBJETO", "COL_FECHA_SUSCRIPCION",
    "COL_PLAZO", "COL_FECHA_INICIO", "COL_FECHA_TERMINACION", "COL_ESTADO_CONTRATO",
    "COL_LUGAR_EJECUCION", "COL_MODALIDAD_SELECCION", "COL_CLASE_CONTRATO",
    "COL_TIPO_ORDEN", "COL_ENTIDAD_RECURSOS_NIT", "COL_ENTIDAD_RECURSOS_DV",
    "COL_ENTIDAD_RECURSOS_NOMBRE", "COL_FUENTE_RECURSOS", "COL_CODIGO_SECOP_SIRECI",
    "COL_VALOR_INICIAL", "COL_VALOR_INICIAL_VIGENCIA_ACTUAL", "COL_TIPO_ANTICIPOS",
    "COL_VALOR_ANTICIPOS", "COL_TIPO_ADICIONES", "COL_REDUCCIONES", "COL_ADICIONES",
    "COL_VALOR_TOTAL", "COL_PRORROGAS_DIAS", "COL_CONTRATISTA_NATURALEZA",
    "COL_CONSORCIO", "COL_CONTRATISTA_TIPO_ID", "COL_CONTRATISTA_NUM_ID",
    "COL_CONTRATISTA_DV", "COL_CONTRATISTA_NOMBRE", "COL_CONTRATISTA_DIRECCION",
    "COL_GARANTIA_TIPO", "COL_GARANTIA_RIESGOS", "COL_GARANTIA_FECHA_EXPED",
    "COL_SUPERVISOR_ID", "COL_SUPERVISOR_NOMBRE", "COL_AVANCE_FISICO_REAL",
    "COL_AVANCE_PRESUP_REAL", "COL_REQUIERE_LIQUIDACION", "COL_FECHA_LIQUIDACION",
    "COL_NUM_PROCESO_ASOCIADO", "COL_LINK", "COL_VALOR_TOTAL_INGRESO",
    "INTERNAL_ONLY", "FEAB_COLUMNS_ORDERED",
    "FillResult", "compute_feab_fill", "nit_dv",
]
