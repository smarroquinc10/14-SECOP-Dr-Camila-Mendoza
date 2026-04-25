from __future__ import annotations

import json
from pathlib import Path

import pytest

from secop_ii.extractors.base import ProcessContext
from secop_ii.extractors.modificatorios import (
    COL_CANTIDAD,
    COL_FECHA_ULTIMO,
    COL_FUENTE,
    COL_TIENE,
    COL_TIPOS,
    ModificatoriosExtractor,
)
from secop_ii.secop_client import SecopClient
from secop_ii.url_parser import parse_secop_url

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str):
    with open(FIXTURES / name, "r", encoding="utf-8") as fh:
        return json.load(fh)


class _FakeContext(ProcessContext):
    def __init__(self, ref, proceso, contratos, adiciones):
        super().__init__(ref=ref, client=SecopClient())
        self._p = proceso
        self._c = contratos
        self._a = adiciones

    def proceso(self):
        return self._p

    def notice_uid(self):
        return None

    def contratos(self):
        return self._c

    def adiciones_de(self, id_contrato):
        return [a for a in self._a if str(a.get("id_contrato")) == str(id_contrato)]


class TestModificatoriosExtractor:
    def test_published_process_without_contract_reports_no_modificatorios(self):
        ref = parse_secop_url(
            "https://community.secop.gov.co/Public/Tendering/ContractNoticePhases/View"
            "?PPI=CO1.PPI.46305103"
        )
        proceso = _load("ppi_46305103_proceso.json")[0]
        ctx = _FakeContext(ref, proceso, contratos=[], adiciones=[])

        result = ModificatoriosExtractor().extract(ctx)

        assert result.ok is True
        assert result.values[COL_TIENE] == "No"
        assert result.values[COL_CANTIDAD] == 0
        assert result.values[COL_TIPOS] == ""

    def test_process_with_adiciones_is_summarized(self):
        ref = parse_secop_url(
            "https://community.secop.gov.co/x?noticeUID=CO1.NTC.9999001"
        )
        ctx = _FakeContext(
            ref,
            proceso=_load("con_modificatorios_proceso.json")[0],
            contratos=_load("con_modificatorios_contratos.json"),
            adiciones=_load("con_modificatorios_adiciones.json"),
        )

        result = ModificatoriosExtractor().extract(ctx)

        assert result.ok is True
        assert result.values[COL_TIENE] == "Sí"
        assert result.values[COL_CANTIDAD] == 2  # 2 adiciones from cb9c-h8sn
        assert "Adición" in result.values[COL_TIPOS]
        assert "Prórroga" in result.values[COL_TIPOS]
        assert result.values[COL_FECHA_ULTIMO] == "2026-03-05T00:00:00.000"
        assert "cb9c(2)" in result.values[COL_FUENTE]

    def test_process_not_found_marks_row_as_not_found(self):
        ref = parse_secop_url(
            "https://community.secop.gov.co/x?PPI=CO1.PPI.99999"
        )
        ctx = _FakeContext(ref, proceso=None, contratos=[], adiciones=[])

        result = ModificatoriosExtractor().extract(ctx)

        assert result.ok is False
        assert result.values[COL_TIENE] == ""
        assert "no_encontrado" in result.values["Detalle modificatorios"]

    @pytest.mark.parametrize(
        "dias_adicionados, expected",
        [
            ("0", "No"),
            ("15", "Sí"),
            ("", "No"),
        ],
    )
    def test_dias_adicionados_triggers_modificatorio(self, dias_adicionados, expected):
        ref = parse_secop_url(
            "https://community.secop.gov.co/x?noticeUID=CO1.NTC.1"
        )
        ctx = _FakeContext(
            ref,
            proceso={"id_del_proceso": "CO1.NTC.1"},
            contratos=[
                {
                    "id_contrato": "CO1.PCCNTR.1",
                    "dias_adicionados": dias_adicionados,
                }
            ],
            adiciones=[],
        )

        assert ModificatoriosExtractor().extract(ctx).values[COL_TIENE] == expected
