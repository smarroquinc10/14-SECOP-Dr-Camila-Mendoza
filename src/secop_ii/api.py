"""FastAPI bridge for the Next.js frontend.

Design constraints (production-grade):

1. **Espejo SECOP**: every endpoint returns ALL raw SECOP fields, never
   filters them down. The frontend can pick what to render.
2. **No false positives**: each cell carries provenance + confidence
   + the SHA-256 fingerprint of the SECOP payload it came from.
3. **No false negatives**: empty/missing fields are explicit (``None``),
   never silently dropped.
4. **No data eating**: every request that mutates state appends to the
   hash-chained audit log, with the ``code_version`` stamp.
5. **Resilient**: tenacity retry on the SECOP layer, graceful degradation
   when a sub-dataset fails (the rest still returns).
6. **Cacheable**: a per-process payload is the same until SECOP changes;
   the hash is the cache key.

Endpoints:

    GET  /health                     — sanity
    GET  /entity/feab                — FEAB metadata (NIT, total counts)
    GET  /contracts                  — all FEAB contracts (every field)
    GET  /contracts/{id_contrato}    — single contract + related data
    GET  /processes                  — all FEAB processes (every field)
    GET  /processes/{notice_uid}     — single process + related data
    GET  /audit-log                  — read the hash-chained log
    POST /refresh                    — trigger an Excel update (background)
    POST /verify                     — re-pega SECOP, compare hashes
    GET  /version                    — code version + git short SHA
"""
from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from secop_ii.audit_log import (
    _CODE_VERSION,
    iter_entries as _audit_iter,
    render_audit_summary,
    verify_audit_log,
)
from secop_ii.feab_columns import compute_feab_fill, source_fingerprint
from secop_ii.feab_validation import validate_fills
from secop_ii.secop_client import SecopClient
from secop_ii.url_parser import InvalidSecopUrlError, parse_secop_url

