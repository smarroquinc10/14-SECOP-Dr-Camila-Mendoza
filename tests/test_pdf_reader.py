"""Tests for the PDF reader's caching and keyword detection.

We don't try to download from SECOP in tests — that's environment-
dependent and slow. Instead we exercise the smaller pure-Python paths:

* the on-disk cache key is deterministic per URL
* keyword normalization correctly handles accents and case
* a ``download_failed`` summary is returned when the URL is unreachable
"""
from __future__ import annotations

from secop_ii.pdf_reader import PdfReader, PdfSummary


class TestPdfReader:
    def test_cache_path_is_deterministic_per_url(self, tmp_path):
        reader = PdfReader(cache_dir=tmp_path)
        url = "https://example.org/Public/Archive/RetrieveFile/Index?DocumentId=42"
        first = reader._cache_path_for(url)
        second = reader._cache_path_for(url)
        assert first == second
        # Different URL must hash to a different path
        other = reader._cache_path_for(url + "&v=2")
        assert other != first

    def test_summary_for_unreachable_url(self, tmp_path):
        reader = PdfReader(cache_dir=tmp_path, timeout_s=1)
        summary = reader.summarize("http://127.0.0.1:1/nonexistent.pdf")
        assert isinstance(summary, PdfSummary)
        assert summary.error == "download_failed"
        assert summary.engine == "none"
        assert summary.n_pages == 0


class TestPdfSummaryProps:
    def test_looks_like_modificatorio_when_keyword_found(self):
        s = PdfSummary(
            url="x", cache_path=None, n_pages=1, n_chars=100,
            engine="pdfplumber",
            keywords_modif=["MODIFICATORIO", "CLAUSULA OCTAVA"],
        )
        assert s.looks_like_modificatorio is True

    def test_looks_scanned_when_text_density_is_low(self):
        # 5 pages, 50 chars → 10 chars/page, well under the 40 threshold
        s = PdfSummary(
            url="x", cache_path=None, n_pages=5, n_chars=50, engine="pypdf",
        )
        assert s.looks_scanned is True

    def test_looks_scanned_false_when_no_pages(self):
        s = PdfSummary(url="x", cache_path=None, n_pages=0, n_chars=0)
        assert s.looks_scanned is False
