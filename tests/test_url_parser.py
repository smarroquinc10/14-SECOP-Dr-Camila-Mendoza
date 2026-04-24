from __future__ import annotations

import pytest

from secop_ii.url_parser import (
    InvalidSecopUrlError,
    normalize_url,
    parse_secop_url,
)


class TestParseSecopUrl:
    @pytest.mark.parametrize(
        "url, expected_id, expected_kind",
        [
            (
                "https://community.secop.gov.co/Public/Tendering/ContractNoticePhases/View"
                "?PPI=CO1.PPI.46305103&isFromPublicArea=True&isModal=False",
                "CO1.PPI.46305103",
                "PPI",
            ),
            (
                "https://community.secop.gov.co/Public/Tendering/OpportunityDetail/Index"
                "?noticeUID=CO1.NTC.1234567&isFromPublicArea=True",
                "CO1.NTC.1234567",
                "NTC",
            ),
            (
                "https://community.secop.gov.co/Public/Tendering/ContractDetailView/Index"
                "?PCCNTR=CO1.PCCNTR.5551234",
                "CO1.PCCNTR.5551234",
                "PCCNTR",
            ),
            (
                "https://community.secop.gov.co/Public/Bidding/NoticePublic/Index"
                "?ProcessID=CO1.NTC.42",
                "CO1.NTC.42",
                "NTC",
            ),
            (
                "https://community.secop.gov.co/Public/Tendering/ContractNoticePhases/View"
                "?ppi=CO1.PPI.46305103",
                "CO1.PPI.46305103",
                "PPI",
            ),
            (
                "https://community.secop.gov.co/path/CO1.BDOS.77777/anything",
                "CO1.BDOS.77777",
                "BDOS",
            ),
        ],
    )
    def test_extracts_known_identifiers(self, url, expected_id, expected_kind):
        ref = parse_secop_url(url)
        assert ref.process_id == expected_id
        assert ref.kind == expected_kind
        assert ref.source_url == url

    @pytest.mark.parametrize(
        "url",
        [
            "",
            "https://example.com",
            "https://community.secop.gov.co/Public/Common/GoogleReCaptcha/Index"
            "?previousUrl=%2FPublic%2FTendering%2FContractNoticeManagement%2FIndex",
        ],
    )
    def test_rejects_invalid_urls(self, url):
        with pytest.raises(InvalidSecopUrlError):
            parse_secop_url(url)

    def test_flags_for_kind(self):
        notice = parse_secop_url(
            "https://community.secop.gov.co/x?noticeUID=CO1.NTC.1"
        )
        contract = parse_secop_url(
            "https://community.secop.gov.co/x?noticeUID=CO1.PCCNTR.2"
        )
        ppi = parse_secop_url("https://community.secop.gov.co/x?PPI=CO1.PPI.3")

        assert notice.is_notice and not notice.is_contract
        assert contract.is_contract and not contract.is_notice
        assert ppi.is_published_process


class TestNormalizeUrl:
    def test_drops_tracking_params(self):
        raw = (
            "https://community.secop.gov.co/Public/Tendering/ContractNoticePhases/View"
            "?PPI=CO1.PPI.46305103&isFromPublicArea=True&isModal=False"
        )
        normalized = normalize_url(raw)
        assert "isFromPublicArea" not in normalized
        assert "isModal" not in normalized
        assert "PPI=CO1.PPI.46305103" in normalized

    def test_is_idempotent(self):
        raw = (
            "https://community.secop.gov.co/X?PPI=CO1.PPI.1&isModal=False"
        )
        once = normalize_url(raw)
        twice = normalize_url(once)
        assert once == twice