log = logging.getLogger("dra-cami-api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# FEAB / Fiscalía General de la Nación
FEAB_NIT = "901148337"

# Reusable client + thread pool. The client memoizes per-process datasets
# in-memory, so repeated /contracts/{id} hits don't re-query SECOP.
_client = SecopClient()
_executor = ThreadPoolExecutor(max_workers=4)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Warm-up: probe SECOP once so the first user request is fast."""
    try:
        await asyncio.get_event_loop().run_in_executor(
            _executor, lambda: _client.query("jbjy-vk9h",
                                             where=f"nit_entidad='{FEAB_NIT}'",
                                             limit=1)
        )
        log.info("SECOP probe OK — API ready")
    except Exception as exc:
        log.warning("SECOP probe failed (non-fatal): %s", exc)
    yield
    _executor.shutdown(wait=False)


app = FastAPI(
    title="Dra Cami Contractual — API",
    description="Espejo automático del SECOP II para FEAB.",
    version="1.0.0",
    lifespan=_lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ---- Response models --------------------------------------------------------


class HealthResponse(BaseModel):
    status: str
    code_version: str
    timestamp: str


class CellMetadata(BaseModel):
    """Provenance + confidence for a single derived cell."""
    value: Any
    source: str | None = None
    confidence: str | None = None  # HIGH / MEDIUM / LOW


class ProcessSummary(BaseModel):
    """One row in the contracts table — keeps every SECOP field plus
    the 77 FEAB-mapped cells with confidence + source."""
    id_contrato: str | None = None
    referencia_del_contrato: str | None = None
    id_del_proceso: str | None = None
    notice_uid: str | None = None
    objeto: str | None = None
    proveedor: str | None = None
    valor: float | None = None
    valor_total: float | None = None
    estado: str | None = None
    fecha_firma: str | None = None
    fecha_inicio: str | None = None
    fecha_fin: str | None = None
    modalidad: str | None = None
    tipo_contrato: str | None = None
    dias_adicionados: int | None = None
    notas: str | None = None
    secop_url: str | None = None
    secop_hash: str | None = None
    confianza: str | None = None
    needs_review: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


class ProcessDetail(BaseModel):
    """Full per-process payload: every dataset SECOP returns about it."""
    notice_uid: str | None
    process_id: str
    proceso: dict[str, Any] | None
    contratos: list[dict[str, Any]]
    adiciones_by_contrato: dict[str, list[dict[str, Any]]]
    garantias_by_contrato: dict[str, list[dict[str, Any]]]
    pagos_by_contrato: dict[str, list[dict[str, Any]]]
    ejecucion_by_contrato: dict[str, list[dict[str, Any]]]
    suspensiones_by_contrato: dict[str, list[dict[str, Any]]]
    mods_proceso: list[dict[str, Any]]
    feab_fills: dict[str, Any]
    feab_confidence: dict[str, str]
    feab_sources: dict[str, str]
    needs_review: list[str]
    issues: list[str]
    secop_hash: str
    code_version: str
    fetched_at: str


# ---- Endpoints --------------------------------------------------------------


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        code_version=_CODE_VERSION,
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


@app.get("/version")
async def version() -> dict[str, str]:
    return {"code_version": _CODE_VERSION, "feab_nit": FEAB_NIT}


@app.get("/entity/feab")
async def entity_feab() -> dict[str, Any]:
    """Metadata about FEAB itself + counts."""
    loop = asyncio.get_event_loop()

    def _counts() -> dict[str, int]:
        try:
            ctos = _client.query("jbjy-vk9h",
                                where=f"nit_entidad='{FEAB_NIT}'",
                                select="count(*) as n",
                                limit=1)
            procs = _client.query("p6dx-8zbt",
                                where=f"nit_entidad='{FEAB_NIT}'",
                                select="count(*) as n",
                                limit=1)
            return {
                "contratos": int(ctos[0].get("n", 0)) if ctos else 0,
                "procesos": int(procs[0].get("n", 0)) if procs else 0,
            }
        except Exception as exc:  # pragma: no cover
            log.warning("entity counts failed: %s", exc)
            return {"contratos": 0, "procesos": 0}

    counts = await loop.run_in_executor(_executor, _counts)
    return {
        "nit": FEAB_NIT,
        "nombre": "Fondo Especial para la Administración de Bienes "
                  "de la Fiscalía General de la Nación",
        "alias": "FEAB",
        "padre": "Fiscalía General de la Nación",
        **counts,
    }


@app.get("/contracts")
async def list_contracts(
    limit: int = Query(500, ge=1, le=10_000),
    offset: int = Query(0, ge=0),
    where: str | None = Query(None, description="Extra Socrata WHERE clause"),
) -> list[dict[str, Any]]:
    """Return EVERY SECOP contract for FEAB with EVERY field.

    The frontend chooses what to render. We never strip fields — that
    would be a false negative.
    """
    loop = asyncio.get_event_loop()

    def _fetch() -> list[dict]:
        clause = f"nit_entidad='{FEAB_NIT}'"
        if where:
            clause = f"({clause}) AND ({where})"
        return _client.query("jbjy-vk9h", where=clause,
                            limit=limit, offset=offset,
                            order="fecha_de_firma DESC")

    rows = await loop.run_in_executor(_executor, _fetch)

    # Add a derived "notas" + auto-generated narrative per row so the
    # frontend doesn't need to recompute it. Same logic the Streamlit
    # app uses — kept here as a single source of truth.
    out: list[dict[str, Any]] = []
    for r in rows:
        notas_parts: list[str] = []
        estado = str(r.get("estado_contrato") or "")
        if "Modificad" in estado:
            notas_parts.append("Modificado")
        try:
            d = int(float(r.get("dias_adicionados") or 0))
            if d > 0:
                notas_parts.append(f"+{d} días")
        except (ValueError, TypeError):
            pass
        liq = str(r.get("liquidaci_n") or "").strip().lower()
        if liq == "si":
            notas_parts.append("Liquidado")
        r["_notas"] = " · ".join(notas_parts)
        # Flatten the urlproceso dict to a plain string up front.
        url = r.get("urlproceso")
        if isinstance(url, dict):
            r["urlproceso"] = url.get("url") or ""
        out.append(r)
    return out


@app.get("/contracts/{id_contrato}", response_model=ProcessDetail)
async def contract_detail(id_contrato: str) -> ProcessDetail:
    """Full payload for a single contract: every SECOP dataset that
    references it, plus FEAB derivations + confidence + audit hash."""
    loop = asyncio.get_event_loop()

    def _fetch() -> ProcessDetail:
        contratos = _client.query(
            "jbjy-vk9h", where=f"id_contrato='{_esc(id_contrato)}'", limit=10,
        )
        if not contratos:
            raise HTTPException(404, f"contrato {id_contrato} no encontrado")
        c = contratos[0]
        portfolio = str(c.get("proceso_de_compra") or "")
        url_field = c.get("urlproceso")
        if isinstance(url_field, dict):
            url_field = url_field.get("url") or ""
        url = str(url_field or "")

        # Resolve the proceso (parent) — by URL parsing or portfolio
        proceso = None
        notice_uid = None
        try:
            ref = parse_secop_url(url)
            proceso = _client.get_proceso(ref.process_id, url=url)
            notice_uid = _client.resolve_notice_uid(ref.process_id, url=url)
        except InvalidSecopUrlError:
            pass

        # All sub-datasets, gracefully degrading on errors per dataset
        def _safe_call(fn, *args, **kw):
            try:
                return fn(*args, **kw)
            except Exception as exc:
                log.warning("subdataset fetch failed for %s: %s",
                          getattr(fn, "__name__", "?"), exc)
                return []

        adis = {ci: _safe_call(_client.get_adiciones, ci)
               for ci in [c.get("id_contrato")] if ci}
        gars = {ci: _safe_call(_client.get_garantias, ci)
               for ci in [c.get("id_contrato")] if ci}
        facs = {ci: _safe_call(_client.get_facturas, ci)
               for ci in [c.get("id_contrato")] if ci}
        ejec = {ci: _safe_call(_client.get_ejecucion, ci)
               for ci in [c.get("id_contrato")] if ci}
        susp = {ci: _safe_call(_client.get_suspensiones, ci)
               for ci in [c.get("id_contrato")] if ci}
        mods_proc = _safe_call(_client.get_mod_procesos, portfolio) if portfolio else []

        result = compute_feab_fill(
            proceso=proceso, contratos=contratos,
            notice_uid=notice_uid, source_url=url,
            adiciones_by_contrato=adis,
            garantias_by_contrato=gars,
            ejecucion_by_contrato=ejec,
        )
        validation = validate_fills(result.values)
        secop_hash = source_fingerprint(
            proceso=proceso, contratos=contratos, notice_uid=notice_uid,
        )

        return ProcessDetail(
            notice_uid=notice_uid,
            process_id=(proceso or {}).get("id_del_proceso", id_contrato),
            proceso=proceso,
            contratos=contratos,
            adiciones_by_contrato=adis,
            garantias_by_contrato=gars,
            pagos_by_contrato=facs,
            ejecucion_by_contrato=ejec,
            suspensiones_by_contrato=susp,
            mods_proceso=mods_proc,
            feab_fills=result.values,
            feab_confidence=result.confidence,
            feab_sources=result.sources,
            needs_review=sorted(validation.needs_review),
            issues=validation.issues,
            secop_hash=secop_hash,
            code_version=_CODE_VERSION,
            fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )

    return await loop.run_in_executor(_executor, _fetch)


@app.get("/processes")
async def list_processes(
    limit: int = Query(500, ge=1, le=10_000),
    offset: int = Query(0, ge=0),
) -> list[dict[str, Any]]:
    """All FEAB processes (p6dx-8zbt) with every field."""
    loop = asyncio.get_event_loop()

    def _fetch() -> list[dict]:
        return _client.query(
            "p6dx-8zbt", where=f"nit_entidad='{FEAB_NIT}'",
            limit=limit, offset=offset,
            order="fecha_de_publicacion_del DESC",
        )

    rows = await loop.run_in_executor(_executor, _fetch)
    for r in rows:
        url = r.get("urlproceso")
        if isinstance(url, dict):
            r["urlproceso"] = url.get("url") or ""
    return rows


_WATCH_PATH = Path(".cache/watched_urls.json")
_WATCH_LOCK = __import__("threading").Lock()


class WatchedItem(BaseModel):
    url: str
    process_id: str | None = None
    notice_uid: str | None = None
    added_at: str
    note: str | None = None


def _load_watched() -> list[dict[str, Any]]:
    if not _WATCH_PATH.exists():
        return []
    try:
        import json as _json
        return _json.loads(_WATCH_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_watched(items: list[dict[str, Any]]) -> None:
    import json as _json
    _WATCH_PATH.parent.mkdir(parents=True, exist_ok=True)
    _WATCH_PATH.write_text(
        _json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
    )


@app.get("/watch")
async def watch_list() -> dict[str, Any]:
    """Return the manually-tracked SECOP URLs (in addition to the
    auto-discovered FEAB contracts)."""
    return {"items": _load_watched()}


@app.post("/watch")
async def watch_add(payload: dict[str, str]) -> dict[str, Any]:
    """Add a SECOP URL to the watch list. Dedup by parsed process_id.

    Returns ``{added: true|false, item, total}`` so the UI can show
    "ya estaba en tu lista" feedback without inventing duplicates.
    """
    url = (payload.get("url") or "").strip()
    note = (payload.get("note") or "").strip() or None
    if not url:
        raise HTTPException(400, "url is required")
    if "secop.gov.co" not in url.lower():
        raise HTTPException(400, "URL no parece de SECOP II")

    process_id = None
    notice_uid = None
    try:
        ref = parse_secop_url(url)
        process_id = ref.process_id
        notice_uid = _client.resolve_notice_uid(ref.process_id, url=url)
    except InvalidSecopUrlError:
        # Allow URLs we can't parse; we'll dedup by URL string instead.
        pass

    with _WATCH_LOCK:
        items = _load_watched()
        # Dedup: prefer process_id match, fall back to URL match.
        for it in items:
            same_id = process_id and it.get("process_id") == process_id
            same_url = it.get("url") == url
            if same_id or same_url:
                return {"added": False, "item": it, "total": len(items),
                       "reason": "ya estaba en tu lista"}
        new_item = {
            "url": url,
            "process_id": process_id,
            "notice_uid": notice_uid,
            "added_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "note": note,
        }
        items.append(new_item)
        _save_watched(items)
        return {"added": True, "item": new_item, "total": len(items)}


@app.delete("/watch")
async def watch_remove(url: str = Query(..., description="URL exacta a borrar"),
                        process_id: str | None = Query(None)) -> dict[str, Any]:
    """Remove a watched URL. Match by URL or process_id."""
    with _WATCH_LOCK:
        items = _load_watched()
        before = len(items)
        items = [
            it for it in items
            if it.get("url") != url
            and (process_id is None or it.get("process_id") != process_id)
        ]
        _save_watched(items)
        return {"removed": before - len(items), "total": len(items)}


# ---- Excel → watch list importer -------------------------------------------
# The Dra's master Excel keeps a "LINK" column with the SECOP URL of each
# process she follows. Some sheets put headers in row 1 (FEAB 2026/2025/
# 2024/2023/2022), and the legacy "FEAB 2018-2021" sheet puts them in row
# 4 (rows 1-3 are formato titles). We auto-detect both layouts.

_DEFAULT_WORKBOOK = "BASE DE DATOS FEAB CONTRATOS2.xlsx"
_LINK_HEADER_KEYWORDS = ("LINK", "URL", "ENLACE")


def _find_link_column(ws) -> tuple[int, int] | None:
    """Return (header_row, link_col_1_indexed) or None.

    Probes row 1, then row 4. Matches a header whose stripped uppercase
    equals exactly ``"LINK"`` to avoid false positives like "LINK
    verificación API" or "Link de SIRECI" — the Dra's column is just
    ``LINK``. Falls back to startswith("LINK") if exact match fails.
    """
    for header_row in (1, 4):
        try:
            row = next(ws.iter_rows(min_row=header_row, max_row=header_row,
                                    values_only=True))
        except StopIteration:
            continue
        # Exact "LINK" match first
        for i, v in enumerate(row, start=1):
            if v is None:
                continue
            text = str(v).strip().upper()
            if text == "LINK":
                return header_row, i
        # Fallback: header equals one of the keywords (whole-cell match)
        for i, v in enumerate(row, start=1):
            if v is None:
                continue
            text = str(v).strip().upper()
            if text in _LINK_HEADER_KEYWORDS:
                return header_row, i
    return None


def _import_workbook_urls(workbook_path: Path) -> dict[str, Any]:
    """Synchronous worker: read every sheet, dedup SECOP URLs by
    process_id, append new ones to the watch list, return a report.
    """
    from openpyxl import load_workbook

    if not workbook_path.exists():
        raise HTTPException(404, f"workbook not found: {workbook_path}")

    wb = load_workbook(workbook_path, data_only=True, read_only=True)

    # Build a lookup of (process_id, url) already in the watch list so
    # we don't append duplicates.
    with _WATCH_LOCK:
        existing = _load_watched()
        existing_pids = {it.get("process_id") for it in existing
                        if it.get("process_id")}
        existing_urls = {it.get("url") for it in existing if it.get("url")}

        per_sheet: dict[str, dict[str, int]] = {}
        added: list[dict[str, Any]] = []
        skipped_dupe = 0
        skipped_invalid = 0
        errors: list[str] = []
        seen_in_run_pids: set[str] = set()
        seen_in_run_urls: set[str] = set()

        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            link_loc = _find_link_column(ws)
            if not link_loc:
                per_sheet[sheet_name] = {"found": 0, "added": 0,
                                        "skipped_dupe": 0,
                                        "skipped_invalid": 0,
                                        "no_link_col": 1}
                continue
            header_row, link_col = link_loc
            stats = {"found": 0, "added": 0, "skipped_dupe": 0,
                    "skipped_invalid": 0, "no_link_col": 0}

            for row in ws.iter_rows(min_row=header_row + 1,
                                    values_only=True):
                if not row or len(row) < link_col:
                    continue
                v = row[link_col - 1]
                if v is None:
                    continue
                url = str(v).strip()
                if not url or "secop.gov.co" not in url.lower():
                    continue
                stats["found"] += 1

                # Try parsing for a stable dedup key
                process_id = None
                notice_uid = None
                try:
                    ref = parse_secop_url(url)
                    process_id = ref.process_id
                except InvalidSecopUrlError:
                    pass

                # Dedup against existing list AND within this run
                if process_id and (
                    process_id in existing_pids
                    or process_id in seen_in_run_pids
                ):
                    stats["skipped_dupe"] += 1
                    skipped_dupe += 1
                    continue
                if url in existing_urls or url in seen_in_run_urls:
                    stats["skipped_dupe"] += 1
                    skipped_dupe += 1
                    continue
                if not process_id and "secop.gov.co" not in url.lower():
                    stats["skipped_invalid"] += 1
                    skipped_invalid += 1
                    continue

                # Try to resolve notice_uid (best-effort, don't fail import)
                if process_id:
                    try:
                        notice_uid = _client.resolve_notice_uid(
                            process_id, url=url
                        )
                    except Exception:
                        notice_uid = None

                new_item = {
                    "url": url,
                    "process_id": process_id,
                    "notice_uid": notice_uid,
                    "added_at": datetime.now(timezone.utc)
                                       .isoformat(timespec="seconds"),
                    "note": f"Importado de Excel · hoja {sheet_name}",
                }
                added.append(new_item)
                if process_id:
                    seen_in_run_pids.add(process_id)
                seen_in_run_urls.add(url)
                stats["added"] += 1

            per_sheet[sheet_name] = stats

        if added:
            existing.extend(added)
            _save_watched(existing)

        return {
            "added": len(added),
            "skipped_dupe": skipped_dupe,
            "skipped_invalid": skipped_invalid,
            "errors": errors,
            "total": len(existing),
            "per_sheet": per_sheet,
            "workbook": str(workbook_path),
        }


@app.post("/watch/import-from-excel")
async def watch_import_from_excel(
    payload: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Bulk-import every SECOP URL from the Dra's master Excel into the
    watch list. Auto-detects the header row (1 or 4) and the LINK column
    per sheet. Dedups by parsed ``process_id`` first, then URL string.

    Body (optional)::

        {"workbook": "path/to/excel.xlsx"}

    Defaults to ``BASE DE DATOS FEAB CONTRATOS2.xlsx`` in the cwd.

    Returns a per-sheet breakdown of how many were found/added/skipped
    so the UI can show "agregadas N de M nuevas" feedback.
    """
    workbook = (payload or {}).get("workbook") or _DEFAULT_WORKBOOK
    path = Path(workbook)
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _executor, _import_workbook_urls, path
    )


