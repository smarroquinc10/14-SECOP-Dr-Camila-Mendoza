"""Field extractors — one module per column group in the output Excel."""

from __future__ import annotations

from secop_ii.extractors.auditoria import AuditoriaExtractor
from secop_ii.extractors.base import ExtractionResult, FieldExtractor, ProcessContext
from secop_ii.extractors.contrato_full import ContratoFullExtractor
from secop_ii.extractors.documentos import DocumentosExtractor
from secop_ii.extractors.feab_fill import FeabFillExtractor
from secop_ii.extractors.garantias import GarantiasExtractor
from secop_ii.extractors.modificatorios import ModificatoriosExtractor
from secop_ii.extractors.mods_proceso import ModsProcesoExtractor
from secop_ii.extractors.pagos import PagosExtractor
from secop_ii.extractors.proceso_full import ProcesoFullExtractor
from secop_ii.extractors.seguimiento import SeguimientoExtractor

# Order matters: the registry order determines the order in which columns
# are appended to the Excel. We group logically:
#   1. Auditoría     — identity of the process (who/what/when/where)
#   2. ProcesoFull   — full process detail (modalidad, tipo, adjudicación, fechas)
#   3. ContratoFull  — contract identity, dates, money flow (all contracts)
#   4. Modificatorios — did this process have modificatorios? (yes/no, count)
#   5. ModsProceso   — edits to the process itself
#   6. Garantías     — pólizas per contract
#   7. Pagos         — facturas and payments per contract
#   8. Seguimiento   — ejecución + suspensiones per contract
#   9. Documentos    — URL listings of published PDFs (evidence)
REGISTRY: dict[str, type[FieldExtractor]] = {
    # FEAB filler runs FIRST so its output lands in the Dra.'s primary
    # columns. The aux extractors below add their own column blocks for
    # audit / drill-down purposes.
    FeabFillExtractor.name: FeabFillExtractor,
    AuditoriaExtractor.name: AuditoriaExtractor,
    ProcesoFullExtractor.name: ProcesoFullExtractor,
    ContratoFullExtractor.name: ContratoFullExtractor,
    ModificatoriosExtractor.name: ModificatoriosExtractor,
    ModsProcesoExtractor.name: ModsProcesoExtractor,
    GarantiasExtractor.name: GarantiasExtractor,
    PagosExtractor.name: PagosExtractor,
    SeguimientoExtractor.name: SeguimientoExtractor,
    DocumentosExtractor.name: DocumentosExtractor,
}


def get_extractor(name: str) -> FieldExtractor:
    cls = REGISTRY[name]
    return cls()


__all__ = [
    "AuditoriaExtractor",
    "ContratoFullExtractor",
    "DocumentosExtractor",
    "ExtractionResult",
    "FeabFillExtractor",
    "FieldExtractor",
    "GarantiasExtractor",
    "ModificatoriosExtractor",
    "ModsProcesoExtractor",
    "PagosExtractor",
    "ProcesoFullExtractor",
    "ProcessContext",
    "SeguimientoExtractor",
    "REGISTRY",
    "get_extractor",
]
