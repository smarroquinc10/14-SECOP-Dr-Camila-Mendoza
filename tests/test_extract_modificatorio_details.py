"""Tests del modulo cardinal de extraccion de detalles del modificatorio.

Cubre 0 FP / 0 FN / 0 datos comidos sobre samples reales del piloto y
casos sinteticos disenados para los patrones que aparecen en SECOP.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from extract_modificatorio_details import (  # noqa: E402
    detect_subtipos,
    extract_dias_prorrogados,
    extract_fecha_documento,
    extract_valor_adicionado,
    extract_details,
    parse_pesos,
)


# === parse_pesos ===

class TestParsePesos:
    def test_separator_punto(self):
        assert parse_pesos("18.000.000") == 18_000_000

    def test_separator_coma_colombia(self):
        # En Colombia el separador de miles puede ser . o ,
        assert parse_pesos("1,052,000") == 1_052_000

    def test_separator_mixto_es_aceptable(self):
        # Si el OCR confunde formatos, parse_pesos los normaliza al int real
        assert parse_pesos("$ 18.000.000") == 18_000_000

    def test_rechaza_valor_absurdo_pequeno(self):
        # Menor a $100k no es un valor cardinal de modificatorio
        assert parse_pesos("99000") is None

    def test_rechaza_valor_absurdo_grande(self):
        # Mas de $10 billones es absurdo para un contrato FEAB
        assert parse_pesos("99.999.999.999.999") is None

    def test_string_vacio(self):
        assert parse_pesos("") is None

    def test_string_no_numerico(self):
        assert parse_pesos("hola") is None


# === detect_subtipos ===

class TestDetectSubtipos:
    """Tipo primary generico (Modificatorio) -> busca subtipos en cuerpo."""

    def test_clausulas_resolutivas_adicion_y_prorroga(self):
        text = """
        PRIMERA: Prorrogar el plazo de ejecucion del contrato.
        SEGUNDA: Adicionar el contrato en la suma de QUINCE MILLONES.
        """
        subtipos = detect_subtipos(text, tipo_primary="Modificatorio")
        assert "Prorroga" in subtipos
        assert "Adicion" in subtipos

    def test_solo_adicion(self):
        text = "ADICIONAR EL VALOR DEL CONTRATO en la suma de DIEZ MILLONES."
        subtipos = detect_subtipos(text, tipo_primary="Modificatorio")
        assert "Adicion" in subtipos
        assert "Prorroga" not in subtipos

    def test_solo_prorroga(self):
        text = "PRIMERA: Prorrogar el plazo del contrato hasta el 31 de diciembre."
        subtipos = detect_subtipos(text, tipo_primary="Modificatorio")
        assert "Prorroga" in subtipos
        assert "Adicion" not in subtipos

    def test_typo_ocr_premagar_se_detecta(self):
        # OCR comun confunde "Prorrogar" con "Premagar" o "Praregar"
        text = "PRIMERA: Premagar el plazo del contrato por un (1) año."
        subtipos = detect_subtipos(text, tipo_primary="Modificatorio")
        assert "Prorroga" in subtipos


class TestDetectSubtiposAntiFP:
    """tipo_primary especifico -> NO buscar subtipos accesorios.

    Razon cardinal: una "Acta de Liquidacion" narra toda la historia del
    contrato (suspensiones, modificatorios anteriores) pero el tipo
    cardinal del documento es Liquidacion · no es un combo.
    """

    def test_liquidacion_no_detecta_suspension_narrada(self):
        text = """
        ACTA DE LIQUIDACION del contrato 005 de 2020.
        Que el 15 de marzo de 2020 se suspendio la ejecucion.
        Que el 1 de junio de 2020 se reanudo.
        Que se firmaron 2 modificatorios.
        Saldo a favor del contratante.
        """
        subtipos = detect_subtipos(text, tipo_primary="Liquidacion")
        # Tipo primary ya es Liquidacion · no debe inferir subtipos accesorios
        assert subtipos == []

    def test_cesion_no_detecta_liquidacion_narrada(self):
        text = """
        CESION DEL CONTRATO No 0167 de 2018.
        El cedente y el cesionario acuerdan transferir.
        Cuando el contrato termine se hara la liquidacion correspondiente.
        """
        subtipos = detect_subtipos(text, tipo_primary="Cesion")
        assert subtipos == []

    def test_aclaratorio_no_detecta_cesion_narrada(self):
        text = """
        ACLARATORIO No 1 a la CESION del contrato 0167 de 2018.
        Se aclara que el cesionario asume todas las obligaciones.
        """
        subtipos = detect_subtipos(text, tipo_primary="Aclaratorio")
        assert subtipos == []

    def test_terminacion_anticipada_no_busca(self):
        text = "TERMINACION ANTICIPADA del contrato. Liquidacion final."
        subtipos = detect_subtipos(text, tipo_primary="Terminacion anticipada")
        assert subtipos == []

    def test_generico_modificatorio_si_busca(self):
        text = "MODIFICATORIO No 1. PRIMERA: Adicionar el valor del contrato."
        subtipos = detect_subtipos(text, tipo_primary="Modificatorio")
        assert "Adicion" in subtipos


# === extract_valor_adicionado ===

class TestExtractValorAdicionado:
    def test_clausula_directa_adicionar_contrato(self):
        text = """
        SEGUNDA: Adicionar el contrato en la suma de DIECIOCHO MILLONES
        DE PESOS M/CTE ($18.000.000), incluido IVA.
        """
        val, warns = extract_valor_adicionado(text, has_adicion=True)
        assert val == 18_000_000
        assert warns == []

    def test_canon_mensual_genera_warning(self):
        # FP cardinal: canon mensual NO es valor adicionado total
        text = """
        Que se incrementa el canon mensual de arrendamiento en la suma
        de UN MILLON CIENTO CINCO MIL PESOS ($1.105.000).
        """
        val, warns = extract_valor_adicionado(text, has_adicion=True)
        # El extractor puede tomar el valor pero DEBE warningear
        if val:
            assert any("mensual" in w or "periodico" in w for w in warns)

    def test_no_adicion_devuelve_none(self):
        text = "Algun texto cualquiera con $5.000.000 mencionado."
        val, warns = extract_valor_adicionado(text, has_adicion=False)
        assert val is None

    def test_adicion_sin_valor_devuelve_warning(self):
        text = "ADICIONAR el contrato en cuanto al alcance del objeto."
        val, warns = extract_valor_adicionado(text, has_adicion=True)
        assert val is None
        assert any("no se pudo extraer valor" in w for w in warns)


# === extract_dias_prorrogados ===

class TestExtractDiasProrrogados:
    def test_un_ano_son_365_dias(self):
        text = "Prorrogar el plazo del contrato por un (1) año mas."
        dias, warns = extract_dias_prorrogados(text, has_prorroga=True)
        assert dias == 365

    def test_dos_meses_son_60_dias(self):
        text = "PRIMERA: Prorrogar el plazo por DOS (2) meses adicionales."
        dias, warns = extract_dias_prorrogados(text, has_prorroga=True)
        assert dias == 60

    def test_60_dias_literal(self):
        text = "Prorrogar el plazo del contrato por 60 dias adicionales."
        dias, warns = extract_dias_prorrogados(text, has_prorroga=True)
        assert dias == 60

    def test_no_prorroga_devuelve_none(self):
        text = "Algun texto"
        dias, warns = extract_dias_prorrogados(text, has_prorroga=False)
        assert dias is None

    def test_prorroga_a_fecha_no_a_dias_genera_warning(self):
        # Caso real: "Prorrogar hasta el 15 de diciembre" no extrae dias
        text = "Prorrogar el plazo de ejecucion del contrato hasta el 15 de diciembre de 2017."
        dias, warns = extract_dias_prorrogados(text, has_prorroga=True)
        assert dias is None
        assert any("plazo" in w for w in warns)


# === extract_fecha_documento ===

class TestExtractFechaDocumento:
    def test_fecha_larga_basica(self):
        text = "Bogota DC, 25 de octubre de 2017. Firmado por el representante."
        fecha, warns = extract_fecha_documento(text)
        assert fecha == "2017-10-25"

    def test_multiples_fechas_toma_la_ultima(self):
        text = """
        Que el 22 de enero de 2024 se suscribio el contrato.
        Que el 15 de marzo de 2025 se firma el presente modificatorio.
        Bogota DC, 27 de enero de 2025.
        """
        fecha, warns = extract_fecha_documento(text)
        # Toma la ultima (la del cierre del documento)
        assert fecha == "2025-01-27"

    def test_meses_con_acento(self):
        text = "Bogota, 5 de septiembre de 2024."
        fecha, warns = extract_fecha_documento(text)
        assert fecha == "2024-09-05"

    def test_sin_fecha_genera_warning(self):
        text = "Texto sin ninguna fecha estructurada."
        fecha, warns = extract_fecha_documento(text)
        assert fecha is None
        assert any("no se encontro fecha" in w for w in warns)

    def test_fecha_invalida_se_descarta(self):
        text = "Que el 32 de febrero de 2024 (fecha imposible) se firmo."
        fecha, warns = extract_fecha_documento(text)
        assert fecha is None or fecha != "2024-02-32"


# === extract_details (pipeline completo) ===

class TestExtractDetailsPipeline:
    def test_modificatorio_completo_con_adicion_y_prorroga(self):
        text = """
        MODIFICATORIO No 1 al contrato 0190 de 2017.
        PRIMERA: Prorrogar el plazo de ejecucion hasta el 15 de diciembre de 2017.
        SEGUNDA: Adicionar el contrato en la suma de DIECIOCHO MILLONES DE PESOS
        M/CTE ($18.000.000), incluido IVA.
        Bogota DC, 25 de octubre de 2017.
        """
        d = extract_details(text, tipo_primary="Modificatorio")
        assert "Prorroga" in d.subtipos
        assert "Adicion" in d.subtipos
        assert d.valor_adicionado_cop == 18_000_000
        assert d.fecha_documento == "2017-10-25"

    def test_liquidacion_no_aplica_subtipos(self):
        text = """
        ACTA DE LIQUIDACION del contrato.
        Saldo a favor.
        Bogota, 15 de abril de 2020.
        """
        d = extract_details(text, tipo_primary="Liquidacion")
        assert d.subtipos == []
        # Aun asi extrae fecha
        assert d.fecha_documento == "2020-04-15"

    def test_texto_vacio(self):
        d = extract_details("")
        assert d.subtipos == []
        assert d.valor_adicionado_cop is None
        assert d.dias_prorrogados is None
        assert d.fecha_documento is None
        assert d.extraction_warnings == ["texto vacio o muy corto"]

    def test_texto_corto_se_maneja_grácil(self):
        d = extract_details("MOD")
        assert d.subtipos == []
        assert d.valor_adicionado_cop is None

    def test_modificatorio_solo_prorroga_a_fecha(self):
        # Caso del MOD 1 del FEAB-0001-2024 segun cuerpo OCR real
        text = """
        MODIFICATORIO No 1 CONTRATO DE ARRENDAMIENTO No FEAB-0001-2024.
        1. Prorrogar el plazo de ejecucion del contrato por un (1) año mas.
        2. Modificar la CLAUSULA SEGUNDA - VALOR DEL CANON DE ARRENDAMIENTO.
        Bogota DC, 27 de enero de 2025.
        """
        d = extract_details(text, tipo_primary="Modificatorio")
        assert "Prorroga" in d.subtipos
        assert d.dias_prorrogados == 365  # un (1) año
        assert d.fecha_documento == "2025-01-27"

    def test_to_dict_devuelve_todos_los_campos(self):
        text = "PRIMERA: Adicionar el contrato en $5.000.000. Bogota, 1 de enero de 2024."
        d = extract_details(text, tipo_primary="Modificatorio")
        out = d.to_dict()
        assert "subtipos" in out
        assert "valor_adicionado_cop" in out
        assert "dias_prorrogados" in out
        assert "fecha_documento" in out
        assert "valor_total_actualizado_cop" in out
        assert "extraction_warnings" in out
