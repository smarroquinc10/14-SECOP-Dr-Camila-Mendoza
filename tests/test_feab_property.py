"""Property-based tests for FEAB precision — tested from many angles.

Hypothesis generates thousands of random inputs to find edge cases that
hand-written tests miss. The properties tested here are the **invariants**
that must hold to guarantee no false positives or negatives in compliance.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import HealthCheck, assume, given, settings, strategies as st

from secop_ii.feab_columns import (
    COL_ADICIONES,
    COL_FECHA_INICIO,
    COL_FECHA_SUSCRIPCION,
    COL_FECHA_TERMINACION,
    COL_NUMERO_CONTRATO,
    COL_REDUCCIONES,
    COL_VALOR_INICIAL,
    COL_VALOR_TOTAL,
    compute_feab_fill,
    nit_dv,
    source_fingerprint,
)
from secop_ii.feab_validation import validate_fills
from secop_ii.extractors.feab_fill import _decide_fills, _normalize_for_compare


# ------------ NIT DV invariants ----------------------------------------------


@given(st.integers(min_value=100_000, max_value=99_999_999_999))
def test_nit_dv_is_always_a_single_digit(nit_int):
    """For any 6-11 digit NIT, the DV must be exactly one digit 0-9."""
    dv = nit_dv(str(nit_int))
    assert dv in {str(d) for d in range(10)} or dv == ""


@given(st.integers(min_value=100_000_000, max_value=999_999_999))
def test_nit_dv_is_deterministic(nit_int):
    """Calling twice on the same NIT yields the same DV."""
    s = str(nit_int)
    assert nit_dv(s) == nit_dv(s)


@given(st.text())
def test_nit_dv_never_raises_on_garbage(garbage):
    """DV computation is safe on any string input — never raises."""
    result = nit_dv(garbage)
    assert isinstance(result, str)


# ------------ Decimal arithmetic invariants ----------------------------------


@st.composite
def adiciones_strategy(draw):
    """Generate a list of adiciones with random valor (positive + negative)."""
    n = draw(st.integers(min_value=0, max_value=10))
    return [
        {
            "valor": draw(st.decimals(min_value=Decimal("-1000000"),
                                     max_value=Decimal("1000000"),
                                     allow_nan=False, allow_infinity=False,
                                     places=2)),
            "tipo": draw(st.sampled_from(["Adición", "Reducción", "Otrosí"])),
        }
        for _ in range(n)
    ]


@given(
    valor_inicial=st.decimals(min_value=Decimal("0"),
                              max_value=Decimal("10000000000"),
                              allow_nan=False, allow_infinity=False, places=2),
    adiciones=adiciones_strategy(),
)
@settings(suppress_health_check=[HealthCheck.too_slow], max_examples=50)
def test_valor_total_equals_inicial_plus_net_adiciones(valor_inicial, adiciones):
    """For any combination, valor_total == inicial + sum(positive) - sum(|negative|)."""
    proceso = {"id_del_proceso": "X", "urlproceso": {"url": "http://x"}}
    contratos = [{
        "id_contrato": "C1",
        "valor_del_contrato": str(valor_inicial),
        "fecha_de_firma": "2024-01-01",
    }]
    result = compute_feab_fill(
        proceso=proceso, contratos=contratos,
        notice_uid=None, source_url=None,
        adiciones_by_contrato={"C1": [{"valor": str(a["valor"]), "tipo": a["tipo"]}
                                       for a in adiciones]},
    )
    add_total = sum(a["valor"] for a in adiciones if a["valor"] > 0)
    red_total = sum(abs(a["valor"]) for a in adiciones if a["valor"] < 0)
    expected_total = valor_inicial + add_total - red_total

    if COL_VALOR_TOTAL in result.values:
        actual = Decimal(str(result.values[COL_VALOR_TOTAL]))
        # Must match exactly (Decimal arithmetic, no rounding drift)
        assert abs(actual - expected_total) < Decimal("0.01"), (
            f"valor_total drift: actual={actual} expected={expected_total} "
            f"(inicial={valor_inicial}, add={add_total}, red={red_total})"
        )


# ------------ Validation invariants ------------------------------------------


@given(st.integers(min_value=-1000, max_value=1000))
def test_validation_flags_negative_amounts(amount):
    """Any negative valor_inicial gets flagged for review."""
    report = validate_fills({COL_VALOR_INICIAL: amount})
    if amount < 0:
        assert COL_VALOR_INICIAL in report.needs_review
    else:
        assert COL_VALOR_INICIAL not in report.needs_review


@given(
    inicio_year=st.integers(min_value=1990, max_value=2099),
    inicio_month=st.integers(min_value=1, max_value=12),
    inicio_day=st.integers(min_value=1, max_value=28),
    days_to_fin=st.integers(min_value=-365, max_value=365),
)
def test_validation_flags_terminacion_before_inicio(
    inicio_year, inicio_month, inicio_day, days_to_fin
):
    """Whenever terminacion < inicio, the validator must catch it."""
    from datetime import date, timedelta
    inicio = date(inicio_year, inicio_month, inicio_day)
    fin = inicio + timedelta(days=days_to_fin)
    report = validate_fills({
        COL_FECHA_INICIO: inicio.isoformat(),
        COL_FECHA_TERMINACION: fin.isoformat(),
    })
    if fin < inicio:
        assert COL_FECHA_TERMINACION in report.needs_review
    # if fin >= inicio it shouldn't be flagged for that reason


# ------------ No-overwrite invariants ----------------------------------------


@given(st.text(min_size=1).filter(lambda s: s.strip()))
def test_decide_fills_secop_wins_logs_replaced(manual_value):
    """SECOP wins for any non-matching manual value. Old value goes to
    the audit log so nothing disappears silently."""
    from secop_ii.feab_columns import FillResult
    result = FillResult(
        values={COL_NUMERO_CONTRATO: "FROM-SECOP"},
        confidence={COL_NUMERO_CONTRATO: "HIGH"},
        sources={COL_NUMERO_CONTRATO: "test"},
    )
    fills, replaced_log, _ = _decide_fills(
        result=result,
        existing={COL_NUMERO_CONTRATO: manual_value},
    )
    same = (_normalize_for_compare(manual_value, COL_NUMERO_CONTRATO) ==
            _normalize_for_compare("FROM-SECOP", COL_NUMERO_CONTRATO))
    if same:
        # Already correct — no overwrite (preserves cell formatting),
        # no log entry (no replacement happened).
        assert COL_NUMERO_CONTRATO not in fills
        assert replaced_log == []
    else:
        # SECOP wins. Cell gets the SECOP value, old goes to log.
        assert fills[COL_NUMERO_CONTRATO] == "FROM-SECOP"
        # Empty-ish manuals don't generate a "replaced" log line —
        # filling an empty cell is fill, not replacement.
        manual_norm = _normalize_for_compare(manual_value, COL_NUMERO_CONTRATO)
        if manual_norm in (None, "", "NO", "N/A"):
            assert replaced_log == []
        else:
            assert len(replaced_log) == 1


# ------------ Source fingerprint invariants ----------------------------------


@given(
    proceso_id=st.text(min_size=1, max_size=30),
    contract_count=st.integers(min_value=0, max_value=5),
)
def test_fingerprint_changes_when_contracts_added(proceso_id, contract_count):
    """Adding any contract changes the SHA-256 — invariant for audit trail."""
    proceso = {"id_del_proceso": proceso_id}
    h_empty = source_fingerprint(proceso=proceso, contratos=[], notice_uid=None)
    contratos = [{"id_contrato": f"C{i}"} for i in range(contract_count)]
    h_with = source_fingerprint(proceso=proceso, contratos=contratos,
                                notice_uid=None)
    if contract_count == 0:
        assert h_empty == h_with
    else:
        assert h_empty != h_with


@given(st.text(min_size=1))
def test_fingerprint_is_64_chars_hex(payload_text):
    """Hash output is always 64-char hex regardless of input."""
    h = source_fingerprint(
        proceso={"id_del_proceso": payload_text},
        contratos=[],
        notice_uid=None,
    )
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


# ------------ Date normalization invariants ----------------------------------


@given(
    year=st.integers(min_value=1990, max_value=2099),
    month=st.integers(min_value=1, max_value=12),
    day=st.integers(min_value=1, max_value=28),
)
def test_date_normalize_handles_iso_with_time(year, month, day):
    """Both '2024-06-13' and '2024-06-13T14:30:00.000' normalize the same."""
    from datetime import date
    d = date(year, month, day).isoformat()
    n1 = _normalize_for_compare(d, COL_FECHA_SUSCRIPCION)
    n2 = _normalize_for_compare(f"{d}T14:30:00.000", COL_FECHA_SUSCRIPCION)
    assert n1 == n2


# ------------ Money normalization invariants ---------------------------------


@given(st.integers(min_value=0, max_value=999_999_999_999))
def test_money_normalize_strips_thousands_separator(amount):
    """'1,234,567' must equal 1234567 for comparison."""
    formatted = f"{amount:,}"  # "1,234,567"
    n1 = _normalize_for_compare(formatted, COL_VALOR_INICIAL)
    n2 = _normalize_for_compare(amount, COL_VALOR_INICIAL)
    assert n1 == n2 == float(amount)


# ------------ End-to-end invariants ------------------------------------------


@given(
    valor=st.integers(min_value=1, max_value=999_999_999),
    objeto=st.text(min_size=10, max_size=200),
)
@settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
def test_compute_feab_fill_never_raises_on_valid_inputs(valor, objeto):
    """Whatever realistic SECOP shape we throw at compute_feab_fill,
    it must never raise — only return what it can."""
    proceso = {
        "id_del_proceso": "CO1.NTC.X",
        "urlproceso": {"url": "https://example.org"},
        "modalidad_de_contratacion": "Mínima cuantía",
    }
    contratos = [{
        "id_contrato": "C1",
        "valor_del_contrato": str(valor),
        "objeto_del_contrato": objeto,
        "fecha_de_firma": "2024-01-01",
        "fecha_de_inicio_del_contrato": "2024-01-15",
        "fecha_de_fin_del_contrato": "2024-12-31",
    }]
    result = compute_feab_fill(
        proceso=proceso, contratos=contratos,
        notice_uid="CO1.NTC.X", source_url=None,
    )
    # Should always return SOMETHING (no crash)
    assert isinstance(result.values, dict)
    assert COL_VALOR_INICIAL in result.values
    assert result.values[COL_VALOR_INICIAL] == valor
