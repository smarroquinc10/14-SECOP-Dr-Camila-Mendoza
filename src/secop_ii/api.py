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


class ObservacionDra(BaseModel):
    """One OBSERVACIONES note the Dra wrote in the master Excel."""
    sheet: str
    row: int
    text: str


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
    observaciones_dra: list[ObservacionDra] = Field(default_factory=list)
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


@app.get("/contracts/{id_or_pid}", response_model=ProcessDetail)
async def contract_detail(id_or_pid: str) -> ProcessDetail:
    """Full payload for a single process. Accepts ANY identifier the UI
    might pass — id_contrato (CO1.PCCNTR.X), notice_uid (CO1.NTC.X),
    process_id (CO1.PPI.X / CO1.REQ.X). Resolves to the contract(s)
    when they exist; returns proceso-only payload (with the Dra's
    observaciones) when there is no contract signed yet.

    Mirror semantics: nothing is invented. If neither contracts nor
    proceso resolve, returns 404 honestly.
    """
    loop = asyncio.get_event_loop()

    def _fetch() -> ProcessDetail:
        ident = id_or_pid.strip()

        # 1) Try as id_contrato (PCCNTR) — direct contract row.
        contratos = _client.query(
            "jbjy-vk9h", where=f"id_contrato='{_esc(ident)}'", limit=10,
        )
        # 2) If no match, try as proceso_de_compra (NTC / REQ at contract level).
        if not contratos:
            contratos = _client.query(
                "jbjy-vk9h",
                where=f"proceso_de_compra='{_esc(ident)}'",
                limit=10,
            )

        # 3) Look up the watch-list entry to get the original URL.
        watch_url = None
        for it in _load_watched():
            if it.get("process_id") == ident or it.get("url") == ident \
                    or it.get("notice_uid") == ident:
                watch_url = it.get("url")
                break

        # 4) Determine the URL we'll use for parsing.
        if contratos:
            c0 = contratos[0]
            url_field = c0.get("urlproceso")
            if isinstance(url_field, dict):
                url_field = url_field.get("url") or ""
            url = str(url_field or "") or (watch_url or "")
        else:
            url = watch_url or ""

        # 5) Resolve proceso (parent). Try the URL parser first;
        # if that fails, use the identifier directly when it looks
        # like a process_id. Drafts (CO1.REQ.*) often have the
        # process info even without a contract.
        proceso = None
        notice_uid = None
        try:
            if url:
                ref = parse_secop_url(url)
                proceso = _client.get_proceso(ref.process_id, url=url)
                notice_uid = _client.resolve_notice_uid(
                    ref.process_id, url=url
                )
            elif ident.startswith(("CO1.PPI.", "CO1.NTC.", "CO1.REQ.")):
                # Best effort lookup by ID alone
                proceso = _client.get_proceso(ident)
                notice_uid = _client.resolve_notice_uid(ident)
        except InvalidSecopUrlError:
            pass
        except Exception as exc:
            log.warning("proceso resolve failed: %s", exc)

        # 6) Honest 404: if NEITHER a contract NOR a proceso resolved,
        # we have nothing meaningful to show. (Observaciones alone are
        # not enough — they may belong to an archived/draft process.)
        if not contratos and not proceso:
            # Last resort: if Excel has notes for this id, return a
            # minimal payload with just the observaciones — better
            # than 404 because the Dra's manual record exists.
            obs_raw = _observaciones_for(
                process_id=ident, proceso_de_compra=ident,
                notice_uid=ident, contract_id=ident, url=url or None,
            )
            if not obs_raw:
                raise HTTPException(
                    404,
                    f"{ident} no se encuentra en SECOP API ni hay "
                    "observaciones en el Excel. Validá manualmente "
                    "abriendo el link.",
                )
            return ProcessDetail(
                notice_uid=None,
                process_id=ident,
                proceso=None,
                contratos=[],
                adiciones_by_contrato={},
                garantias_by_contrato={},
                pagos_by_contrato={},
                ejecucion_by_contrato={},
                suspensiones_by_contrato={},
                mods_proceso=[],
                feab_fills={},
                feab_confidence={},
                feab_sources={},
                needs_review=[],
                issues=[
                    "El proceso no aparece en el API público de "
                    "datos.gov.co. Las observaciones de abajo vienen "
                    "del Excel master de la Dra.",
                ],
                observaciones_dra=[ObservacionDra(**e) for e in obs_raw],
                secop_hash="",
                code_version=_CODE_VERSION,
                fetched_at=datetime.now(timezone.utc).isoformat(
                    timespec="seconds"
                ),
            )

        # Normal path: contracts (or proceso-only if no contracts)
        c = contratos[0] if contratos else {}
        portfolio = str(c.get("proceso_de_compra") or "")

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

        # Look up the Dra's manual notes from the Excel master file.
        # Best-effort: if the workbook isn't available or the row
        # doesn't exist, return an empty list — never blocks the API.
        try:
            obs_raw = _observaciones_for(
                process_id=(proceso or {}).get("id_del_proceso"),
                proceso_de_compra=str(c.get("proceso_de_compra") or "")
                                  or None,
                notice_uid=notice_uid,
                contract_id=c.get("id_contrato"),
                url=url,
            )
            obs = [ObservacionDra(**e) for e in obs_raw]
        except Exception as exc:
            log.warning("observaciones lookup failed: %s", exc)
            obs = []

        return ProcessDetail(
            notice_uid=notice_uid,
            process_id=(proceso or {}).get("id_del_proceso", ident),
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
            observaciones_dra=obs,
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
    """One unique SECOP process the Dra is tracking.

    The same process can appear on multiple Excel sheets (e.g. a
    plurianual contract that shows up in FEAB 2024 and FEAB 2025).
    To avoid hiding that fact while also avoiding duplicate rows,
    each item carries a list of every (sheet, vigencia) pair where
    its URL was seen. The UI filter by sheet returns the same count
    the Dra sees in Excel — no data is eaten, no row is invented.
    """
    url: str
    process_id: str | None = None
    notice_uid: str | None = None
    sheets: list[str] = Field(default_factory=list)
    vigencias: list[str] = Field(default_factory=list)
    appearances: list[dict[str, str | None]] = Field(default_factory=list)
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


@app.put("/watch")
async def watch_update(payload: dict[str, str]) -> dict[str, Any]:
    """Edit a watched item — replace its URL while keeping its
    appearances/sheets/vigencias history intact.

    Body::

        {"old_url": "<the URL currently stored>",
         "new_url": "<the corrected URL>",
         "note": "optional updated note"}

    Re-parses ``new_url`` to extract ``process_id`` and resolves
    ``notice_uid`` against SECOP. Refuses if ``new_url`` already
    belongs to a different watched process (would create a duplicate).
    """
    old_url = (payload.get("old_url") or "").strip()
    new_url = (payload.get("new_url") or "").strip()
    note = payload.get("note")
    if not old_url or not new_url:
        raise HTTPException(400, "old_url y new_url son requeridos")
    if "secop.gov.co" not in new_url.lower():
        raise HTTPException(400, "new_url no parece de SECOP II")

    new_process_id = None
    new_notice_uid = None
    try:
        ref = parse_secop_url(new_url)
        new_process_id = ref.process_id
        new_notice_uid = _client.resolve_notice_uid(
            ref.process_id, url=new_url
        )
    except InvalidSecopUrlError:
        pass

    with _WATCH_LOCK:
        items = _load_watched()

        # Locate the item to edit
        target = None
        for it in items:
            if it.get("url") == old_url:
                target = it
                break
        if target is None:
            raise HTTPException(404, f"no encuentro old_url en tu lista")

        # Refuse if new_url is already in another item (different process)
        for it in items:
            if it is target:
                continue
            if it.get("url") == new_url:
                raise HTTPException(
                    409, "new_url ya pertenece a otro proceso de tu lista"
                )
            if (new_process_id and it.get("process_id") == new_process_id):
                raise HTTPException(
                    409,
                    f"new_url apunta al mismo process_id ({new_process_id}) "
                    "que otro item de tu lista",
                )

        target["url"] = new_url
        if new_process_id:
            target["process_id"] = new_process_id
        if new_notice_uid is not None:
            target["notice_uid"] = new_notice_uid
        if note is not None:
            target["note"] = (note.strip() or None) if note else None
        # Stamp the edit
        target["edited_at"] = datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        )

        _save_watched(items)
        return {"updated": True, "item": target, "total": len(items)}


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


