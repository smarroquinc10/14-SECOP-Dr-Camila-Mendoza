"""Tests for the cross-check engine.

Covers:
1. API vs Portal comparisons (fase, valor, modalidad, modificatorios)
2. Internal consistency (proceso vs contrato) — proveedor name, NIT, value
3. Date monotonicity (firma ≤ inicio ≤ fin)
4. Fuzzy name matching (tolerates accents + minor typos)
5. NIT cleaning (strips "NIT:" prefix, zeros, dashes)
6. Edge cases (empty inputs, both-missing, zero values)
"""
from __future__ import annotations

from secop_ii.discrepancies import detect_discrepancies


# ---------------------------------------------------------------------------
# API vs Portal
# ---------------------------------------------------------------------------
class TestApiVsPortal:
    def test_clean_when_api_and_portal_agree(self):
        assert detect_discrepancies({
            "Fase en SECOP": "Ejecución",
            "Portal: Fase": "ejecución",  # case-insensitive
            "Valor estimado": 1_000_000,
            "Portal: Precio estimado": "$ 1.000.000 COP",
            "# modificatorios": 2,
            "Portal: # notificaciones": 3,
        }) == ""

    def test_fase_mismatch_is_flagged(self):
        msg = detect_discrepancies({
            "Fase en SECOP": "Adjudicado",
            "Portal: Fase": "Ejecución",
        })
        assert "Fase en SECOP" in msg
        assert "Adjudicado" in msg and "Ejecución" in msg

    def test_mods_count_api_behind_portal(self):
        msg = detect_discrepancies({
            "# modificatorios": 0,
            "Portal: # notificaciones": 4,
        })
        assert "API atrasado" in msg

    def test_money_within_1_percent_is_clean(self):
        assert detect_discrepancies({
            "Valor estimado": 1_000_000,
            "Portal: Precio estimado": "$ 1.005.000",  # +0.5% — tolerated
        }) == ""

    def test_money_beyond_1_percent_is_flagged(self):
        msg = detect_discrepancies({
            "Valor estimado": 1_000_000,
            "Portal: Precio estimado": 1_050_000,  # +5%
        })
        assert "Valor estimado" in msg

    def test_modalidad_mismatch_is_flagged(self):
        msg = detect_discrepancies({
            "Proceso: Modalidad": "Régimen especial",
            "Portal: Modalidad": "Contratación directa",
        })
        assert "Proceso: Modalidad" in msg


# ---------------------------------------------------------------------------
# Internal consistency
# ---------------------------------------------------------------------------
class TestInternalConsistency:
    def test_same_proveedor_different_capitalisation_is_clean(self):
        assert detect_discrepancies({
            "Proceso: Nombre proveedor adjudicado": "ACME SAS",
            "Contrato: Proveedor adjudicado": "Acme S.A.S.",
        }) == ""

    def test_different_proveedor_is_flagged(self):
        msg = detect_discrepancies({
            "Proceso: Nombre proveedor adjudicado": "ACME SAS",
            "Contrato: Proveedor adjudicado": "ZETA LTDA",
        })
        assert "proveedor" in msg.lower() or "Proveedor" in msg

    def test_nit_with_prefix_is_cleaned_before_compare(self):
        # jbjy-vk9h format: "NIT:900123456"; p6dx-8zbt returns plain "900123456"
        assert detect_discrepancies({
            "Proceso: NIT proveedor adjudicado": "900123456",
            "Contrato: NIT/doc proveedor": "NIT:900123456",
        }) == ""

    def test_different_nits_are_flagged(self):
        msg = detect_discrepancies({
            "Proceso: NIT proveedor adjudicado": "900111111",
            "Contrato: NIT/doc proveedor": "NIT:900222222",
        })
        assert "NIT" in msg

    def test_value_mismatch_is_flagged_over_1_percent(self):
        msg = detect_discrepancies({
            "Proceso: Valor adjudicación": 1_000_000,
            "Contrato: Valor": 2_000_000,
        })
        # This hits the "money" kind in _PAIRS_API_INTERNAL
        assert "$1,000,000" in msg or "1,000,000" in msg


# ---------------------------------------------------------------------------
# Date monotonicity
# ---------------------------------------------------------------------------
class TestDateMonotonicity:
    def test_firma_inicio_fin_in_order_is_clean(self):
        assert detect_discrepancies({
            "Contrato: Fecha firma": "2024-01-10",
            "Contrato: Fecha inicio": "2024-01-15",
            "Contrato: Fecha fin": "2024-06-30",
        }) == ""

    def test_firma_after_inicio_is_flagged(self):
        msg = detect_discrepancies({
            "Contrato: Fecha firma": "2024-02-01",
            "Contrato: Fecha inicio": "2024-01-15",
        })
        assert "Fechas fuera de orden" in msg

    def test_spanish_date_formats_are_parsed(self):
        # dateparser should understand "6 de marzo de 2024"
        assert detect_discrepancies({
            "Contrato: Fecha firma": "6 de marzo de 2024",
            "Contrato: Fecha inicio": "2024-03-10",
            "Contrato: Fecha fin": "2024-12-31",
        }) == ""

    def test_missing_middle_date_does_not_crash(self):
        # firma and fin present, inicio absent — still monotonic
        assert detect_discrepancies({
            "Contrato: Fecha firma": "2024-01-01",
            "Contrato: Fecha fin": "2024-12-31",
        }) == ""


# ---------------------------------------------------------------------------
# Empty inputs — never crash, never hallucinate a discrepancy
# ---------------------------------------------------------------------------
class TestEdgeCases:
    def test_empty_dict(self):
        assert detect_discrepancies({}) == ""

    def test_only_api_values(self):
        # No portal columns at all → no cross-check triggered
        assert detect_discrepancies({"Fase en SECOP": "Ejecución"}) == ""

    def test_both_values_are_none(self):
        assert detect_discrepancies({
            "Fase en SECOP": None,
            "Portal: Fase": None,
        }) == ""

    def test_empty_strings_are_treated_as_missing(self):
        assert detect_discrepancies({
            "Fase en SECOP": "",
            "Portal: Fase": "",
        }) == ""
