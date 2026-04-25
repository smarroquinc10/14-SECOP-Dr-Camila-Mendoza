"""Tests for the persistent watchlist (seguimiento.json).

The Dra.'s ability to *not lose* anything she adds depends on this file
being written atomically and surviving restarts. These tests exercise
the happy path and the edge cases: empty URL, invalid URL, duplicate
adds, persistence across instances, and remove.
"""
from __future__ import annotations

import pytest

from secop_ii.tracking import TrackedProcess, Watchlist


class TestAdd:
    def test_extracts_id_from_ntc_url(self, tmp_path):
        wl = Watchlist(path=tmp_path / "w.json")
        entry = wl.add_url(
            "https://community.secop.gov.co/Public/Tendering/OpportunityDetail/"
            "Index?noticeUID=CO1.NTC.1234567"
        )
        assert entry.id == "CO1.NTC.1234567"
        assert entry.added_at  # stamped

    def test_extracts_id_from_ppi_url(self, tmp_path):
        wl = Watchlist(path=tmp_path / "w.json")
        entry = wl.add_url(
            "https://community.secop.gov.co/Public/Tendering/ContractNoticePhases/"
            "View?PPI=CO1.PPI.30337199"
        )
        assert entry.id == "CO1.PPI.30337199"

    def test_rejects_empty_url(self, tmp_path):
        wl = Watchlist(path=tmp_path / "w.json")
        with pytest.raises(ValueError, match="vacía"):
            wl.add_url("")

    def test_rejects_url_without_secop_id(self, tmp_path):
        wl = Watchlist(path=tmp_path / "w.json")
        with pytest.raises(ValueError, match="identificador"):
            wl.add_url("https://www.google.com/search?q=secop")

    def test_duplicate_add_is_idempotent(self, tmp_path):
        wl = Watchlist(path=tmp_path / "w.json")
        a = wl.add_url("https://x/noticeUID=CO1.NTC.42")
        b = wl.add_url("https://x/noticeUID=CO1.NTC.42")
        assert a.id == b.id
        assert len(wl.entries()) == 1


class TestPersistence:
    def test_survives_reload(self, tmp_path):
        path = tmp_path / "w.json"
        wl1 = Watchlist(path=path)
        wl1.add_url("https://x/noticeUID=CO1.NTC.1")
        wl1.add_url("https://x/noticeUID=CO1.NTC.2")

        # New instance, same file
        wl2 = Watchlist(path=path)
        ids = {e.id for e in wl2.entries()}
        assert ids == {"CO1.NTC.1", "CO1.NTC.2"}


class TestRemove:
    def test_remove_existing(self, tmp_path):
        wl = Watchlist(path=tmp_path / "w.json")
        wl.add_url("https://x/noticeUID=CO1.NTC.1")
        assert wl.remove("CO1.NTC.1") is True
        assert wl.entries() == []

    def test_remove_nonexistent_is_noop(self, tmp_path):
        wl = Watchlist(path=tmp_path / "w.json")
        assert wl.remove("CO1.NTC.999") is False

    def test_is_tracked(self, tmp_path):
        wl = Watchlist(path=tmp_path / "w.json")
        wl.add_url("https://x/noticeUID=CO1.NTC.1")
        assert wl.is_tracked("CO1.NTC.1") is True
        assert wl.is_tracked("CO1.NTC.2") is False