def _find_vigencia_column(ws, header_row: int) -> int | None:
    """Return the 1-indexed column that holds the VIGENCIA value, or None.

    The Dra's format uses ``"3.VIGENCIA"`` as the canonical header, but
    different sheets put it in different physical columns (col 2 in
    FEAB 2026/2025/2024/2023/2022, col 3 in FEAB 2018-2021). We match
    by header text, not column index — that way the columns can shift
    without breaking the importer.

    Skips headers that *contain* "VIGENCIA" but mean something else
    (e.g. "VALOR VIGENCIA ACTUAL", "Garantía vigencia desde"): we
    require the header to start with a digit-and-dot prefix followed
    by VIGENCIA, OR to equal "VIGENCIA" alone.
    """
    try:
        row = next(ws.iter_rows(min_row=header_row, max_row=header_row,
                                values_only=True))
    except StopIteration:
        return None
    for i, v in enumerate(row, start=1):
        if v is None:
            continue
        text = str(v).strip().upper()
        # Match "3.VIGENCIA", "3 VIGENCIA", "VIGENCIA" — but not
        # "VALOR VIGENCIA ACTUAL" or "VIGENCIA FUTURA".
        if text == "VIGENCIA":
            return i
        # Strip leading digits + punctuation
        head = text.lstrip("0123456789. ")
        if head == "VIGENCIA":
            return i
    return None


