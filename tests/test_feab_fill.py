"""Tests for the FEAB filler — the heart of the no-false-positives layer."""
from __future__ import annotations

from decimal import Decimal

import pytest

from secop_ii.feab_columns import (
    COL_ADICIONES,
    COL_CONTRATISTA_DV,
    COL_CONTRATISTA_NOMBRE,
    COL_CONTRATISTA_NUM_ID,
    COL_CONTRATISTA_TIPO_ID,
    COL_ENTIDAD_RECURSOS_DV,
    COL_ENTIDAD_RECURSOS_NIT,
    COL_FECHA_INICIO,
    COL_FECHA_SUSCRIPCION,
    COL_FECHA_TERMINACION,
    COL_LINK,
    COL_NUMERO_CONTRATO,
    COL_PRORROGAS_DIAS,
    COL_REDUCCIONES,
    COL_VALOR_INICIAL,
    COL_VALOR_TOTAL,
    INTERNAL_ONLY,
    compute_feab_fill,
    nit_dv,
    source_fingerprint,
)
from secop_ii.feab_validation import validate_fills
from secop_ii.extractors.feab_fill import (
    COL_DISCREPANCIAS,
    COL_HASH_SECOP,
    _decide_fills,
    _normalize_for_compare,
)


# --- NIT digit of verification (DIAN algorithm) ----------------------------


@pytest.mark.parametrize(
    ("nit", "expected_dv"),
    [
        ("800255024", "3"),  # Fiscalía General de la Nación — known NIT-DV
        ("860007738", "9"),  # Bavaria — known NIT-DV
        ("901148337", "1"),  # FEAB — verified by hand
        ("", ""),            # empty input
        ("notdigits", ""),   # non-numeric input
        (None, ""),
    ],
)
def test_nit_dv_matches_dian_algorithm(nit, expected_dv):
    assert nit_dv(nit) == expected_dv


def test_nit_dv_strips_separators():
    """800.255.024 should compute the same DV as 800255024."""
    assert nit_dv("800.255.024") == nit_dv("800255024") == "3"
    assert nit_dv("800-255-024") == "3"
    assert nit_dv("800 255 024") == "3"


# --- compute_feab_fill returns nothing when there's no SECOP data ---------


def test_compute_feab_fill_empty_inputs():
    result = compute_feab_fill(
        proceso=None, contratos=[], notice_uid=None, source_url=None,
    )
    # No SECOP data => no fills => no false positives.
    assert result.values == {}
    assert result.confidence == {}


def test_compute_feab_fill_proceso_only_fills_minimal_set():
    """When there's a proceso but no contract, only proceso-derivable cells."""
    proceso = {
        "id_del_proceso": "CO1.NTC.123",
        "modalidad_de_contratacion": "Mínima cuantía",
        "ordenentidad": "Nacional",
        "descripci_n_del_procedimiento": "Compra de equipos",
        "urlproceso": {"url": "https://example.org/proc"},
    }
    result = compute_feab_fill(
        proceso=proceso,
        contratos=[],
        notice_uid="CO1.NTC.123",
        source_url=None,
    )
    # Cells from proceso are filled; all contract-only cells stay missing.
    assert result.values.get(COL_LINK) == "https://example.org/proc"
    assert result.values.get(COL_NUMERO_CONTRATO) is None  # contract-only
    assert result.values.get(COL_VALOR_INICIAL) is None    # contract-only


def test_compute_feab_fill_real_feab_contract_arithmetic():
    """Mirror a real ECOBLUE-style contract — arithmetic must use Decimal."""
    proceso = {"id_del_proceso": "CO1.NTC.4156515", "urlproceso": {"url": "x"}}
    contratos = [{
        "id_contrato": "CO1.PCCNTR.4913416",
        "referencia_del_contrato": "CONTRATO-FEAB-0006-2023",
        "fecha_de_firma": "2023-05-08T00:00:00.000",
        "fecha_de_inicio_del_contrato": "2023-05-15T00:00:00.000",
        "fecha_de_fin_del_contrato": "2024-02-28T00:00:00.000",
        "estado_contrato": "Modificado",
        "valor_del_contrato": "62832000",
        "tipodocproveedor": "NIT",
        "documento_proveedor": "9009647055",
        "proveedor_adjudicado": "ECOBLUE S.A.S",
        "nit_entidad": "901148337",
        "nombre_entidad": "FEAB",
        "dias_adicionados": 63,
        "liquidaci_n": "Si",
        "fecha_fin_liquidacion": "2024-06-29T00:00:00.000",
        "objeto_del_contrato": "ENAJENACION DE FIBRA",
        "habilita_pago_adelantado": "No",
    }]
    result = compute_feab_fill(
        proceso=proceso, contratos=contratos,
        notice_uid="CO1.NTC.4156515", source_url=None,
    )
    assert result.values[COL_NUMERO_CONTRATO] == "CONTRATO-FEAB-0006-2023"
    assert result.values[COL_VALOR_INICIAL] == 62832000
    # 0 adiciones, 0 reducciones => total == inicial
    assert result.values[COL_VALOR_TOTAL] == 62832000
    assert result.values[COL_PRORROGAS_DIAS] == 63
    assert result.values[COL_FECHA_SUSCRIPCION] == "2023-05-08"
    assert result.values[COL_FECHA_INICIO] == "2023-05-15"
    assert result.values[COL_FECHA_TERMINACION] == "2024-02-28"
    assert result.values[COL_CONTRATISTA_NOMBRE] == "ECOBLUE S.A.S"
    assert result.values[COL_CONTRATISTA_NUM_ID] == "9009647055"
    # DV computed via DIAN algorithm
    assert result.values[COL_CONTRATISTA_DV] == nit_dv("9009647055")


