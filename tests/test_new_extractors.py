"""Tests for the 6 extractors added in Step 2 (March 2026).

Each extractor is exercised with a minimal fixture that mirrors the
exact shape of a real Socrata row (fields named exactly as they arrive
from ``p6dx-8zbt``, ``jbjy-vk9h``, etc.). We test three behaviours per
extractor:

1. Happy path — fields are filled from the fixture.
2. Empty path — when the upstream dataset returns nothing, the output
   columns exist (so the workbook layout is stable) but are empty strings.
3. Multi-row path — when a process has more than one contract / more
   than one póliza, aggregation (sum, join, max-date) behaves.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from secop_ii.extractors import (
    ContratoFullExtractor,
    GarantiasExtractor,
    ModsProcesoExtractor,
    PagosExtractor,
    ProcesoFullExtractor,
    SeguimientoExtractor,
)
from secop_ii.extractors.base import ProcessContext
from secop_ii.secop_client import SecopClient
from secop_ii.url_parser import parse_secop_url


@dataclass
class FakeCtx(ProcessContext):
    """Minimal ProcessContext that returns canned data without hitting network."""

    _p: dict | None = None
    _contratos: list[dict] = field(default_factory=list)
    _gar: dict[str, list[dict]] = field(default_factory=dict)
    _fact: dict[str, list[dict]] = field(default_factory=dict)
    _ejec: dict[str, list[dict]] = field(default_factory=dict)
    _susp: dict[str, list[dict]] = field(default_factory=dict)
    _mods: list[dict] = field(default_factory=list)

    def proceso(self):  # type: ignore[override]
        return self._p

    def contratos(self):  # type: ignore[override]
        return self._contratos

    def garantias_de(self, id_contrato):  # type: ignore[override]
        return self._gar.get(id_contrato, [])

    def facturas_de(self, id_contrato):  # type: ignore[override]
        return self._fact.get(id_contrato, [])

    def ejecucion_de(self, id_contrato):  # type: ignore[override]
        return self._ejec.get(id_contrato, [])

    def suspensiones_de(self, id_contrato):  # type: ignore[override]
        return self._susp.get(id_contrato, [])

    def mods_proceso(self):  # type: ignore[override]
        return self._mods


def _ref():
    return parse_secop_url(
        "https://community.secop.gov.co/Public/Tendering/OpportunityDetail/Index?noticeUID=CO1.NTC.123"
    )


# ---------------------------------------------------------------------------
# ProcesoFullExtractor
# ---------------------------------------------------------------------------
class TestProcesoFullExtractor:
    def test_extracts_modality_type_and_dates_from_proceso(self):
        proc = {
            "modalidad_de_contratacion": "Régimen especial",
            "tipo_de_contrato": "Compraventa",
            "subtipo_de_contrato": "No Definido",
            "referencia_del_proceso": "FEAB-EB-0013-2024",
            "nombre_del_adjudicador": "María Camila Mendoza Zubiría",
            "precio_base": "1000000",
            "valor_total_adjudicacion": "950000",
            "fecha_de_publicacion_del": "2024-11-25T00:00:00.000",
            "duracion": 60,
            "unidad_de_duracion": "día(s)",
            "respuestas_al_procedimiento": "1",
        }
        ctx = FakeCtx(ref=_ref(), client=SecopClient(), _p=proc)
        result = ProcesoFullExtractor().extract(ctx)

        assert result.ok
        v = result.values
        assert v["Proceso: Modalidad"] == "Régimen especial"
        assert v["Proceso: Tipo contrato"] == "Compraventa"
        assert v["Proceso: Referencia"] == "FEAB-EB-0013-2024"
        assert v["Proceso: Precio base"] == 1000000
        assert v["Proceso: Valor adjudicación"] == 950000
        assert v["Proceso: Fecha publicación"] == "2024-11-25"
        assert v["Proceso: Duración"] == "60 día(s)"
        assert v["Proceso: # ofertas recibidas"] == 1

    def test_empty_proceso_returns_empty_but_all_columns(self):
        ctx = FakeCtx(ref=_ref(), client=SecopClient(), _p=None)
        result = ProcesoFullExtractor().extract(ctx)
        assert not result.ok
        assert set(result.values) == set(ProcesoFullExtractor.output_columns)
        assert all(v == "" for v in result.values.values())

    def test_extras_captures_unknown_fields(self):
        proc = {
            # known field — goes to its own column
            "modalidad_de_contratacion": "X",
            # unknown field — should land in extras
            "estado_resumen": "FaseCerrada",
            "visualizaciones_del": 7,
        }
        ctx = FakeCtx(ref=_ref(), client=SecopClient(), _p=proc)
        result = ProcesoFullExtractor().extract(ctx)
        extras = result.values["Proceso: Otros campos"]
        assert "estado_resumen=FaseCerrada" in extras
        assert "visualizaciones_del=7" in extras
        # Known fields must NOT be duplicated in extras
        assert "modalidad_de_contratacion" not in extras


# ---------------------------------------------------------------------------
# ContratoFullExtractor
# ---------------------------------------------------------------------------
class TestContratoFullExtractor:
    def test_single_contract_all_key_fields(self):
        ctr = {
            "id_contrato": "CO1.PCCNTR.9999",
            "referencia_del_contrato": "CONTRATO-FEAB-001",
            "estado_contrato": "En ejecución",
            "proveedor_adjudicado": "ACME SAS",
            "documento_proveedor": "900123456",
            "tipodocproveedor": "NIT",
            "valor_del_contrato": "5000000",
            "valor_pagado": "2000000",
            "valor_pendiente_de_pago": "3000000",
            "fecha_de_firma": "2024-01-15T00:00:00.000",
            "nombre_supervisor": "Juan Pérez",
            "liquidaci_n": "Si",
        }
        ctx = FakeCtx(ref=_ref(), client=SecopClient(), _contratos=[ctr])
        result = ContratoFullExtractor().extract(ctx)
        v = result.values

        assert v["Contrato: ID(s)"] == "CO1.PCCNTR.9999"
        assert v["Contrato: Estado"] == "En ejecución"
        assert v["Contrato: Proveedor adjudicado"] == "ACME SAS"
        assert v["Contrato: NIT/doc proveedor"] == "NIT:900123456"
        assert v["Contrato: Valor"] == 5000000
        assert v["Contrato: Valor pagado"] == 2000000
        assert v["Contrato: Fecha firma"] == "2024-01-15"
        assert v["Contrato: Supervisor"] == "Juan Pérez"
        assert v["Contrato: ¿Liquidación?"] == "Si"

    def test_multiple_contracts_are_aggregated(self):
        ctr1 = {"id_contrato": "A", "valor_del_contrato": "1000", "valor_pagado": "500",
                "estado_contrato": "En ejecución", "proveedor_adjudicado": "ACME"}
        ctr2 = {"id_contrato": "B", "valor_del_contrato": "2000", "valor_pagado": "1000",
                "estado_contrato": "Cerrado", "proveedor_adjudicado": "ZETA"}
        ctx = FakeCtx(ref=_ref(), client=SecopClient(), _contratos=[ctr1, ctr2])
        result = ContratoFullExtractor().extract(ctx)
        v = result.values

        assert v["Contrato: ID(s)"] == "A | B"
        assert v["Contrato: Valor"] == 3000
        assert v["Contrato: Valor pagado"] == 1500
        # Estados: both shown in deterministic (sorted) order
        assert "En ejecución" in v["Contrato: Estado"]
        assert "Cerrado" in v["Contrato: Estado"]
        assert "ACME" in v["Contrato: Proveedor adjudicado"]
        assert "ZETA" in v["Contrato: Proveedor adjudicado"]

    def test_no_contracts_returns_empty_columns(self):
        ctx = FakeCtx(ref=_ref(), client=SecopClient(), _contratos=[])
        result = ContratoFullExtractor().extract(ctx)
        assert result.ok
        assert set(result.values) == set(ContratoFullExtractor.output_columns)


# ---------------------------------------------------------------------------
# GarantiasExtractor
# ---------------------------------------------------------------------------
class TestGarantiasExtractor:
    def test_counts_and_aggregates_polizas(self):
        contratos = [{"id_contrato": "C1"}]
        polizas = [
            {"aseguradora": "Seguros del Estado", "tipopoliza": "Contrato de Seguro",
             "estado": "Vigente", "fechafinpoliza": "2025-03-31 23:59:00",
             "numeropoliza": "144610", "valor": "3000000"},
            {"aseguradora": "Sura", "tipopoliza": "Contrato de Seguro",
             "estado": "Expirada", "fechafinpoliza": "2024-02-28 23:59:00",
             "numeropoliza": "77", "valor": "1500000"},
        ]
        ctx = FakeCtx(ref=_ref(), client=SecopClient(),
                      _contratos=contratos, _gar={"C1": polizas})
        result = GarantiasExtractor().extract(ctx)
        v = result.values

        assert v["Garantías: # pólizas"] == 2
        assert v["Garantías: # vigentes"] == 1
        assert "Seguros del Estado" in v["Garantías: Aseguradoras"]
        assert "Sura" in v["Garantías: Aseguradoras"]
        assert v["Garantías: Fecha fin más lejana"] == "2025-03-31"
        assert v["Garantías: Valor total"] == 4500000

    def test_empty_when_no_contracts(self):
        ctx = FakeCtx(ref=_ref(), client=SecopClient(), _contratos=[])
        result = GarantiasExtractor().extract(ctx)
        assert result.ok
        assert result.values["Garantías: # pólizas"] == ""


# ---------------------------------------------------------------------------
# PagosExtractor
# ---------------------------------------------------------------------------
class TestPagosExtractor:
    def test_counts_facturas_and_sums_values(self):
        contratos = [{"id_contrato": "C1"}]
        facts = [
            {"fecha_factura": "2024-02-01", "numero_de_factura": "A-1",
             "estado": "Pagado", "pago_confirmado": True,
             "valor_total": "1000", "valor_a_pagar": "1000", "valor_neto": "900"},
            {"fecha_factura": "2024-03-15", "numero_de_factura": "A-2",
             "estado": "Pendiente", "pago_confirmado": False,
             "valor_total": "500", "valor_a_pagar": "500", "valor_neto": "450"},
        ]
        ctx = FakeCtx(ref=_ref(), client=SecopClient(),
                      _contratos=contratos, _fact={"C1": facts})
        result = PagosExtractor().extract(ctx)
        v = result.values

        assert v["Pagos: # facturas"] == 2
        assert v["Pagos: # pagadas"] == 1
        assert v["Pagos: Total facturado"] == 1500
        assert v["Pagos: Total pagado"] == 1500
        # Most recent factura is the March one
        assert v["Pagos: Última factura"].startswith("2024-03-15")

    def test_empty_when_no_contracts(self):
        ctx = FakeCtx(ref=_ref(), client=SecopClient(), _contratos=[])
        result = PagosExtractor().extract(ctx)
        assert result.ok
        assert result.values["Pagos: # facturas"] == ""


# ---------------------------------------------------------------------------
# SeguimientoExtractor
# ---------------------------------------------------------------------------
class TestSeguimientoExtractor:
    def test_takes_max_avance_and_counts_suspensions(self):
        contratos = [{"id_contrato": "C1"}]
        ejec = [
            {"porcentaje_de_avance_real": "30", "porcentajedeavanceesperado": "50"},
            {"porcentaje_de_avance_real": "45", "porcentajedeavanceesperado": "60"},
        ]
        susp = [
            {"fecha_de_creacion": "2024-06-21", "tipo": "Suspension",
             "proposito_de_la_modificacion": "FUERZA MAYOR"},
        ]
        ctx = FakeCtx(ref=_ref(), client=SecopClient(),
                      _contratos=contratos, _ejec={"C1": ejec}, _susp={"C1": susp})
        result = SeguimientoExtractor().extract(ctx)
        v = result.values

        assert v["Seguimiento: Avance real %"] == 45
        assert v["Seguimiento: Avance esperado %"] == 60
        assert v["Seguimiento: Brecha avance"] == 15
        assert v["Seguimiento: # suspensiones"] == 1
        assert v["Seguimiento: Tipo suspensión"] == "Suspension"

    def test_empty_when_nothing_tracked(self):
        ctx = FakeCtx(ref=_ref(), client=SecopClient(),
                      _contratos=[{"id_contrato": "C1"}])
        result = SeguimientoExtractor().extract(ctx)
        v = result.values
        assert v["Seguimiento: Avance real %"] == ""
        assert v["Seguimiento: # suspensiones"] == 0


# ---------------------------------------------------------------------------
# ModsProcesoExtractor
# ---------------------------------------------------------------------------
class TestModsProcesoExtractor:
    def test_counts_and_picks_latest(self):
        mods = [
            {"ultima_modificacion": "2021-02-15 15:02:50.2081303",
             "descripcion_proceso": "Primera edición"},
            {"ultima_modificacion": "2021-05-20 11:00:00.0000000",
             "descripcion_proceso": "Extensión del plazo"},
        ]
        ctx = FakeCtx(ref=_ref(), client=SecopClient(), _mods=mods)
        result = ModsProcesoExtractor().extract(ctx)
        v = result.values

        assert v["Mods proceso: # ediciones"] == 2
        assert v["Mods proceso: Última edición"].startswith("2021-05-20")
        assert "Extensión del plazo" in v["Mods proceso: Detalle"]

    def test_empty_when_no_mods(self):
        ctx = FakeCtx(ref=_ref(), client=SecopClient(), _mods=[])
        result = ModsProcesoExtractor().extract(ctx)
        assert result.ok
        assert result.values["Mods proceso: # ediciones"] == ""
