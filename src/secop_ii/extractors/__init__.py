"""Field extractors — one module per column group in the output Excel."""

from __future__ import annotations

from secop_ii.extractors.base import ExtractionResult, FieldExtractor, ProcessContext
from secop_ii.extractors.modificatorios import ModificatoriosExtractor

REGISTRY: dict[str, type[FieldExtractor]] = {
    ModificatoriosExtractor.name: ModificatoriosExtractor,
}


def get_extractor(name: str) -> FieldExtractor:
    cls = REGISTRY[name]
    return cls()


__all__ = [
    "ExtractionResult",
    "FieldExtractor",
    "ProcessContext",
    "ModificatoriosExtractor",
    "REGISTRY",
    "get_extractor",
]
