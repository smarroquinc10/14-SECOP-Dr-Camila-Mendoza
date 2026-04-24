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


@dataclass
class ProcessContext:
    """Lazy, memoized view of a process for extractors to consume."""

    ref: ProcessRef
    client: SecopClient
    _proceso: dict | None = field(default=None, init=False, repr=False)
    _contratos: list[dict] | None = field(default=None, init=False, repr=False)
    _adiciones_by_contrato: dict[str, list[dict]] = field(
        default_factory=dict, init=False, repr=False
    )

    def proceso(self) -> dict | None:
        if self._proceso is None:
            self._proceso = self.client.get_proceso(
                self.ref.process_id, url=self.ref.source_url
            )
        return self._proceso

    def contratos(self) -> list[dict]:
        if self._contratos is None:
            self._contratos = self.client.get_contratos(self.ref.process_id)
        return self._contratos

    def adiciones_de(self, id_contrato: str) -> list[dict]:
        if id_contrato not in self._adiciones_by_contrato:
            self._adiciones_by_contrato[id_contrato] = self.client.get_adiciones(
                id_contrato
            )
        return self._adiciones_by_contrato[id_contrato]


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