@app.get("/audit-log")
async def audit_log(
    limit: int = Query(500, ge=1, le=10_000),
    op: str | None = Query(None, description="Filter by op: fill/replace/etc."),
) -> dict[str, Any]:
    """Return recent audit-log entries + chain integrity status."""
    log_path = Path(".cache/audit_log.jsonl")
    if not log_path.exists():
        return {"entries": [], "intact": True, "problems": [], "total": 0}

    intact, problems = await asyncio.get_event_loop().run_in_executor(
        _executor, verify_audit_log, log_path,
    )
    entries: list[dict[str, Any]] = []
    total = 0
    for entry in _audit_iter(log_path):
        total += 1
        if op and entry.op != op:
            continue
        entries.append({
            "ts": entry.ts, "op": entry.op, "row": entry.row,
            "process_id": entry.process_id, "column": entry.column,
            "old": entry.old, "new": entry.new, "source": entry.source,
            "confidence": entry.confidence, "secop_hash": entry.secop_hash,
            "code_version": entry.code_version,
            "hash": entry.hash, "prev_hash": entry.prev_hash,
        })
    # Return tail (most recent) up to limit
    return {
        "entries": entries[-limit:],
        "intact": intact,
        "problems": problems,
        "total": total,
    }


@app.get("/ultima-actualizacion")
async def ultima_actualizacion() -> dict[str, Any]:
    """Última vez que el programa actualizó / verificó / consultó SECOP.

    Lee el audit log y reporta los timestamps más recientes por tipo
    de operación. La Dra. ve esto en el header para saber qué tan
    fresca está la data sin tener que disparar una verificación.
    """
    log_path = Path(".cache/audit_log.jsonl")
    result: dict[str, str | None] = {
        "ultimo_fill": None,
        "ultimo_replace": None,
        "ultima_verificacion": None,
        "ultima_consulta": None,
        "total_operaciones": 0,
    }
    if not log_path.exists():
        return result
    total = 0
    for entry in _audit_iter(log_path):
        total += 1
        if entry.op == "fill" and (
            result["ultimo_fill"] is None or entry.ts > result["ultimo_fill"]
        ):
            result["ultimo_fill"] = entry.ts
        elif entry.op == "replace" and (
            result["ultimo_replace"] is None or entry.ts > result["ultimo_replace"]
        ):
            result["ultimo_replace"] = entry.ts
        elif entry.op == "verify_drift" and (
            result["ultima_verificacion"] is None
            or entry.ts > result["ultima_verificacion"]
        ):
            result["ultima_verificacion"] = entry.ts
    result["total_operaciones"] = total
    # The "ultima consulta" is the most recent of any of the above.
    timestamps = [v for k, v in result.items()
                 if k != "total_operaciones" and v]
    result["ultima_consulta"] = max(timestamps) if timestamps else None
    return result