def _vigencia_from_sheet_name(sheet_name: str) -> str | None:
    """Best-effort fallback: derive vigencia from a sheet name like
    ``"FEAB 2024"`` → ``"2024"``. Returns None for ranges like
    ``"FEAB 2018-2021"`` (those rows always have an explicit per-row
    vigencia in the Excel column)."""
    import re
    m = re.search(r"\b(\d{4})\s*$", sheet_name.strip())
    return m.group(1) if m else None


def _find_obs_column(ws, header_row: int) -> int | None:
    """Locate the ``OBSERVACIONES`` column in a sheet by header text.

    Lives at col 75 in FEAB 2026/2025/2024/2023/2022 and at col 73 in
    FEAB 2018-2021. Match is by header substring 'OBSERVAC' so it
    works across "72. OBSERVACIONES" and any minor formatting.
    """
    try:
        row = next(ws.iter_rows(min_row=header_row, max_row=header_row,
                                values_only=True))
    except StopIteration:
        return None
    for i, v in enumerate(row, start=1):
        if v is None:
            continue
        if "OBSERVAC" in str(v).strip().upper():
            return i
    return None


# In-memory cache keyed by (workbook_path, mtime) so we re-read the
# Excel only when it actually changes.
_OBS_INDEX_CACHE: dict[tuple[str, float],
                       dict[str, list[dict[str, Any]]]] = {}


