"""Tests del parser HTML del scraper portal SECOP.

Estos tests cubren el parser puro (`_extract_fields`, `_extract_documents`,
`_extract_notificaciones` y los helpers `_normalize_label` / `_clean_value`)
sin tocar la red ni Playwright. Usan fixtures HTML sintéticos en
``tests/fixtures/portal_html/`` que reproducen el layout Vortal del portal
SECOP II.

Filosofía cardinal: el parser es ESPEJO del HTML — nunca debe inventar
valores ausentes, nunca debe rellenar con `None` campos vacíos como si
fueran datos. Los tests verifican explícitamente:
- valores vacíos → no entran en `mapped` (el subset curado)
- placeholders de translator JS → se descartan
- etiquetas ruidosas (sí/no/asterisco/vacío) → se ignoran
- documentos duplicados → se deduplican por nombre
- filas no-notificación → se ignoran en `_extract_notificaciones`
"""
from __future__ import annotations

from pathlib import Path

import pytest

from secop_ii.portal_scraper import (
    _clean_value,
    _extract_documents,
    _extract_fields,
    _extract_notificaciones,
    _normalize_label,
)

FIXTURES = Path(__file__).parent / "fixtures" / "portal_html"


@pytest.fixture(scope="module")
def sample_html() -> str:
    return (FIXTURES / "sample_complete.html").read_text(encoding="utf-8")


# ---- _normalize_label -------------------------------------------------------


def test_normalize_label_strips_accents_and_colon():
    assert _normalize_label("Número del proceso:") == "Numero del proceso"
    assert _normalize_label("  Título  ") == "Titulo"
    assert _normalize_label("Descripción:") == "Descripcion"


def test_normalize_label_handles_empty():
    assert _normalize_label("") == ""
    assert _normalize_label("   ") == ""


# ---- _clean_value -----------------------------------------------------------


def test_clean_value_collapses_whitespace_and_nbsp():
    assert _clean_value("foo   bar") == "foo bar"
    assert _clean_value("a\nb") == "a | b"
    assert _clean_value("  x  y  ") == "x y"


def test_clean_value_drops_translator_js_placeholder():
    assert _clean_value("translator.loadFile('xx')") == ""
    assert _clean_value("xxx loadFileAndTranslate yyy") == ""


# ---- _extract_fields --------------------------------------------------------


def test_extract_fields_finds_curated_subset(sample_html: str):
    all_labels, mapped = _extract_fields(sample_html)
    # Some curated keys must be present
    assert mapped.get("numero_proceso") == "FEAB-LP-2024-001"
    assert mapped.get("titulo") == "Adquisición de bienes para el FEAB"
    assert mapped.get("tipo_proceso") == "Licitación pública"
    assert mapped.get("estado") == "Adjudicado"
    assert mapped.get("fase") == "Ejecución"
    assert mapped.get("valor_total") == "$ 250.000.000,00"
    assert mapped.get("fecha_firma_contrato") == "2024-08-15"


def test_extract_fields_dumps_all_labels_for_audit(sample_html: str):
    all_labels, _mapped = _extract_fields(sample_html)
    # all_labels should include every meaningful label, even ones not in the curated map
    assert "Numero del proceso" in all_labels
    assert "Codigo UNSPSC" in all_labels
    assert "Direccion de ejecucion del contrato" in all_labels


def test_extract_fields_skips_empty_values_in_mapped(sample_html: str):
    """Justificación de la modalidad has empty <td> in fixture — must not
    appear in `mapped` (the curated subset). The parser would lie if it
    pretended an empty value was data."""
    _all, mapped = _extract_fields(sample_html)
    assert "justificacion_modalidad" not in mapped


def test_extract_fields_drops_translator_js_placeholder(sample_html: str):
    _all, mapped = _extract_fields(sample_html)
    # Lotes? has translator.loadFile placeholder — must be dropped
    assert "lotes" not in mapped


def test_extract_fields_ignores_noise_labels(sample_html: str):
    all_labels, _mapped = _extract_fields(sample_html)
    # "Sí" and "*" are noise (radio button labels) — must NOT be in all_labels
    # (the parser strips them via _NOISE_LABELS).
    assert "Si" not in all_labels  # normalized form
    assert "*" not in all_labels


# ---- _extract_documents -----------------------------------------------------


def test_extract_documents_returns_name_and_url(sample_html: str):
    docs = _extract_documents(sample_html)
    assert any(
        d["name"] == "Pliego_definitivo.pdf"
        and "documentFileId=12345" in d["url"]
        for d in docs
    )


def test_extract_documents_includes_mkey_when_present(sample_html: str):
    docs = _extract_documents(sample_html)
    adenda = next(d for d in docs if d["name"] == "Adenda_01.pdf")
    assert "mkey=abc123def4" in adenda["url"]
    assert "documentFileId=67890" in adenda["url"]


def test_extract_documents_dedupes_by_name(sample_html: str):
    """Pliego_definitivo.pdf appears twice in the fixture — parser must
    keep only the first occurrence."""
    docs = _extract_documents(sample_html)
    pliego_count = sum(1 for d in docs if d["name"] == "Pliego_definitivo.pdf")
    assert pliego_count == 1


def test_extract_documents_uses_https_community_secop_prefix(sample_html: str):
    docs = _extract_documents(sample_html)
    for d in docs:
        if d["url"]:
            assert d["url"].startswith("https://community.secop.gov.co/Public/Tendering/")


# ---- _extract_notificaciones ------------------------------------------------


def test_extract_notificaciones_parses_rows(sample_html: str):
    notifs = _extract_notificaciones(sample_html)
    assert len(notifs) == 2
    first = notifs[0]
    assert first["proceso"] == "FEAB-LP-2024-001"
    assert first["evento"] == "Publicación inicial"
    assert first["fecha"] == "15/07/2024 10:30 AM"


def test_extract_notificaciones_pulls_date_from_merged_event(sample_html: str):
    """When the event cell has the date inlined, parser splits them."""
    notifs = _extract_notificaciones(sample_html)
    second = notifs[1]
    assert second["evento"] == "Adenda 01 publicada"
    assert second["fecha"] == "22/07/2024 03:15 PM"


def test_extract_notificaciones_skips_non_notification_rows(sample_html: str):
    """Row with first cell != 'Notificación' must be skipped."""
    notifs = _extract_notificaciones(sample_html)
    # Only 2 valid rows in the fixture; 'Otro' row must NOT make it in.
    assert all(n["proceso"] != "x" for n in notifs)
    assert len(notifs) == 2


# ---- Edge cases -------------------------------------------------------------


def test_extract_fields_empty_html_returns_empty():
    all_labels, mapped = _extract_fields("<html><body></body></html>")
    assert all_labels == {}
    assert mapped == {}


def test_extract_documents_empty_html_returns_empty():
    assert _extract_documents("<html><body></body></html>") == []


def test_extract_notificaciones_empty_html_returns_empty():
    assert _extract_notificaciones("<html><body></body></html>") == []