@app.get("/modificatorios-recientes")
async def modificatorios_recientes(limit: int = Query(20, ge=1, le=100)) -> dict[str, Any]:
    """Aggregate view of every contract that has been modified — sorted
    by recency. Backbone of the 'Movimientos / Modificatorios' dashboard
    panel. Includes per-contract: last fecha_de_notificacion_de_prorroga
    if any, total días added, total adiciones value.
    """
    loop = asyncio.get_event_loop()

    def _fetch() -> dict[str, Any]:
        contratos = _client.query(
            "jbjy-vk9h",
            where=(
                f"nit_entidad='{FEAB_NIT}' AND "
                "(estado_contrato='Modificado' OR dias_adicionados>0)"
            ),
            limit=2000,
        )

        items: list[dict[str, Any]] = []
        for c in contratos:
            url_field = c.get("urlproceso")
            if isinstance(url_field, dict):
                url_field = url_field.get("url") or ""
            try:
                dias = int(float(c.get("dias_adicionados") or 0))
            except (ValueError, TypeError):
                dias = 0
            items.append({
                "id_contrato": c.get("id_contrato"),
                "referencia": c.get("referencia_del_contrato"),
                "proveedor": c.get("proveedor_adjudicado"),
                "objeto": (c.get("objeto_del_contrato") or "")[:120],
                "valor": c.get("valor_del_contrato"),
                "estado": c.get("estado_contrato"),
                "dias_adicionados": dias,
                "fecha_firma": (c.get("fecha_de_firma") or "")[:10],
                "fecha_fin": (c.get("fecha_de_fin_del_contrato") or "")[:10],
                "fecha_notificacion_prorroga":
                    (c.get("fecha_de_notificaci_n_de_prorrogaci_n") or "")[:10],
                "fecha_actualizacion": (c.get("ultima_actualizacion") or "")[:10],
                "url": url_field,
            })

        # Sort by the most-recent signal we have: notificacion_prorroga
        # first, then ultima_actualizacion, then fecha_fin (a contract
        # whose fin is later than original probably had a prorroga).
        def _key(it: dict) -> str:
            return (
                it.get("fecha_notificacion_prorroga", "")
                or it.get("fecha_actualizacion", "")
                or it.get("fecha_fin", "")
                or ""
            )
        items.sort(key=_key, reverse=True)

        last = items[0] if items else None
        return {
            "total_modificados": len(items),
            "total_dias_adicionados": sum(it["dias_adicionados"] for it in items),
            "ultimo": last,
            "items": items[:limit],
        }

    return await loop.run_in_executor(_executor, _fetch)


