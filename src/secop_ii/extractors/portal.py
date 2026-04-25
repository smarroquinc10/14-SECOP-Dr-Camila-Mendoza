"""Mirror what each ``OpportunityDetail`` page shows on the public portal.

The ``portal`` extractor is opt-in (CLI ``--mirror-portal``). When enabled
the orchestrator opens a single :class:`PortalScraper` for the run and
passes it to this extractor. We then pull each process's
``OpportunityDetail`` page through the scraper's persistent Chrome
session and surface the visible fields as ``Portal: …`` columns.

Captcha handling: the scraper auto-clicks "No soy un robot" inside the
anchor iframe; if Google still demands a challenge the user solves it
once in the visible Chrome window — the cookie then covers all
subsequent processes for ~30 minutes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from secop_ii.extractors.base import ExtractionResult, ProcessContext
from secop_ii.portal_scraper import PortalData, PortalScraper

COL_PRECIO_EST = "Portal: Precio estimado"
COL_NUMERO = "Portal: Número del proceso"
COL_TITULO = "Portal: Título"
COL_FASE = "Portal: Fase"
COL_ESTADO = "Portal: Estado"
COL_DESCRIPCION = "Portal: Descripción"
COL_TIPO_PROCESO = "Portal: Tipo proceso"
COL_TIPO_CONTRATO = "Portal: Tipo contrato"
COL_JUSTIFICACION = "Portal: Justificación modalidad"
COL_DURACION = "Portal: Duración contrato"
COL_DIRECCION_EJEC = "Portal: Dirección ejecución"
COL_UNSPSC = "Portal: Código UNSPSC"
COL_UNSPSC_ADIC = "Portal: UNSPSC adicionales"
COL_LOTES = "Portal: Lotes"
COL_MIPYME = "Portal: Limitación MiPymes"
COL_DAR_PUBLICIDAD = "Portal: Dar publicidad al proceso"
COL_MODULO_PUB = "Portal: Módulo publicitario"
COL_FECHA_FIRMA = "Portal: Fecha firma contrato"
COL_FECHA_INICIO = "Portal: Fecha inicio ejecución"
COL_PLAZO = "Portal: Plazo ejecución contrato"
COL_FECHA_TERM = "Portal: Fecha terminación contrato"
COL_FECHA_PUB = "Portal: Fecha publicación"
COL_DESTINO_GASTO = "Portal: Destinación del gasto"
COL_VALOR_TOTAL = "Portal: Valor total"
COL_GAR_CUMPL = "Portal: Garantía cumplimiento"
COL_GAR_PCT = "Portal: % valor contrato (garantía)"
COL_GAR_DESDE = "Portal: Garantía vigencia desde"
COL_GAR_HASTA = "Portal: Garantía vigencia hasta"
COL_GAR_RESP = "Portal: Resp. civil extracontractual"
COL_GAR_SMMLV = "Portal: SMMLV resp. civil"
COL_NOTIFS = "Portal: Notificaciones (modificatorios)"
COL_NOTIFS_N = "Portal: # notificaciones"
COL_DOCUMENTOS = "Portal: Documentos adjuntos"
COL_DOCUMENTOS_N = "Portal: # documentos"
COL_FUENTE_PORTAL = "Portal: Estado scraping"
COL_CAMPOS_FALTAN = "Portal: Campos faltantes"  # critical-field audit
COL_SCRAPED_AT = "Portal: Última verificación"

# Maps `PortalData.fields` keys -> Excel column names. Order = column order
# in the Excel (left to right after the API columns).
_FIELD_TO_COLUMN = {
    "precio_estimado": COL_PRECIO_EST,
    "numero_proceso": COL_NUMERO,
    "titulo": COL_TITULO,
    "fase": COL_FASE,
    "estado": COL_ESTADO,
    "descripcion": COL_DESCRIPCION,
    "tipo_proceso": COL_TIPO_PROCESO,
    "tipo_contrato": COL_TIPO_CONTRATO,
    "justificacion_modalidad": COL_JUSTIFICACION,
    "duracion_contrato": COL_DURACION,
    "direccion_ejecucion": COL_DIRECCION_EJEC,
    "unspsc_principal": COL_UNSPSC,
    "unspsc_adicional": COL_UNSPSC_ADIC,
    "lotes": COL_LOTES,
    "mipyme_limitacion": COL_MIPYME,
    "dar_publicidad": COL_DAR_PUBLICIDAD,
    "modulo_publicitario": COL_MODULO_PUB,
    "fecha_firma_contrato": COL_FECHA_FIRMA,
    "fecha_inicio_ejecucion": COL_FECHA_INICIO,
    "plazo_ejecucion": COL_PLAZO,
    "fecha_terminacion": COL_FECHA_TERM,
    "fecha_publicacion": COL_FECHA_PUB,
    "destinacion_gasto": COL_DESTINO_GASTO,
    "valor_total": COL_VALOR_TOTAL,
    "garantia_cumplimiento": COL_GAR_CUMPL,
    "garantia_pct_valor": COL_GAR_PCT,
    "garantia_vigencia_desde": COL_GAR_DESDE,
    "garantia_vigencia_hasta": COL_GAR_HASTA,
    "garantia_resp_civil": COL_GAR_RESP,
    "garantia_smmlv": COL_GAR_SMMLV,
}


@dataclass
class PortalExtractor:
    """Extractor that mirrors the OpportunityDetail HTML."""

    name: str = "portal"
    scraper: PortalScraper | None = field(default=None)
    output_columns: tuple[str, ...] = tuple(_FIELD_TO_COLUMN.values()) + (
        COL_NOTIFS,
        COL_NOTIFS_N,
        COL_DOCUMENTOS,
        COL_DOCUMENTOS_N,
        COL_FUENTE_PORTAL,
        COL_CAMPOS_FALTAN,
        COL_SCRAPED_AT,
    )

    def extract(self, ctx: ProcessContext) -> ExtractionResult:
        if self.scraper is None:
            return ExtractionResult(
                values=_empty(estado="scraper no configurado"),
                ok=False,
                error="PortalExtractor sin scraper; usar --mirror-portal",
            )

        notice_uid = ctx.notice_uid()
        if not notice_uid:
            # Resolve via proceso row's URL field if available
            proceso = None
            try:
                proceso = ctx.proceso()
            except Exception:  # pragma: no cover
                pass
            if proceso:
                url_field = proceso.get("urlproceso")
                if isinstance(url_field, dict):
                    raw_url = url_field.get("url", "")
                    import re
                    m = re.search(r"CO1\.NTC\.\d+", raw_url)
                    if m:
                        notice_uid = m.group(0)
        if not notice_uid:
            return ExtractionResult(
                values=_empty(estado="sin_notice_uid"),
                ok=False,
                error="No se pudo determinar el CO1.NTC.* del proceso",
            )

        try:
            data = self.scraper.fetch(notice_uid)
        except Exception as exc:  # pragma: no cover
            return ExtractionResult(
                values=_empty(estado=f"error: {str(exc)[:80]}"),
                ok=False,
                error=str(exc),
            )

        if data is None:
            return ExtractionResult(
                values=_empty(estado="portal_no_disponible"),
                ok=False,
                error="No se pudo abrir/scrapear OpportunityDetail",
            )
        return ExtractionResult(values=_to_columns(data), ok=True)


def _empty(estado: str) -> dict[str, Any]:
    base = {col: "" for col in _FIELD_TO_COLUMN.values()}
    base[COL_NOTIFS] = ""
    base[COL_NOTIFS_N] = ""
    base[COL_DOCUMENTOS] = ""
    base[COL_DOCUMENTOS_N] = ""
    base[COL_FUENTE_PORTAL] = estado
    base[COL_CAMPOS_FALTAN] = ""
    base[COL_SCRAPED_AT] = ""
    return base


def _to_columns(data: PortalData) -> dict[str, Any]:
    """Strict mapping: write every value we have, leave the rest empty.

    Never invent or extrapolate. If the portal didn't render a label, the
    cell stays empty (not "No data" or "0"). False positives/negatives are
    avoided by relying on the curated `_FIELD_TO_COLUMN` mapping only.
    """
    out: dict[str, Any] = {col: "" for col in _FIELD_TO_COLUMN.values()}
    for src_key, dst_col in _FIELD_TO_COLUMN.items():
        value = data.fields.get(src_key)
        if value:
            out[dst_col] = value
    # Notificaciones: each row in PortalData.notificaciones is one published
    # event (e.g. "Publicación modificación 16/04/2026"). Concatenate all so
    # the user sees them at a glance, and report the count separately.
    if data.notificaciones:
        formatted = []
        for n in data.notificaciones[:10]:
            evento = (n.get("evento") or "").strip()
            fecha = (n.get("fecha") or "").strip()
            piece = f"{evento} {fecha}".strip()
            if piece:
                formatted.append(piece)
        out[COL_NOTIFS] = " | ".join(formatted)[:500]
        out[COL_NOTIFS_N] = len(data.notificaciones)
    else:
        out[COL_NOTIFS] = ""
        out[COL_NOTIFS_N] = 0
    out[COL_DOCUMENTOS] = " | ".join(
        d.get("name", "") for d in data.documents[:10]
    )[:500]
    out[COL_DOCUMENTOS_N] = len(data.documents)
    out[COL_FUENTE_PORTAL] = data.status
    out[COL_CAMPOS_FALTAN] = ", ".join(data.missing_fields) if data.missing_fields else ""
    out[COL_SCRAPED_AT] = data.scraped_at
    return out


__all__ = [
    "PortalExtractor",
    "COL_DIRECCION_EJEC",
    "COL_DOCUMENTOS",
    "COL_DOCUMENTOS_N",
    "COL_FUENTE_PORTAL",
]
