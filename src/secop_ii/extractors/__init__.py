"""Field extractors — one module per column group in the output Excel."""

from __future__ import annotations

from secop_ii.extractors.auditoria import AuditoriaExtractor
from secop_ii.extractors.base import ExtractionResult, FieldExtractor, ProcessContext
from secop_ii.extractors.modificatorios import ModificatoriosExtractor

# Order matters: the registry order determines the order in which columns
# are appended to the Excel. Auditoría goes first so the user sees "what
# SECOP says this process is" before "whether it had modificatorios".
REGISTRY: dict[str, type[FieldExtractor]] = {
    AuditoriaExtractor.name: AuditoriaExtractor,
    ModificatoriosExtractor.name: ModificatoriosExtractor,
}


def get_extractor(name: str) -> FieldExtractor:
    cls = REGISTRY[name]
    return cls()


__all__ = [
    "AuditoriaExtractor",
    "ExtractionResult",
    "FieldExtractor",
    "ProcessContext",
    "ModificatoriosExtractor",
    "REGISTRY",
    "get_extractor",
]
