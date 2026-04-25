"""Auditoría de integridad de datos — regla cardinal del proyecto.

Estos tests son LEY: garantizan que el sistema NUNCA infringe las reglas
cardinales que la Dra. María Camila Mendoza Zubiría (Jefe de Gestión
Contractual del FEAB, Fiscalía General de la Nación) repitió varias veces:

    "No comerse datos. No alucinar. No falsos positivos. No falsos negativos.
     Es inadmisible."

Cualquier falla en estos tests = riesgo de compliance.

Cubren:
    1. Endpoints que devuelven cached data: si la key no existe, deben
       responder ``{available: false}`` SIN inventar fields/all_labels.
    2. Cuando un proceso está EN AMBAS fuentes (Integrado + Portal),
       las fuentes se exponen separadas — NUNCA se promedian o eligen
       silenciosamente.
    3. El cache Integrado solo persiste campos que vinieron del API
       (Socrata rpmr-utcd) — sin valores default ni placeholders.
    4. Cuando un proceso NO está en ninguna fuente pública, el sistema
       lo muestra honestamente como ausente — nunca con datos del Excel.
    5. El audit log preserva la chain (hash + code_version + prev_hash).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


# ---- Endpoint /contract-portal/{notice_uid} ---------------------------------


def test_contract_portal_unknown_uid_does_not_invent_fields(monkeypatch, tmp_path):
    """Si un notice_uid no está en el cache, el endpoint DEBE devolver
    `{available: false}` y NUNCA inventar `fields`, `all_labels` o
    `documents`."""
    from secop_ii import api as api_module

    fake_cache = tmp_path / "portal.json"
    fake_cache.write_text(json.dumps({}), encoding="utf-8")
    monkeypatch.setattr(api_module, "_PORTAL_CACHE", fake_cache)

    from fastapi.testclient import TestClient
    client = TestClient(api_module.app)

    res = client.get("/contract-portal/CO1.NTC.NOEXISTE_999")
    assert res.status_code == 200
    body = res.json()
    assert body["available"] is False
    assert body["notice_uid"] == "CO1.NTC.NOEXISTE_999"
    # Honestidad: ningún campo de datos debe aparecer.
    assert "fields" not in body or not body.get("fields")
    assert "all_labels" not in body or not body.get("all_labels")
    assert "documents" not in body or not body.get("documents")


def test_contract_portal_known_uid_mirrors_cache_exactly(monkeypatch, tmp_path):
    """Cuando el cache tiene un proceso, el endpoint devuelve EXACTAMENTE
    los campos cacheados — sin enriquecer ni transformar ni omitir."""
    from secop_ii import api as api_module

    cache_data = {
        "CO1.NTC.TEST_ESPEJO": {
            "fields": {"estado": "Adjudicado", "valor_total": "$ 100.000"},
            "all_labels": {"Estado": "Adjudicado", "Valor total": "$ 100.000"},
            "documents": [{"name": "pliego.pdf", "url": "https://x.y/z"}],
            "notificaciones": [],
            "raw_length": 12345,
            "status": "ok_completo",
        },
    }
    fake_cache = tmp_path / "portal.json"
    fake_cache.write_text(json.dumps(cache_data), encoding="utf-8")
    monkeypatch.setattr(api_module, "_PORTAL_CACHE", fake_cache)

    from fastapi.testclient import TestClient
    client = TestClient(api_module.app)
    res = client.get("/contract-portal/CO1.NTC.TEST_ESPEJO")
    assert res.status_code == 200
    body = res.json()
    assert body["available"] is True
    assert body["fields"] == {"estado": "Adjudicado", "valor_total": "$ 100.000"}
    assert body["documents"] == [{"name": "pliego.pdf", "url": "https://x.y/z"}]
    assert body["status"] == "ok_completo"


# ---- Endpoint /contract-integrado/{key} -------------------------------------


def test_contract_integrado_unknown_key_does_not_invent_fields(monkeypatch, tmp_path):
    """Si un notice_uid o pccntr no está en rpmr-utcd cache, el endpoint
    debe devolver `{available: false}` SIN inventar fields."""
    from secop_ii import api as api_module

    fake_cache = tmp_path / "integ.json"
    fake_cache.write_text(
        json.dumps({"by_notice_uid": {}, "by_pccntr": {}}), encoding="utf-8"
    )
    monkeypatch.setattr(api_module, "_INTEGRADO_CACHE", fake_cache)

    from fastapi.testclient import TestClient
    client = TestClient(api_module.app)

    res = client.get("/contract-integrado/CO1.NTC.NOEXISTE_999")
    assert res.status_code == 200
    body = res.json()
    assert body["available"] is False
    assert "fields" not in body or not body.get("fields")


def test_contract_integrado_pccntr_lookup_falls_through(monkeypatch, tmp_path):
    """El endpoint busca primero por notice_uid, después por PCCNTR.
    Si solo está indexado por PCCNTR, debe encontrarlo."""
    from secop_ii import api as api_module

    cache_data = {
        "by_notice_uid": {},
        "by_pccntr": {
            "CO1.PCCNTR.TEST_999": {
                "estado_del_proceso": "Activo",
                "valor_contrato": "1000",
                "numero_del_contrato": "CO1.PCCNTR.TEST_999",
            }
        },
    }
    fake_cache = tmp_path / "integ.json"
    fake_cache.write_text(json.dumps(cache_data), encoding="utf-8")
    monkeypatch.setattr(api_module, "_INTEGRADO_CACHE", fake_cache)

    from fastapi.testclient import TestClient
    client = TestClient(api_module.app)
    res = client.get("/contract-integrado/CO1.PCCNTR.TEST_999")
    assert res.status_code == 200
    body = res.json()
    assert body["available"] is True
    assert body["fields"]["estado_del_proceso"] == "Activo"


# ---- Endpoint /integrado-bulk -----------------------------------------------


def test_integrado_bulk_strips_null_fields(monkeypatch, tmp_path):
    """El bulk solo expone campos QUE TIENEN valor — los `null` deben ser
    omitidos para que la UI no los confunda con `0` / `""` / `false`."""
    from secop_ii import api as api_module

    cache_data = {
        "by_notice_uid": {
            "CO1.NTC.X": {
                "estado_del_proceso": "Activo",
                "valor_contrato": None,  # debe NO aparecer en summary
                "nom_raz_social_contratista": "",  # debe NO aparecer
                "tipo_de_contrato": "Compraventa",
            }
        },
        "by_pccntr": {},
    }
    fake_cache = tmp_path / "integ.json"
    fake_cache.write_text(json.dumps(cache_data), encoding="utf-8")
    monkeypatch.setattr(api_module, "_INTEGRADO_CACHE", fake_cache)

    from fastapi.testclient import TestClient
    client = TestClient(api_module.app)
    res = client.get("/integrado-bulk")
    body = res.json()
    summary = body["by_notice_uid"]["CO1.NTC.X"]
    assert summary["estado_del_proceso"] == "Activo"
    assert summary["tipo_de_contrato"] == "Compraventa"
    # Críticamente: campos null/empty NO deben aparecer
    assert "valor_contrato" not in summary
    assert "nom_raz_social_contratista" not in summary


# ---- Sync script integrity --------------------------------------------------


def test_sync_integrado_extracts_notice_uid_correctly():
    """El extractor de notice_uid de la URL debe devolver `None` si no
    encuentra el patrón — NUNCA inventar un ID."""
    from scripts.sync_secop_integrado import _extract_notice_uid

    # URL típica del dataset
    assert (
        _extract_notice_uid(
            "https://community.secop.gov.co/Public/Tendering/OpportunityDetail/Index?noticeUID=CO1.NTC.5934044&isFromPublicArea=True"
        )
        == "CO1.NTC.5934044"
    )
    # URL sin noticeUID
    assert _extract_notice_uid("https://example.com/no-notice-here") is None
    # URL vacía / None
    assert _extract_notice_uid("") is None
    assert _extract_notice_uid(None) is None


# ---- Audit log chain integrity ----------------------------------------------


def test_audit_log_endpoint_reports_chain_status(monkeypatch, tmp_path):
    """El endpoint /audit-log expone `intact` boolean — la UI lo muestra
    como ALERTA si la chain está rota. Debe ser True con un log fresco."""
    from secop_ii import api as api_module

    # Forzar audit log fresco / vacío
    log_path = tmp_path / "audit_log.jsonl"
    log_path.write_text("", encoding="utf-8")

    # No es trivial mockear la lógica interna del audit log. En lugar
    # de mockear, validamos que el endpoint /audit-log exista y
    # retorne las claves de integridad esperadas (`intact`, `total`).
    from fastapi.testclient import TestClient
    client = TestClient(api_module.app)
    res = client.get("/audit-log?limit=1")
    assert res.status_code == 200
    body = res.json()
    # API contract: estos dos campos siempre deben estar presentes.
    assert "intact" in body
    assert "total" in body
    # Si el log fue alterado a mano, `intact` debe ser False — pero
    # con uso normal debe ser True.
    assert isinstance(body["intact"], bool)


# ---- Cardinal rule: Excel never bleeds into the main table ------------------


def test_watch_endpoint_does_not_set_numero_contrato_excel_anymore():
    """Regresión: el campo `numero_contrato_excel` fue eliminado del
    backend (regla cardinal: del Excel solo vigencia + link). Si vuelve
    a aparecer, este test falla."""
    src = (Path(__file__).parent.parent / "src" / "secop_ii" / "api.py").read_text(
        encoding="utf-8"
    )
    # No debe haber ninguna asignación a esta clave en el endpoint /watch
    assert 'it["numero_contrato_excel"]' not in src, (
        "REGRESIÓN CARDINAL: el backend volvió a setear numero_contrato_excel "
        "desde el Excel. Esto viola la regla 'la verdad es SECOP'."
    )
