"use client";

/**
 * DetailDialog · CARDINAL PURO post 2026-04-27
 *
 * Frase fundadora de Sergio: "una abogada no puede ver errores · no te
 * puedes comer datos · no puede haber falsos positivos y falsos negativos".
 *
 * Filosofía cardinal de este modal:
 *   - SOLO muestra lo que el scrape del link community.secop extrajo
 *   - NO hace fetches a jbjy-vk9h ni rpmr-utcd (mienten · 33 procs >50% drift)
 *   - NO calcula "alertas legales" derivadas (eran FP/FN frecuentes)
 *   - NO muestra comparaciones entre fuentes (cardinal puro = solo el link)
 *   - Si el portal no tiene datos: mensaje honesto + botón "Abrir en SECOP II"
 *   - "—" honesto en cada celda faltante
 *
 * Memoria: feedback_dashboard_es_scraper_de_links.md, project_porque_fundador.md
 */

import * as React from "react";
import useSWR from "swr";
import { ChevronRight, ExternalLink, Loader2 } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { api, type PortalSnapshot } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Props {
  contractId: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * Etiquetas humanas para los campos del portal scrape.
 * Si el campo no está acá, se muestra con su nombre crudo (snake_case → spaces).
 * Cardinal: NUNCA esconder un campo · si existe en el scrape, se muestra.
 */
const PORTAL_FIELD_LABELS: Record<string, string> = {
  numero_proceso: "Número del proceso",
  numero_contrato: "Número del contrato",
  titulo: "Título",
  descripcion: "Descripción / objeto",
  estado: "Estado del proceso (en SECOP)",
  fase: "Fase del proceso",
  tipo_proceso: "Tipo de proceso",
  tipo_contrato: "Tipo de contrato",
  modalidad: "Modalidad de contratación",
  justificacion_modalidad: "Justificación de la modalidad",
  valor_total: "Valor total",
  precio_estimado: "Precio estimado",
  proveedor: "Proveedor (cuando publicado)",
  fecha_publicacion: "Fecha de publicación del proceso",
  fecha_firma_contrato: "Fecha de firma del contrato",
  fecha_inicio_ejecucion: "Fecha de inicio de ejecución",
  fecha_terminacion: "Fecha de terminación",
  plazo_ejecucion: "Plazo de ejecución",
  duracion_contrato: "Duración del contrato",
  direccion_ejecucion: "Dirección de ejecución",
  unspsc_principal: "Código UNSPSC principal",
  unspsc_adicional: "Códigos UNSPSC adicionales",
  destinacion_gasto: "Destinación del gasto",
  garantia_cumplimiento: "Garantía de cumplimiento",
  garantia_pct_valor: "Garantía: % del valor",
  garantia_smmlv: "Garantía: SMMLV",
  garantia_resp_civil: "Garantía: responsabilidad civil",
  garantia_vigencia_desde: "Garantía: vigencia desde",
  garantia_vigencia_hasta: "Garantía: vigencia hasta",
  dar_publicidad: "Publicidad del proceso",
  lotes: "Procedimiento por lotes",
  mipyme_limitacion: "Limitación a MIPYMES",
};


/** Convierte snake_case → "Snake Case" para campos sin label explícito. */
function humanizeFieldName(s: string): string {
  return s
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}


/** Render value · si vacío, "—" honesto. */
function renderValue(v: string | null | undefined): React.ReactNode {
  if (v == null || String(v).trim() === "") {
    return <span className="text-ink-soft italic">—</span>;
  }
  return <span className="whitespace-pre-wrap">{String(v)}</span>;
}


export function DetailDialog({ contractId, open, onOpenChange }: Props) {
  // CARDINAL PURO: única fetch · SOLO portal scrape del link community.secop.
  // Si el contractId puede ser tanto process_id como notice_uid, intenta
  // ambos · el `api.contractPortal()` ya maneja el lookup por ambas keys.
  const { data: portalData, isLoading } = useSWR<PortalSnapshot | null>(
    open && contractId ? `portal:${contractId}` : null,
    () => api.contractPortal(contractId!),
    { revalidateOnFocus: false },
  );

  // CARDINAL (2026-04-28) · lookup de consecutivos FEAB del Excel.
  // SWR cachea la lista entera entre aperturas del modal · O(1) lookup
  // dentro de `useMemo`. La Dra habla por consecutivo (CONTRATO-FEAB-XXXX-AAAA),
  // no por process_id · sin esto la sección no aparece en el modal.
  const { data: watchListData } = useSWR(
    open ? "watchList:cache" : null,
    () => api.watchList(),
    { revalidateOnFocus: false },
  );
  const numerosContratos: string[] = React.useMemo(() => {
    if (!contractId || !watchListData) return [];
    const items = watchListData.items;
    // Match por process_id, notice_uid o url ending — el contractId puede
    // ser el `key` de UnifiedRow que típicamente es la URL completa.
    const item = items.find(
      (it) =>
        it.process_id === contractId ||
        it.notice_uid === contractId ||
        it.url === contractId,
    );
    return item?.numero_contrato_excel ?? [];
  }, [contractId, watchListData]);

  if (!open) return null;

  const fields = portalData?.fields ?? {};
  const documents = portalData?.documents ?? [];
  const notificaciones = portalData?.notificaciones ?? [];
  const scrapedAt = portalData?.scraped_at ?? null;
  const status = portalData?.status ?? null;

  // Detectar tipo de link para mensajes específicos cardinal-honestos
  const isContratoInterno = contractId?.startsWith("CO1.PCCNTR.") ?? false;
  const isBorrador =
    (contractId?.startsWith("CO1.REQ.") || contractId?.startsWith("CO1.BDOS.")) ??
    false;
  const hasPortalData = Object.keys(fields).length > 0;

  // Construir el link de SECOP II para abrir manualmente
  const secopUrl =
    fields.url_proceso ??
    fields.url ??
    (contractId
      ? `https://community.secop.gov.co/Public/Tendering/OpportunityDetail/Index?noticeUID=${contractId}`
      : null);

  // Título del modal · CARDINAL (2026-04-28): prioridad Excel > portal SECOP.
  // Si la Dra escribió `CONTRATO-FEAB-0001-2024` en su Excel, ese es el
  // título canónico (lo que ella usa para hablar del contrato). Caemos a
  // numero_contrato del portal solo si el Excel no lo trae.
  const modalTitle =
    numerosContratos[0] ??
    fields.numero_contrato ??
    fields.numero_proceso ??
    contractId ??
    "Detalle del contrato";

  // Subtítulo: descripción del portal (truncada)
  const subtitle = fields.titulo ?? fields.descripcion ?? "";

  // Renderizado: ordenar campos · primero los más importantes (labels conocidos),
  // después el resto alfabético (cardinal "ver todo")
  const knownFields = Object.keys(PORTAL_FIELD_LABELS).filter(
    (k) => k in fields,
  );
  const otherFields = Object.keys(fields)
    .filter((k) => !(k in PORTAL_FIELD_LABELS))
    .sort();
  const orderedFields = [...knownFields, ...otherFields];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <p className="text-[10px] uppercase tracking-wider text-ink-soft">
            Detalle del contrato
          </p>
          <DialogTitle className="serif text-2xl text-ink">
            {modalTitle}
          </DialogTitle>
          {subtitle && (
            <DialogDescription className="text-ink-soft text-sm">
              {String(subtitle).slice(0, 200)}
              {String(subtitle).length > 200 ? "…" : ""}
            </DialogDescription>
          )}
          {secopUrl && (
            <a
              href={secopUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-burgundy hover:underline text-sm w-fit mt-1"
            >
              <ExternalLink className="h-3 w-3" />
              Abrir en SECOP II
            </a>
          )}
        </DialogHeader>

        <div className="space-y-5 mt-4">
          {/* CONTRATOS FEAB ASOCIADOS · CARDINAL (2026-04-28).
              La Dra registra cada contrato firmado en su Excel con su
              consecutivo CONTRATO-FEAB-NNNN-VIGENCIA. Una URL del SECOP
              puede tener N contratos asociados (subasta con varias
              adjudicaciones · max observado: 13 contratos en una sola
              URL). Sección visible solo si hay al menos 1 consecutivo
              vinculado. Sin consecutivo → sección oculta · "—" honesto. */}
          {numerosContratos.length > 0 && (
            <section className="border border-rule rounded-md overflow-hidden">
              <div className="bg-stone-50 px-4 py-2.5 border-b border-rule">
                <h3 className="serif text-base font-semibold text-ink">
                  {numerosContratos.length === 1
                    ? "Contrato FEAB asociado"
                    : `Contratos FEAB asociados (${numerosContratos.length})`}
                </h3>
                <p className="text-xs text-ink-soft mt-0.5">
                  Consecutivos del Excel de gestión contractual
                </p>
              </div>
              <ul className="divide-y divide-rule">
                {numerosContratos.map((c) => (
                  <li
                    key={c}
                    className="px-4 py-2 text-sm font-mono text-ink"
                  >
                    {c}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {/* LOADING STATE */}
          {isLoading && (
            <div className="flex items-center gap-2 text-ink-soft py-8 justify-center">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>Cargando datos del scrape del link…</span>
            </div>
          )}

          {/* SIN DATOS DEL PORTAL · mensaje honesto cardinal por tipo */}
          {!isLoading && !hasPortalData && (
            <section className="border border-rule rounded-md p-4 bg-amber-50/40">
              {isContratoInterno && (
                <>
                  <h3 className="serif text-base font-semibold text-violet-900 mb-1">
                    Este link va al portal interno SECOP II
                  </h3>
                  <p className="text-sm text-ink leading-relaxed">
                    El link de este proceso apunta al portal interno del SECOP II
                    que requiere <strong>tu login institucional</strong>. El
                    sistema no puede leerlo automáticamente · click en{" "}
                    <strong>&ldquo;Abrir en SECOP II&rdquo;</strong> arriba para
                    verificar los datos con tu sesión.
                  </p>
                </>
              )}
              {isBorrador && (
                <>
                  <h3 className="serif text-base font-semibold text-amber-900 mb-1">
                    Este proceso aún está en preparación (borrador)
                  </h3>
                  <p className="text-sm text-ink leading-relaxed">
                    El SECOP todavía no publicó los datos de este proceso · está
                    en estado borrador. Cuando se publique, el sistema lo
                    detecta automáticamente y trae sus datos.
                  </p>
                </>
              )}
              {!isContratoInterno && !isBorrador && (
                <>
                  <h3 className="serif text-base font-semibold text-rose-900 mb-1">
                    Este proceso aún no aparece publicado en SECOP
                  </h3>
                  <p className="text-sm text-ink leading-relaxed">
                    Las APIs públicas del SECOP no exponen este proceso ·
                    puede ser un borrador, un proceso cancelado, o uno en
                    limbo. Click en <strong>&ldquo;Abrir en SECOP II&rdquo;</strong>{" "}
                    arriba para verlo manualmente.
                  </p>
                </>
              )}
            </section>
          )}

          {/* MODIFICATORIOS · CARDINAL PURO REAL · sección destacada
              porque Camila los prioriza explícitamente (memoria
              feedback_modal_modificatorios_destacada.md). Los detectamos
              automáticamente del scrape del link community.secop por
              patrón de nombre PDF. */}
          {!isLoading && hasPortalData && (() => {
            const modDocs = documents.filter((d) =>
              /modificatorio|otros[ií]|adendo|adicional al contrato/i.test(
                d.name ?? "",
              ),
            );
            if (modDocs.length === 0) return null;
            return (
              <section className="border-2 border-amber-300 bg-amber-50/50 rounded-md overflow-hidden">
                <div className="bg-amber-100/60 px-4 py-2.5 border-b border-amber-200">
                  <h3 className="serif text-base font-semibold text-amber-900">
                    📝 Modificatorios detectados ({modDocs.length})
                  </h3>
                  <p className="text-[11px] text-amber-800 mt-0.5">
                    PDFs encontrados en el link community.secop. Click en
                    cada uno para descargarlo y revisar los términos del
                    modificatorio.
                  </p>
                </div>
                <ul className="divide-y divide-amber-200/50">
                  {modDocs.map((doc, i) => (
                    <li
                      key={i}
                      className="px-3 py-2.5 flex items-start gap-2 hover:bg-amber-50"
                    >
                      <ChevronRight className="h-3 w-3 mt-1 text-amber-700 flex-shrink-0" />
                      <a
                        href={doc.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-burgundy hover:underline text-sm flex-1 font-medium"
                      >
                        {doc.name}
                      </a>
                    </li>
                  ))}
                </ul>
              </section>
            );
          })()}

          {/* DATOS DEL PORTAL · todos los campos · cardinal "ver todo" */}
          {!isLoading && hasPortalData && (
            <>
              <section className="border border-rule rounded-md overflow-hidden">
                <div className="bg-surface px-4 py-2.5 border-b border-rule">
                  <h3 className="serif text-base font-semibold text-ink">
                    Datos del proceso (extraídos del link)
                  </h3>
                  <p className="text-[11px] text-ink-soft mt-0.5">
                    Espejo cardinal de lo que la entidad publicó en{" "}
                    <strong>community.secop.gov.co</strong>. Si necesitás
                    verificar algún campo, click &ldquo;Abrir en SECOP II&rdquo;
                    arriba.
                  </p>
                </div>
                <table className="w-full text-sm">
                  <tbody>
                    {orderedFields.map((field, i) => {
                      const label =
                        PORTAL_FIELD_LABELS[field] ?? humanizeFieldName(field);
                      const value = fields[field];
                      return (
                        <tr
                          key={field}
                          className={cn(
                            "border-b border-rule/50 last:border-0",
                            i % 2 === 0 ? "bg-background" : "bg-surface",
                          )}
                        >
                          <td className="px-3 py-2 w-1/3 text-ink-soft text-[11px] uppercase tracking-wide font-medium align-top">
                            {label}
                          </td>
                          <td className="px-3 py-2 text-ink align-top">
                            {renderValue(value)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </section>

              {/* DOCUMENTOS PUBLICADOS · si los hay */}
              {documents.length > 0 && (
                <section className="border border-rule rounded-md overflow-hidden">
                  <div className="bg-surface px-4 py-2.5 border-b border-rule">
                    <h3 className="serif text-base font-semibold text-ink">
                      Documentos publicados ({documents.length})
                    </h3>
                  </div>
                  <ul className="divide-y divide-rule/50">
                    {documents.map((doc, i) => (
                      <li key={i} className="px-3 py-2 flex items-start gap-2">
                        <ChevronRight className="h-3 w-3 mt-1 text-ink-soft flex-shrink-0" />
                        <a
                          href={doc.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-burgundy hover:underline text-sm flex-1"
                        >
                          {doc.name}
                        </a>
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              {/* NOTIFICACIONES DEL PROCESO · si las hay */}
              {notificaciones.length > 0 && (
                <section className="border border-rule rounded-md overflow-hidden">
                  <div className="bg-surface px-4 py-2.5 border-b border-rule">
                    <h3 className="serif text-base font-semibold text-ink">
                      Notificaciones del proceso ({notificaciones.length})
                    </h3>
                  </div>
                  <ul className="divide-y divide-rule/50">
                    {notificaciones.map((n, i) => (
                      <li key={i} className="px-3 py-2 text-sm">
                        <div className="text-ink font-medium">{n.evento}</div>
                        <div className="text-[11px] text-ink-soft mt-0.5">
                          {n.proceso} · {n.fecha}
                        </div>
                      </li>
                    ))}
                  </ul>
                </section>
              )}
            </>
          )}

          {/* FOOTER · trazabilidad cardinal · auditable */}
          <footer className="border-t border-rule pt-3 mt-4 text-[10px] text-ink-soft font-mono">
            <div>process_id: {contractId ?? "—"}</div>
            {scrapedAt && (
              <div>scrape del link: {scrapedAt}</div>
            )}
            {status && (
              <div>status del scrape: {status}</div>
            )}
            <div>code version: cardinal-puro · 2026-04-27</div>
          </footer>
        </div>

        <div className="flex justify-end gap-2 mt-4 pt-3 border-t border-rule">
          <Button
            variant="ghost"
            onClick={() => onOpenChange(false)}
          >
            Cerrar
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
