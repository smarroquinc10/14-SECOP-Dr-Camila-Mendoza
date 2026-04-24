"""Command-line entry point for the Secop-II tool.

This CLI is used mostly for debugging and to let power users run the
tool without the Streamlit UI. The end-user deliverable is the Streamlit
``.exe`` that calls into the same building blocks.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from secop_ii.config import (
    DATASET_ADICIONES,
    DATASET_CONTRATOS,
    DATASET_PROCESOS,
    FIELD_ADICION_CONTRATO,
    FIELD_CONTRATO_PROCESO,
    FIELD_PROCESO_ID,
)
from secop_ii.extractors import REGISTRY, get_extractor
from secop_ii.extractors.base import ProcessContext
from secop_ii.orchestrator import process_workbook
from secop_ii.secop_client import SecopClient
from secop_ii.url_parser import InvalidSecopUrlError, parse_secop_url


def _run_all_extractors(ctx: ProcessContext) -> dict:
    """Execute every registered extractor and merge their outputs."""
    combined: dict = {}
    errors: list[str] = []
    all_ok = True
    for name in REGISTRY:
        try:
            result = get_extractor(name).extract(ctx)
        except Exception as exc:  # pragma: no cover
            errors.append(f"{name}: {exc}")
            all_ok = False
            continue
        combined.update(result.values)
        if not result.ok:
            all_ok = False
            if result.error:
                errors.append(f"{name}: {result.error}")
    return {"ok": all_ok, "error": "; ".join(errors) or None, "values": combined}

app = typer.Typer(
    help="Herramientas CLI para consultar procesos del SECOP II.",
    no_args_is_help=True,
)
console = Console()


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


@app.command("parse-url")
def parse_url_cmd(
    url: Annotated[str, typer.Argument(help="URL pública del SECOP II.")],
) -> None:
    """Parse a SECOP II URL and print the identifier it encodes."""
    try:
        ref = parse_secop_url(url)
    except InvalidSecopUrlError as exc:
        console.print(f"[red]ERROR:[/] {exc}")
        raise typer.Exit(code=2)

    console.print(f"[green]ID:[/]         {ref.process_id}")
    console.print(f"[green]Tipo:[/]       {ref.kind}")
    console.print(f"[green]Normalizada:[/] {ref.normalized_url}")


@app.command("show-queries")
def show_queries_cmd(
    url: Annotated[str, typer.Argument(help="URL pública del SECOP II.")],
) -> None:
    """Print the Socrata query URLs that would be used for this process.

    Useful when the machine running the CLI cannot reach datos.gov.co:
    copy any of the printed URLs into a browser that can, inspect the
    JSON, and share it back.
    """
    try:
        ref = parse_secop_url(url)
    except InvalidSecopUrlError as exc:
        console.print(f"[red]ERROR:[/] {exc}")
        raise typer.Exit(code=2)

    client = SecopClient()
    pid = ref.process_id

    console.print(f"[bold]Identificador:[/] {pid} ({ref.kind})\n")
    table = Table(title="Consultas Socrata que haría el programa")
    table.add_column("Dataset", style="cyan")
    table.add_column("URL", style="white", overflow="fold")
    table.add_row(
        f"Procesos ({DATASET_PROCESOS})",
        client.build_query_url(
            DATASET_PROCESOS, where=f"{FIELD_PROCESO_ID}='{pid}'", limit=1
        ),
    )
    table.add_row(
        f"Contratos ({DATASET_CONTRATOS})",
        client.build_query_url(
            DATASET_CONTRATOS,
            where=f"{FIELD_CONTRATO_PROCESO}='{pid}'",
            limit=50,
        ),
    )
    table.add_row(
        f"Adiciones ({DATASET_ADICIONES})",
        client.build_query_url(
            DATASET_ADICIONES,
            where=f"{FIELD_ADICION_CONTRATO}='<id_contrato de la consulta anterior>'",
            limit=50,
        ),
    )
    console.print(table)


@app.command("check-url")
def check_url_cmd(
    url: Annotated[str, typer.Argument(help="URL pública del SECOP II.")],
    app_token: Annotated[
        str | None,
        typer.Option(
            "--app-token",
            envvar="SOCRATA_APP_TOKEN",
            help="Token opcional de datos.gov.co (más cuota y menos 429).",
        ),
    ] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Salida JSON.")] = False,
    verbose: Annotated[bool, typer.Option("-v", "--verbose")] = False,
) -> None:
    """Query SECOP II live and report whether the process has modificatorios."""
    _configure_logging(verbose)
    try:
        ref = parse_secop_url(url)
    except InvalidSecopUrlError as exc:
        console.print(f"[red]ERROR:[/] {exc}")
        raise typer.Exit(code=2)

    client = SecopClient(app_token=app_token)
    ctx = ProcessContext(ref=ref, client=client)
    outcome = _run_all_extractors(ctx)

    payload = {
        "id": ref.process_id,
        "kind": ref.kind,
        "ok": outcome["ok"],
        "error": outcome["error"],
        "values": outcome["values"],
    }

    if as_json:
        console.print_json(data=payload)
        return

    console.print(f"\n[bold]Proceso:[/] {ref.process_id}  ({ref.kind})")
    if not outcome["ok"] and outcome["error"]:
        console.print(f"[yellow]{outcome['error']}[/]")
    for col, val in outcome["values"].items():
        console.print(f"  [cyan]{col}:[/] {val}")


@app.command("check-json")
def check_json_cmd(
    url: Annotated[str, typer.Argument(help="URL original del SECOP II.")],
    proceso_file: Annotated[
        str | None,
        typer.Option(
            "--proceso",
            help="Ruta a JSON con la respuesta de datos.gov.co para el proceso.",
        ),
    ] = None,
    contratos_file: Annotated[
        str | None,
        typer.Option("--contratos", help="Ruta a JSON con los contratos."),
    ] = None,
    adiciones_file: Annotated[
        str | None,
        typer.Option("--adiciones", help="Ruta a JSON con las adiciones."),
    ] = None,
) -> None:
    """Run the modificatorios extractor using canned JSON fixtures.

    Intended for demos/tests when the machine running the CLI cannot
    reach datos.gov.co. Pass the JSON responses you downloaded manually
    from the browser and this command produces the same output that
    ``check-url`` would have produced against the live API.
    """
    ref = parse_secop_url(url)

    proceso = _load_json(proceso_file)
    if isinstance(proceso, list):
        proceso = proceso[0] if proceso else None
    contratos = _load_json(contratos_file) or []
    adiciones_all = _load_json(adiciones_file) or []

    class _OfflineContext(ProcessContext):
        def proceso(self_inner):  # type: ignore[override]
            return proceso

        def contratos(self_inner):  # type: ignore[override]
            return contratos

        def adiciones_de(self_inner, id_contrato):  # type: ignore[override]
            return [
                a
                for a in adiciones_all
                if str(a.get(FIELD_ADICION_CONTRATO)) == str(id_contrato)
            ]

    ctx = _OfflineContext(ref=ref, client=SecopClient())
    outcome = _run_all_extractors(ctx)

    console.print(f"\n[bold]Proceso:[/] {ref.process_id} ({ref.kind})  [offline demo]")
    if not outcome["ok"] and outcome["error"]:
        console.print(f"[yellow]{outcome['error']}[/]")
    for col, val in outcome["values"].items():
        console.print(f"  [cyan]{col}:[/] {val}")


def _load_json(path: str | None):
    if not path:
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


@app.command("update-excel")
def update_excel_cmd(
    input_file: Annotated[str, typer.Argument(help="Ruta al archivo .xlsx a actualizar.")],
    url_column: Annotated[
        str | None,
        typer.Option(
            "--url-column",
            help="Encabezado exacto de la columna con las URLs (autodetecta si no se pasa).",
        ),
    ] = None,
    sheet: Annotated[
        str | None,
        typer.Option("--sheet", help="Nombre de la hoja (por defecto la activa)."),
    ] = None,
    header_row: Annotated[
        int, typer.Option("--header-row", help="Fila del encabezado (1-based).")
    ] = 1,
    app_token: Annotated[
        str | None,
        typer.Option(
            "--app-token",
            envvar="SOCRATA_APP_TOKEN",
            help="Token opcional de datos.gov.co.",
        ),
    ] = None,
    no_backup: Annotated[
        bool, typer.Option("--no-backup", help="Saltar la creación del backup.")
    ] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="No escribe cambios al archivo."),
    ] = False,
    verbose: Annotated[bool, typer.Option("-v", "--verbose")] = False,
) -> None:
    """Actualiza un Excel con datos del SECOP II."""
    _configure_logging(verbose)

    def _progress(done: int, total: int, row) -> None:
        mark = "[OK]" if row.ok else "[X] "
        console.print(
            f"[dim]{done:>3}/{total}[/] {mark} fila {row.row}: "
            f"{row.process_id or row.url[:60]} -> {row.status}"
        )

    report = process_workbook(
        input_file,
        url_column=url_column,
        sheet_name=sheet,
        header_row=header_row,
        app_token=app_token,
        do_backup=not no_backup,
        progress=_progress,
        dry_run=dry_run,
    )

    console.print("\n[bold]Resumen:[/]")
    summary = report.as_dict()
    for key, value in summary.items():
        console.print(f"  [cyan]{key}:[/] {value}")
    if report.errors:
        raise typer.Exit(code=1)


if __name__ == "__main__":  # pragma: no cover
    app()
