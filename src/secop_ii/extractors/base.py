"""Base protocol + shared context for field extractors.

Each extractor contributes one or more output columns to the Excel. The
orchestrator builds a :class:`ProcessContext` per row and calls every
registered extractor; extractors read from the context's lazy accessors so
each dataset is fetched at most once per row (memoized in the
:class:`SecopClient` cache too, so shared processes across rows reuse
network work).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from secop_ii.secop_client import SecopClient
from secop_ii.url_parser import ProcessRef


_PROCESO_UNFETCHED = object()


@dataclass
class ProcessContext:
    """Lazy, memoized view of a process for extractors to consume.

    ``existing_row`` carries the row's current cell values keyed by
    header name. The :class:`FeabFillExtractor` uses it to enforce the
    no-overwrite rule: a cell with manual data is never replaced —
    discrepancies vs SECOP are logged but the user's value stays.
    """

    ref: ProcessRef
    client: SecopClient
    existing_row: dict[str, Any] = field(default_factory=dict)
    row_idx: int | None = None
    _proceso: Any = field(default=_PROCESO_UNFETCHED, init=False, repr=False)
    _contratos: list[dict] | None = field(default=None, init=False, repr=False)
    _adiciones_by_contrato: dict[str, list[dict]] = field(
        default_factory=dict, init=False, repr=False
    )

    def proceso(self) -> dict | None:
        if self._proceso is _PROCESO_UNFETCHED:
            self._proceso = self.client.get_proceso(
                self.ref.process_id, url=self.ref.source_url
            )
        return self._proceso

    def notice_uid(self) -> str | None:
        """Resolved ``CO1.NTC.*`` for this process (when the URL is a PPI pivot)."""
        return self.client.resolve_notice_uid(
            self.ref.process_id, self.ref.source_url
        )

    def contratos(self) -> list[dict]:
        if self._contratos is None:
            proceso = self.proceso()
            portfolio_id = (
                str(proceso.get("id_del_portafolio")) if proceso else None
            ) or None
            self._contratos = self.client.get_contratos(
                portfolio_id=portfolio_id,
                notice_uid=self.notice_uid(),
            )
        return self._contratos

    def adiciones_de(self, id_contrato: str) -> list[dict]:
        if id_contrato not in self._adiciones_by_contrato:
            self._adiciones_by_contrato[id_contrato] = self.client.get_adiciones(
                id_contrato
            )
        return self._adiciones_by_contrato[id_contrato]

    def modificaciones_ricas_de(self, id_contrato: str) -> list[dict]:
        """Rows from u8cx-r425 (valor, días, fecha aprobación). Memoized per contrato."""
        cache = getattr(self, "_mod_ricas_by_contrato", None)
        if cache is None:
            cache = {}
            object.__setattr__(self, "_mod_ricas_by_contrato", cache)
        if id_contrato not in cache:
            cache[id_contrato] = self.client.get_modificaciones_ricas(id_contrato)
        return cache[id_contrato]

    def ubicaciones_de(self, id_contrato: str) -> list[dict]:
        """Direcciones de ejecución para ``id_contrato``. Memoized."""
        cache = getattr(self, "_ubic_by_contrato", None)
        if cache is None:
            cache = {}
            object.__setattr__(self, "_ubic_by_contrato", cache)
        if id_contrato not in cache:
            cache[id_contrato] = self.client.get_ubicaciones(id_contrato)
        return cache[id_contrato]

    def garantias_de(self, id_contrato: str) -> list[dict]:
        """Pólizas (gjp9-cutm) para ``id_contrato``. Memoized."""
        cache = getattr(self, "_gar_by_contrato", None)
        if cache is None:
            cache = {}
            object.__setattr__(self, "_gar_by_contrato", cache)
        if id_contrato not in cache:
            cache[id_contrato] = self.client.get_garantias(id_contrato)
        return cache[id_contrato]

    def facturas_de(self, id_contrato: str) -> list[dict]:
        """Facturas (ibyt-yi2f) para ``id_contrato``. Memoized."""
        cache = getattr(self, "_fact_by_contrato", None)
        if cache is None:
            cache = {}
            object.__setattr__(self, "_fact_by_contrato", cache)
        if id_contrato not in cache:
            cache[id_contrato] = self.client.get_facturas(id_contrato)
        return cache[id_contrato]

    def ejecucion_de(self, id_contrato: str) -> list[dict]:
        """Avance de ejecución (mfmm-jqmq) para ``id_contrato``. Memoized."""
        cache = getattr(self, "_ejec_by_contrato", None)
        if cache is None:
            cache = {}
            object.__setattr__(self, "_ejec_by_contrato", cache)
        if id_contrato not in cache:
            cache[id_contrato] = self.client.get_ejecucion(id_contrato)
        return cache[id_contrato]

    def suspensiones_de(self, id_contrato: str) -> list[dict]:
        """Suspensiones (u99c-7mfm) para ``id_contrato``. Memoized."""
        cache = getattr(self, "_susp_by_contrato", None)
        if cache is None:
            cache = {}
            object.__setattr__(self, "_susp_by_contrato", cache)
        if id_contrato not in cache:
            cache[id_contrato] = self.client.get_suspensiones(id_contrato)
        return cache[id_contrato]

    def mods_proceso(self) -> list[dict]:
        """Modificaciones al proceso (e2u2-swiw). Memoized."""
        cached = getattr(self, "_mods_proceso", None)
        if cached is not None:
            return cached
        proceso = self.proceso()
        portfolio_id = (
            str(proceso.get("id_del_portafolio")) if proceso else None
        ) or ""
        rows = (
            self.client.get_mod_procesos(portfolio_id) if portfolio_id else []
        )
        object.__setattr__(self, "_mods_proceso", rows)
        return rows


@dataclass
class ExtractionResult:
    """What an extractor returns for a single row."""

    values: dict[str, Any]
    ok: bool = True
    error: str | None = None


@runtime_checkable
class FieldExtractor(Protocol):
    name: str
    output_columns: list[str]

    def extract(self, ctx: ProcessContext) -> ExtractionResult: ...
