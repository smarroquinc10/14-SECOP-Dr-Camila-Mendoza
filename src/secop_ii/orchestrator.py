"""Row-by-row pipeline: reads URLs from an Excel, calls extractors, writes back.

Used by both the CLI (``update-excel``) and the Streamlit UI. Exposes a
progress callback so the UI can render a progress bar and live log.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from secop_ii.excel_io import (
    ExcelStructureError,
    backup_workbook,
    detect_url_column,
    ensure_columns,
    iter_rows,
    load_workbook,
    save_workbook,
    write_row,
)
from secop_ii.extractors import FieldExtractor, REGISTRY, get_extractor
from secop_ii.extractors.base import ExtractionResult, ProcessContext
from secop_ii.extractors.modificatorios import COL_DETALLE
from secop_ii.observaciones import (
    OUTPUT_COLUMNS as OBS_OUTPUT_COLUMNS,
    detect_observaciones_column,
    parse_observaciones,
)
from secop_ii.secop_client import SecopClient
from secop_ii.url_parser import InvalidSecopUrlError, parse_secop_url

log = logging.getLogger(__name__)

STATUS_COLUMN = "Estado actualización"
LAST_UPDATE_COLUMN = "Última actualización"


@dataclass
class RowReport:
    row: int
    url: str
    process_id: str | None
    ok: bool
    status: str  # "ok", "no_encontrado", "error", "url_invalida"
    error: str | None = None
    values: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunReport:
    input_path: Path
    backup_path: Path | None
    rows: list[RowReport] = field(default_factory=list)
    total: int = 0
    ok: int = 0
    with_modificatorio: int = 0
    without_modificatorio: int = 0
    errors: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "input": str(self.input_path),
            "backup": str(self.backup_path) if self.backup_path else None,
            "total": self.total,
            "ok": self.ok,
            "con_modificatorio": self.with_modificatorio,
            "sin_modificatorio": self.without_modificatorio,
            "errores": self.errors,
        }


ProgressCallback = Callable[[int, int, RowReport], None]


def process_workbook(
    path: Path | str,
    *,
    url_column: str | None = None,
    sheet_name: str | None = None,
    header_row: int = 1,
    fields: list[str] | None = None,
    app_token: str | None = None,
    rate_per_second: float | None = None,
    do_backup: bool = True,
    progress: ProgressCallback | None = None,
    dry_run: bool = False,
    mirror_portal: bool = False,
) -> RunReport:
    """Update ``path`` in place with SECOP II data.

    Args:
        path: Excel file to update.
        url_column: Optional exact header name of the URL column. If
            ``None`` it is auto-detected.
        sheet_name: Sheet to process (defaults to the active one).
        header_row: 1-based index of the header row (default 1).
        fields: Names of extractors to run. ``None`` runs every registered
            extractor. Currently supported: ``"modificatorios"``.
        app_token: Socrata app token (recommended to avoid 429).
        rate_per_second: Override the default request rate.
        do_backup: Create a timestamped copy before writing.
        progress: Called after each row with ``(done, total, row_report)``.
        dry_run: If ``True``, nothing is written to disk.

    Returns:
        :class:`RunReport` with per-row details and summary counts.
    """
    path = Path(path)
    backup_path = backup_workbook(path) if (do_backup and not dry_run) else None

    wb, ws = load_workbook(path, sheet_name=sheet_name)

    url_col = detect_url_column(ws, header_row=header_row, preferred=url_column)
    # OBSERVACIONES is read-only — we never write to it, just mirror its
    # signals ("NO LEG", modificatorio mentions) into separate columns.
    obs_col = detect_observaciones_column(ws, header_row=header_row)

    extractors = _resolve_extractors(fields)

    # ``--mirror-portal`` opens visible Chrome and scrapes each
    # OpportunityDetail directly. The PortalScraper has its own session
    # lifetime so we manage it as a context manager around the row loop.
    portal_scraper_cm = None
    if mirror_portal:
        from secop_ii.extractors.portal import PortalExtractor
        from secop_ii.portal_scraper import PortalScraper
        portal_scraper_cm = PortalScraper()
        portal_scraper_cm.__enter__()
        portal_ext = PortalExtractor(scraper=portal_scraper_cm)
        extractors.append(portal_ext)

    output_columns: list[str] = [STATUS_COLUMN, LAST_UPDATE_COLUMN]
    for ext in extractors:
        output_columns.extend(ext.output_columns)
    # Only add the OBS columns if we actually found the source column.
    if obs_col is not None:
        output_columns.extend(OBS_OUTPUT_COLUMNS)
    column_map = ensure_columns(ws, output_columns, header_row=header_row)

    client = SecopClient(app_token=app_token, rate_per_second=rate_per_second)
    report = RunReport(input_path=path, backup_path=backup_path)

    rows = list(iter_rows(ws, url_col, header_row=header_row))
    report.total = len(rows)

    from datetime import datetime

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    for idx, (row_idx, url) in enumerate(rows, start=1):
        obs_text = ws.cell(row=row_idx, column=obs_col).value if obs_col else None
        row_report = _process_one_row(
            row_idx=row_idx,
            url=url,
            client=client,
            extractors=extractors,
            ws=ws,
            column_map=column_map,
            now=now,
            obs_text=obs_text,
        )
        report.rows.append(row_report)
        if row_report.ok:
            report.ok += 1
            mod_value = row_report.values.get("¿Hubo modificatorio?", "")
            if mod_value == "Sí":
                report.with_modificatorio += 1
            elif mod_value == "No":
                report.without_modificatorio += 1
        else:
            report.errors += 1
        if progress:
            progress(idx, report.total, row_report)

    if not dry_run:
        save_workbook(wb, path)

    if portal_scraper_cm is not None:
        try:
            portal_scraper_cm.__exit__(None, None, None)
        except Exception:  # pragma: no cover - cleanup is best-effort
            pass

    return report


def _resolve_extractors(fields: list[str] | None) -> list[FieldExtractor]:
    names = fields if fields else list(REGISTRY)
    unknown = [n for n in names if n not in REGISTRY]
    if unknown:
        raise ValueError(
            f"Extractores desconocidos: {unknown}. Disponibles: {list(REGISTRY)}"
        )
    return [get_extractor(n) for n in names]


def _process_one_row(
    *,
    row_idx: int,
    url: str,
    client: SecopClient,
    extractors: list[FieldExtractor],
    ws,
    column_map: dict[str, int],
    now: str,
    obs_text: str | None = None,
) -> RowReport:
    obs_values = parse_observaciones(obs_text) if obs_text else {}
    try:
        ref = parse_secop_url(url)
    except InvalidSecopUrlError as exc:
        write_row(
            ws,
            row_idx,
            {
                STATUS_COLUMN: "url_invalida",
                LAST_UPDATE_COLUMN: now,
                COL_DETALLE: str(exc),
                **obs_values,
            },
            column_map,
        )
        return RowReport(
            row=row_idx,
            url=url,
            process_id=None,
            ok=False,
            status="url_invalida",
            error=str(exc),
        )

    ctx = ProcessContext(ref=ref, client=client)
    combined_values: dict[str, Any] = {}
    row_ok = True
    first_error: str | None = None
    row_status = "ok"

    for ext in extractors:
        try:
            result: ExtractionResult = ext.extract(ctx)
        except Exception as exc:  # pragma: no cover - safety net
            log.exception("extractor %s falló en fila %s", ext.name, row_idx)
            result = ExtractionResult(values={}, ok=False, error=str(exc))

        combined_values.update(result.values)
        if not result.ok:
            row_ok = False
            first_error = first_error or result.error
            row_status = (
                "no_encontrado"
                if result.error and "no_encontrado" in result.error
                else "error"
            )

    combined_values[STATUS_COLUMN] = row_status if row_ok else (row_status or "error")
    combined_values[LAST_UPDATE_COLUMN] = now
    # OBSERVACIONES-derived columns are appended last so they read as
    # extra context next to the SECOP API data (API is authoritative;
    # these are the Dra.'s hand-noted FEAB admin markers).
    combined_values.update(obs_values)
    write_row(ws, row_idx, combined_values, column_map)

    return RowReport(
        row=row_idx,
        url=url,
        process_id=ref.process_id,
        ok=row_ok,
        status=combined_values[STATUS_COLUMN],
        error=first_error,
        values=combined_values,
    )


__all__ = ["RunReport", "RowReport", "process_workbook"]