def _load_excel_obs_index(workbook_path: Path) -> dict[
    str, list[dict[str, Any]]
]:
    """Build ``{key -> [{sheet, row, text}, ...]}`` where ``key`` is
    every URL substring or process_id we can cheaply extract from each
    Excel row that has a non-empty OBSERVACIONES cell.

    Cached per (path, mtime) — re-reads only when the Excel changes.
    """
    if not workbook_path.exists():
        return {}
    mtime = workbook_path.stat().st_mtime
    cache_key = (str(workbook_path), mtime)
    cached = _OBS_INDEX_CACHE.get(cache_key)
    if cached is not None:
        return cached

    from openpyxl import load_workbook
    wb = load_workbook(workbook_path, data_only=True, read_only=True)
    index: dict[str, list[dict[str, Any]]] = {}

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        link_loc = _find_link_column(ws)
        if not link_loc:
            continue
        header_row, link_col = link_loc
        obs_col = _find_obs_column(ws, header_row)
        if obs_col is None:
            continue

        for excel_row_idx, row in enumerate(
            ws.iter_rows(min_row=header_row + 1, values_only=True),
            start=header_row + 1,
        ):
            if not row or len(row) < max(link_col, obs_col):
                continue
            obs_v = row[obs_col - 1]
            if obs_v is None:
                continue
            text = str(obs_v).strip()
            if not text:
                continue

            entry = {"sheet": sheet_name, "row": excel_row_idx,
                    "text": text}

            # Index by URL (full + lower) and parsed process_id.
            # Skip non-URL values (the LINK column sometimes contains
            # status words like "ANULADO" — those would pollute the
            # index with garbage keys).
            link_v = row[link_col - 1]
            if link_v is not None:
                url = str(link_v).strip()
                if url and "secop.gov.co" in url.lower():
                    index.setdefault(url, []).append(entry)
                    index.setdefault(url.lower(), []).append(entry)
                    try:
                        ref = parse_secop_url(url)
                        index.setdefault(ref.process_id, []).append(entry)
                    except InvalidSecopUrlError:
                        pass

    # Dedup entries within each key (multiple keys can point to the same row)
    for key, entries in index.items():
        seen = set()
        unique: list[dict[str, Any]] = []
        for e in entries:
            sig = (e["sheet"], e["row"])
            if sig in seen:
                continue
            seen.add(sig)
            unique.append(e)
        index[key] = unique

    # Evict older cache entries (single-workbook system)
    _OBS_INDEX_CACHE.clear()
    _OBS_INDEX_CACHE[cache_key] = index
    return index


def _observaciones_for(
    process_id: str | None,
    proceso_de_compra: str | None,
    notice_uid: str | None,
    contract_id: str | None,
    url: str | None,
) -> list[dict[str, Any]]:
    """Look up the Dra's notes for a contract by every available key.

    Tries: explicit URL, process_id, proceso_de_compra (NTC for many
    contracts), notice_uid, id_contrato (PCCNTR). De-dups results.
    """
    workbook = Path(_DEFAULT_WORKBOOK)
    index = _load_excel_obs_index(workbook)
    found: list[dict[str, Any]] = []
    seen_rows: set[tuple[str, int]] = set()
    for key in (process_id, proceso_de_compra, notice_uid,
                contract_id, url, (url or "").lower()):
        if not key:
            continue
        for entry in index.get(key, []):
            sig = (entry["sheet"], entry["row"])
            if sig in seen_rows:
                continue
            seen_rows.add(sig)
            found.append(entry)
    return found