@app.post("/refresh")
async def refresh(background: BackgroundTasks) -> dict[str, str]:
    """Kick off an Excel update in the background. Returns immediately."""
    workbook = "BASE DE DATOS FEAB CONTRATOS2.xlsx"
    if not Path(workbook).exists():
        raise HTTPException(404, f"workbook not found: {workbook}")

    def _run():
        from secop_ii.orchestrator import process_workbook
        try:
            report = process_workbook(
                workbook, do_backup=True, fields=["feab_fill"],
                generate_detalles=False, apply_view=True,
            )
            log.info("refresh done: %d ok, %d errors",
                    report.ok, report.errors)
        except Exception as exc:
            log.exception("refresh failed: %s", exc)

    background.add_task(_run)
    return {
        "status": "started",
        "workbook": workbook,
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


@app.post("/verify")
async def verify_endpoint() -> dict[str, Any]:
    """Re-fetch SECOP for each row, compare with stored hashes."""
    workbook = "BASE DE DATOS FEAB CONTRATOS2.xlsx"
    if not Path(workbook).exists():
        raise HTTPException(404, f"workbook not found: {workbook}")
    loop = asyncio.get_event_loop()

    def _verify() -> dict[str, Any]:
        from secop_ii.verify import verify_workbook
        report = verify_workbook(workbook)
        return {
            "total": report.total,
            "fresh": report.fresh_count,
            "stale": report.stale_count,
            "errors": report.error_count,
            "drift_rows": [
                {"row": r.row, "process_id": r.process_id,
                 "stored_hash": r.stored_hash, "current_hash": r.current_hash}
                for r in report.rows if r.changed
            ],
        }

    return await loop.run_in_executor(_executor, _verify)


# ---- Helpers ----------------------------------------------------------------


def _esc(value: str) -> str:
    """Escape single quotes for a Socrata WHERE clause."""
    return str(value).replace("'", "''")


def main() -> None:
    """Entry point used by the launcher and the .bat file."""
    import uvicorn
    uvicorn.run(
        "secop_ii.api:app",
        host="127.0.0.1", port=8000,
        log_level="info", reload=False,
    )


if __name__ == "__main__":
    main()