def test_compute_feab_fill_decimal_arithmetic_for_adiciones():
    """Adiciones + reducciones must compute exact totals, no IEEE 754 drift."""
    proceso = {"id_del_proceso": "X", "urlproceso": {"url": "x"}}
    contratos = [{
        "id_contrato": "C1",
        "valor_del_contrato": "100000.50",
        "fecha_de_firma": "2024-01-01",
    }]
    adiciones = {
        "C1": [
            {"valor": "25000.25", "tipo": "Adición"},
            {"valor": "10000.10", "tipo": "Adición"},
            {"valor": "-5000.05", "tipo": "Reducción"},
        ],
    }
    result = compute_feab_fill(
        proceso=proceso, contratos=contratos,
        notice_uid=None, source_url=None,
        adiciones_by_contrato=adiciones,
    )
    # 100000.50 + (25000.25 + 10000.10) - 5000.05 = 130000.80 exactly
    assert result.values[COL_ADICIONES] == 35000.35
    assert result.values[COL_REDUCCIONES] == 5000.05
    assert result.values[COL_VALOR_TOTAL] == 130000.80


# --- Validation reports issues without blocking fills ---------------------


def test_validation_flags_arithmetic_mismatch_but_does_not_block():
    """Even if a check fails, the data is still in `values` (no false neg)."""
    bad = {COL_VALOR_INICIAL: 100, COL_VALOR_TOTAL: 999}  # impossibly different
    report = validate_fills(bad)
    assert COL_VALOR_TOTAL in report.needs_review
    assert any("arithmetic mismatch" in i.lower() for i in report.issues)


def test_validation_flags_date_inversion():
    """fecha_inicio > fecha_terminacion is impossible."""
    bad = {
        COL_FECHA_INICIO: "2025-12-01",
        COL_FECHA_TERMINACION: "2024-01-01",
    }
    report = validate_fills(bad)
    assert COL_FECHA_TERMINACION in report.needs_review


def test_validation_flags_wrong_dv():
    """If DV doesn't match the NIT, flag it."""
    bad = {
        COL_ENTIDAD_RECURSOS_NIT: "901148337",
        COL_ENTIDAD_RECURSOS_DV: "9",  # real DV is 1
    }
    report = validate_fills(bad)
    assert COL_ENTIDAD_RECURSOS_DV in report.needs_review


def test_validation_skips_dv_check_for_non_NIT_contractor():
    """A contratista with CC doesn't have a DV — don't false-flag."""
    ok = {
        COL_CONTRATISTA_TIPO_ID: "CC",
        COL_CONTRATISTA_NUM_ID: "1019082314",
        # no DV — that's correct for CC
    }
    report = validate_fills(ok)
    assert COL_CONTRATISTA_DV not in report.needs_review


def test_validation_does_not_block_correct_data():
    """Sanity: a clean record produces no flags."""
    good = {
        COL_VALOR_INICIAL: 1000,
        COL_VALOR_TOTAL: 1500,
        COL_ADICIONES: 500,
        COL_FECHA_SUSCRIPCION: "2024-01-01",
        COL_FECHA_INICIO: "2024-01-15",
        COL_FECHA_TERMINACION: "2024-12-31",
        COL_ENTIDAD_RECURSOS_NIT: "901148337",
        COL_ENTIDAD_RECURSOS_DV: "1",
    }
    report = validate_fills(good)
    assert report.needs_review == set()
    assert report.issues == []


# --- _decide_fills: no overwrite of manual data ---------------------------