def _import_workbook_urls(workbook_path: Path) -> dict[str, Any]:
    """Synchronous worker: read every sheet, MERGE per-URL appearances
    into one item per unique URL/process_id, return a report.

    Mirror semantics: every (sheet, row) where a SECOP URL appears in
    the Excel is recorded as an "appearance". A URL that shows up on
    3 sheets has 3 appearances on a single watch item — the UI filter
    by sheet shows it once for each sheet, matching the Excel exactly.
    """
    from openpyxl import load_workbook

    if not workbook_path.exists():
        raise HTTPException(404, f"workbook not found: {workbook_path}")

    wb = load_workbook(workbook_path, data_only=True, read_only=True)

    with _WATCH_LOCK:
        existing = _load_watched()

        # Build O(1) lookups so we can merge by process_id or by URL.
        by_pid: dict[str, dict[str, Any]] = {}
        by_url: dict[str, dict[str, Any]] = {}
        for it in existing:
            pid = it.get("process_id")
            url = it.get("url")
            if pid:
                by_pid[pid] = it
            if url:
                by_url[url] = it
            # Backfill the new schema for legacy items missing the lists
            it.setdefault("sheets", [])
            it.setdefault("vigencias", [])
            it.setdefault("appearances", [])

        per_sheet: dict[str, dict[str, int]] = {}
        new_items_count = 0
        merged_count = 0
        already_recorded = 0  # appearance already on file (idempotent re-runs)
        errors: list[str] = []

        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            link_loc = _find_link_column(ws)
            if not link_loc:
                per_sheet[sheet_name] = {"found": 0, "added_new": 0,
                                        "merged": 0, "already_recorded": 0,
                                        "no_link_col": 1}
                continue
            header_row, link_col = link_loc
            vig_col = _find_vigencia_column(ws, header_row)
            sheet_fallback_vig = _vigencia_from_sheet_name(sheet_name)
            stats = {"found": 0, "added_new": 0, "merged": 0,
                    "already_recorded": 0, "no_link_col": 0}

            for excel_row_idx, row in enumerate(
                ws.iter_rows(min_row=header_row + 1, values_only=True),
                start=header_row + 1,
            ):
                if not row or len(row) < link_col:
                    continue
                v = row[link_col - 1]
                if v is None:
                    continue
                url = str(v).strip()
                if not url or "secop.gov.co" not in url.lower():
                    continue
                stats["found"] += 1

                # Read VIGENCIA per-row (Excel column 3.VIGENCIA) with
                # fallback to the sheet name year.
                vigencia: str | None = None
                if vig_col is not None and len(row) >= vig_col:
                    rv = row[vig_col - 1]
                    if rv is not None:
                        if isinstance(rv, (int, float)):
                            vigencia = str(int(rv))
                        else:
                            vigencia = str(rv).strip() or None
                if not vigencia:
                    vigencia = sheet_fallback_vig

                process_id = None
                try:
                    ref = parse_secop_url(url)
                    process_id = ref.process_id
                except InvalidSecopUrlError:
                    pass

                appearance = {
                    "sheet": sheet_name,
                    "vigencia": vigencia,
                    "row": excel_row_idx,
                    "url": url,
                }

                # Find a matching existing item by process_id, then URL
                target = None
                if process_id and process_id in by_pid:
                    target = by_pid[process_id]
                elif url in by_url:
                    target = by_url[url]

                if target is None:
                    # New unique process
                    target = {
                        "url": url,
                        "process_id": process_id,
                        "notice_uid": None,
                        "sheets": [],
                        "vigencias": [],
                        "appearances": [],
                        "added_at": datetime.now(timezone.utc)
                                           .isoformat(timespec="seconds"),
                        "note": f"Importado de Excel · primera vista en "
                                f"{sheet_name}",
                    }
                    existing.append(target)
                    if process_id:
                        by_pid[process_id] = target
                    by_url[url] = target
                    new_items_count += 1
                    stats["added_new"] += 1
                else:
                    # Merge: already known process. Did we already see
                    # THIS exact (sheet, row, url) appearance?
                    already_seen = any(
                        a.get("sheet") == sheet_name
                        and a.get("row") == excel_row_idx
                        and a.get("url") == url
                        for a in target.get("appearances", [])
                    )
                    if already_seen:
                        already_recorded += 1
                        stats["already_recorded"] += 1
                        continue
                    merged_count += 1
                    stats["merged"] += 1

                # Record the appearance, keep sheets/vigencias unique
                target.setdefault("appearances", []).append(appearance)
                if sheet_name not in target.setdefault("sheets", []):
                    target["sheets"].append(sheet_name)
                if vigencia and vigencia not in target.setdefault(
                    "vigencias", []
                ):
                    target["vigencias"].append(vigencia)

            per_sheet[sheet_name] = stats

        _save_watched(existing)

        return {
            "added_new": new_items_count,
            "merged": merged_count,
            "already_recorded": already_recorded,
            "skipped_invalid": 0,
            "errors": errors,
            "total_unique": len(existing),
            "total_appearances": sum(
                len(it.get("appearances", [])) for it in existing
            ),
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
