from __future__ import annotations

from secop_ii.extractors.auditoria import (
    COL_ENTIDAD,
    COL_FASE,
    COL_ID,
    COL_LINK_API,
    COL_NIT,
    COL_OBJETO,
    COL_VALOR,
    AuditoriaExtractor,
)
from secop_ii.extractors.base import ProcessContext
from secop_ii.secop_client import SecopClient
from secop_ii.url_parser import parse_secop_url


class _FakeCtx(ProcessContext):
    def __init__(self, ref, proceso, notice_uid=None):
        super().__init__(ref=ref, client=SecopClient())
        self._p = proceso
        self._ntc = notice_uid

    def proceso(self):
        return self._p

    def notice_uid(self):
        return self._ntc

    def contratos(self):
        return []

    def adiciones_de(self, _):
        return []


class TestAuditoriaExtractor:
    def test_mirror_fields_from_proceso(self):
        ref = parse_secop_url(
            "https://community.secop.gov.co/x?noticeUID=CO1.NTC.123"
        )
        proceso = {
            "id_del_proceso": "CO1.NTC.123",
            "fase": "Adjudicado",
            "entidad": "Alcaldía de Ejemplo",
            "nit_entidad": "800000000",
            "descripci_n_del_procedimiento": "Suministro de papel 2026",
            "precio_base": "50000000",
        }
        ctx = _FakeCtx(ref, proceso)

        result = AuditoriaExtractor().extract(ctx)

        assert result.ok is True
        assert result.values[COL_ID] == "CO1.NTC.123"
        assert result.values[COL_FASE] == "Adjudicado"
        assert result.values[COL_ENTIDAD] == "Alcaldía de Ejemplo"
        assert result.values[COL_NIT] == "800000000"
        assert "Suministro de papel" in result.values[COL_OBJETO]
        assert result.values[COL_VALOR] == 50000000.0
        assert "datos.gov.co" in result.values[COL_LINK_API]
        assert "CO1.NTC.123" in result.values[COL_LINK_API]

    def test_still_emits_id_and_link_when_proceso_not_found(self):
        """Even a miss on Socrata must produce an auditable row:
        the identifier we extracted and the exact query that returned empty.
        """
        ref = parse_secop_url(
            "https://community.secop.gov.co/x?PPI=CO1.PPI.99999"
        )
        ctx = _FakeCtx(ref, proceso=None)

        result = AuditoriaExtractor().extract(ctx)

        assert result.ok is False
        assert result.values[COL_ID] == "CO1.PPI.99999"
        assert result.values[COL_FASE] == "no_encontrado"
        assert result.values[COL_ENTIDAD] == ""
        assert "CO1.PPI.99999" in result.values[COL_LINK_API]

    def test_link_is_a_real_datos_gov_co_url(self):
        ref = parse_secop_url(
            "https://community.secop.gov.co/x?PPI=CO1.PPI.46305103"
        )
        ctx = _FakeCtx(ref, proceso=None)

        link = AuditoriaExtractor().extract(ctx).values[COL_LINK_API]
        assert link.startswith("https://www.datos.gov.co/resource/")
        assert "p6dx-8zbt.json" in link
        assert "$where=" in link
