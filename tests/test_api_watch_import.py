"""Tests for ``POST /watch/import-from-excel``.

We don't hit the real SECOP — the endpoint calls
``_client.resolve_notice_uid`` for each parsed URL, so we monkeypatch it
to a no-op. The watch list lives at ``.cache/watched_urls.json``; we
redirect it to a tmp path so tests don't pollute real state.

Verifies:

* Auto-detects header row (1 vs 4 — the legacy ``FEAB 2018-2021`` layout)
* Auto-detects the LINK column case-insensitively
* Skips URLs that aren't SECOP
* Dedups within the run AND against an already-populated watch list
* Per-sheet stats add up to the global counts
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook


@pytest.fixture
def fixture_workbook(tmp_path: Path) -> Path:
    """Build a 3-sheet workbook that exercises every layout we expect."""
    wb = Workbook()
    # Sheet 1: row-1 headers, two valid SECOP URLs (one of which is dup
    # of sheet 2), one empty, one non-SECOP URL.
    s1 = wb.active
    s1.title = "FEAB 2026"
    s1.append(["#", "OBJETO", "LINK"])
    s1.append([1, "Contrato A",
              "https://community.secop.gov.co/Public/Tendering/"
              "OpportunityDetail/Index?noticeUID=CO1.NTC.1111111"])
    s1.append([2, "Contrato B",
              "https://community.secop.gov.co/Public/Tendering/"
              "OpportunityDetail/Index?noticeUID=CO1.NTC.2222222"])
    s1.append([3, "Contrato vacio", ""])
    s1.append([4, "URL externa", "https://www.google.com/search?q=foo"])

    # Sheet 2: row-1 headers — one URL is a dup of sheet 1 (NTC.1111111),
    # one new.
    s2 = wb.create_sheet("FEAB 2025")
    s2.append(["#", "OBJETO", "LINK"])
    s2.append([1, "Contrato A (otra hoja)",
              "https://community.secop.gov.co/Public/Tendering/"
              "OpportunityDetail/Index?noticeUID=CO1.NTC.1111111"])
    s2.append([2, "Contrato C",
              "https://community.secop.gov.co/Public/Tendering/"
              "OpportunityDetail/Index?noticeUID=CO1.NTC.3333333"])

    # Sheet 3: row-4 headers (legacy FEAB 2018-2021 layout). LINK is in
    # an arbitrary column to verify we find it by name, not by position.
    s3 = wb.create_sheet("FEAB 2018-2021")
    s3.append(["PROCESO GESTIÓN CONTRACTUAL"])
    s3.append(["FORMATO"])
    s3.append([])
    s3.append(["#", "OBJETO", "LINK", "EXTRA"])
    s3.append([1, "Contrato D",
              "https://community.secop.gov.co/Public/Tendering/"
              "OpportunityDetail/Index?noticeUID=CO1.NTC.4444444",
              "x"])

    out = tmp_path / "fixture.xlsx"
    wb.save(out)
    return out


@pytest.fixture
def client(monkeypatch, tmp_path: Path) -> TestClient:
    """Build a TestClient with the watch list and SECOP client patched
    so the test runs offline and doesn't pollute real cache files."""
    from secop_ii import api as api_module

    # Redirect watch list to tmp
    monkeypatch.setattr(api_module, "_WATCH_PATH",
                        tmp_path / "watched_urls.json")

    # Block any SECOP network call. resolve_notice_uid is the only one
    # the importer touches.
    monkeypatch.setattr(api_module._client, "resolve_notice_uid",
                        lambda pid, url=None: None)

    return TestClient(api_module.app)


class TestWatchImportFromExcel:
    def test_imports_all_unique_secop_urls(self, client, fixture_workbook):
        res = client.post("/watch/import-from-excel",
                         json={"workbook": str(fixture_workbook)})
        assert res.status_code == 200
        body = res.json()

        # 4 unique SECOP URLs across the 3 sheets:
        #   NTC.1111111 (sheets 1+2 → counts as 1)
        #   NTC.2222222 (sheet 1)
        #   NTC.3333333 (sheet 2)
        #   NTC.4444444 (sheet 3 — row-4 headers)
        assert body["added"] == 4
        assert body["skipped_dupe"] == 1   # the second NTC.1111111
        assert body["total"] == 4

    def test_per_sheet_counts(self, client, fixture_workbook):
        body = client.post("/watch/import-from-excel",
                          json={"workbook": str(fixture_workbook)}).json()
        per_sheet = body["per_sheet"]

        # Sheet 1: 2 SECOP URLs found (NTC.1111111 + NTC.2222222),
        # both new. The non-SECOP google URL never reaches stats[found].
        assert per_sheet["FEAB 2026"]["found"] == 2
        assert per_sheet["FEAB 2026"]["added"] == 2

        # Sheet 2: 2 found (NTC.1111111 dup + NTC.3333333 new)
        assert per_sheet["FEAB 2025"]["found"] == 2
        assert per_sheet["FEAB 2025"]["added"] == 1
        assert per_sheet["FEAB 2025"]["skipped_dupe"] == 1

        # Sheet 3: row-4 layout, 1 SECOP URL
        assert per_sheet["FEAB 2018-2021"]["found"] == 1
        assert per_sheet["FEAB 2018-2021"]["added"] == 1

    def test_running_twice_dedups_against_existing(
            self, client, fixture_workbook):
        first = client.post("/watch/import-from-excel",
                           json={"workbook": str(fixture_workbook)}).json()
        assert first["added"] == 4

        second = client.post("/watch/import-from-excel",
                            json={"workbook": str(fixture_workbook)}).json()
        # All 5 SECOP URL hits dedup against the existing watch list
        assert second["added"] == 0
        assert second["skipped_dupe"] >= 4
        assert second["total"] == 4

    def test_missing_workbook_returns_404(self, client, tmp_path):
        res = client.post("/watch/import-from-excel",
                         json={"workbook": str(tmp_path / "nope.xlsx")})
        assert res.status_code == 404

    def test_default_workbook_used_when_omitted(
            self, client, monkeypatch, tmp_path, fixture_workbook):
        # Point the default at our fixture
        from secop_ii import api as api_module
        monkeypatch.setattr(api_module, "_DEFAULT_WORKBOOK",
                           str(fixture_workbook))
        res = client.post("/watch/import-from-excel", json={})
        assert res.status_code == 200
        assert res.json()["added"] == 4

    def test_persists_to_watched_urls_json(
            self, client, fixture_workbook, monkeypatch, tmp_path):
        from secop_ii import api as api_module
        client.post("/watch/import-from-excel",
                   json={"workbook": str(fixture_workbook)})

        # Re-read the watch endpoint and confirm the items are there
        items = client.get("/watch").json()["items"]
        assert len(items) == 4
        pids = {it["process_id"] for it in items}
        assert pids == {
            "CO1.NTC.1111111", "CO1.NTC.2222222",
            "CO1.NTC.3333333", "CO1.NTC.4444444",
        }
        # Each note should record which sheet it came from
        sheet_notes = {it["note"] for it in items}
        assert any("FEAB 2026" in n for n in sheet_notes)
        assert any("FEAB 2018-2021" in n for n in sheet_notes)