def test_decide_fills_writes_to_empty_cells():
    """Empty cells get filled (no false negative — SECOP data shown)."""
    from secop_ii.feab_columns import FillResult
    result = FillResult(
        values={COL_NUMERO_CONTRATO: "CONTRATO-FEAB-001"},
        confidence={COL_NUMERO_CONTRATO: "HIGH"},
        sources={COL_NUMERO_CONTRATO: "contrato.referencia"},
    )
    fills, replaced_log, fuentes = _decide_fills(result=result, existing={})
    assert fills[COL_NUMERO_CONTRATO] == "CONTRATO-FEAB-001"
    # No log entry — empty cell isn't a "replaced" event.
    assert replaced_log == []


def test_decide_fills_overwrites_with_secop_and_logs_replaced():
    """SECOP wins: cell with different manual value gets replaced,
    old value goes to the audit log so nothing disappears silently."""
    from secop_ii.feab_columns import FillResult
    result = FillResult(
        values={COL_NUMERO_CONTRATO: "CONTRATO-FEAB-001"},
        confidence={COL_NUMERO_CONTRATO: "HIGH"},
        sources={COL_NUMERO_CONTRATO: "contrato.referencia"},
    )
    fills, replaced_log, fuentes = _decide_fills(
        result=result,
        existing={COL_NUMERO_CONTRATO: "CONTRATO-MANUAL-XYZ"},
    )
    # SECOP value gets written (cell is overwritten — SECOP is truth).
    assert fills[COL_NUMERO_CONTRATO] == "CONTRATO-FEAB-001"
    # Old manual value is logged for auditability — nothing eaten.
    assert len(replaced_log) == 1
    assert "CONTRATO-MANUAL-XYZ" in replaced_log[0]
    assert "CONTRATO-FEAB-001" in replaced_log[0]


def test_decide_fills_no_op_when_values_match():
    """Manual cell with same value as SECOP -> skip (preserves cell formatting)."""
    from secop_ii.feab_columns import FillResult
    result = FillResult(
        values={COL_NUMERO_CONTRATO: "CONTRATO-FEAB-001"},
        confidence={COL_NUMERO_CONTRATO: "HIGH"},
        sources={COL_NUMERO_CONTRATO: "contrato.referencia"},
    )
    fills, replaced_log, fuentes = _decide_fills(
        result=result,
        existing={COL_NUMERO_CONTRATO: "CONTRATO-FEAB-001"},
    )
    assert COL_NUMERO_CONTRATO not in fills
    assert replaced_log == []


def test_decide_fills_skips_internal_only_columns():
    """Internal-only cells (CDP, Orfeo, etc.) are NEVER touched.
    SECOP doesn't own them — manual data is preserved as authoritative."""
    from secop_ii.feab_columns import FillResult
    internal_col = next(iter(INTERNAL_ONLY))
    result = FillResult(
        values={internal_col: "should-not-be-written"},
        confidence={internal_col: "HIGH"},
        sources={internal_col: "test"},
    )
    fills, replaced_log, fuentes = _decide_fills(result=result, existing={})
    assert internal_col not in fills
    assert replaced_log == []


# --- Numeric / date normalization --------------------------------------------


def test_normalize_for_compare_money_handles_thousands_separators():
    """'62,832,000' must equal 62832000 for comparison purposes."""
    n1 = _normalize_for_compare("62,832,000", COL_VALOR_INICIAL)
    n2 = _normalize_for_compare(62832000, COL_VALOR_INICIAL)
    assert n1 == n2 == 62832000.0


def test_normalize_for_compare_dates_strip_time():
    """'2024-06-13' and '2024-06-13T00:00:00' compare equal."""
    n1 = _normalize_for_compare("2024-06-13", COL_FECHA_SUSCRIPCION)
    n2 = _normalize_for_compare("2024-06-13T00:00:00.000", COL_FECHA_SUSCRIPCION)
    assert n1 == n2 == "2024-06-13"


# --- Source fingerprint -----------------------------------------------------


def test_source_fingerprint_is_deterministic():
    """Same inputs -> same SHA-256 (Dra. can prove SECOP didn't change)."""
    p = {"id_del_proceso": "X", "modalidad_de_contratacion": "Mínima cuantía"}
    c = [{"id_contrato": "C1", "valor_del_contrato": "100"}]
    h1 = source_fingerprint(proceso=p, contratos=c, notice_uid="NTC-1")
    h2 = source_fingerprint(proceso=p, contratos=c, notice_uid="NTC-1")
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex digest


def test_source_fingerprint_changes_with_data():
    """Any change in SECOP payload -> different hash."""
    p = {"id_del_proceso": "X"}
    h1 = source_fingerprint(proceso=p, contratos=[], notice_uid="NTC-1")
    p["modalidad_de_contratacion"] = "Mínima cuantía"
    h2 = source_fingerprint(proceso=p, contratos=[], notice_uid="NTC-1")
    assert h1 != h2
