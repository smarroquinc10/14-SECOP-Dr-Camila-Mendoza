"use client";

import * as React from "react";
import useSWR from "swr";
import {
  ChevronDown,
  ChevronRight,
  Download,
  ExternalLink,
  Globe,
  Loader2,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api, type ContractDetail, type PortalSnapshot } from "@/lib/api";
import { cn, confidenceColor, fmtDate, moneyCO } from "@/lib/utils";

interface Props {
  contractId: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/** Friendly Spanish labels for raw SECOP fields, grouped by section. */
const SECTIONS: { label: string; fields: [string, string][] }[] = [
  {
    label: "Identificación",
    fields: [
      ["id_contrato", "Código del contrato"],
      ["referencia_del_contrato", "Referencia FEAB"],
      ["proceso_de_compra", "Portafolio (CO1.BDOS)"],
      ["nombre_entidad", "Entidad contratante"],
      ["nit_entidad", "NIT entidad"],
      ["objeto_del_contrato", "Objeto"],
      ["modalidad_de_contratacion", "Modalidad de contratación"],
      ["tipo_de_contrato", "Tipo de contrato"],
      ["justificacion_modalidad_de", "Justificación modalidad"],
    ],
  },
  {
    label: "Estado y fechas",
    fields: [
      ["estado_contrato", "Estado del contrato"],
      ["fecha_de_firma", "Fecha de firma"],
      ["fecha_de_inicio_del_contrato", "Fecha de inicio"],
      ["fecha_de_fin_del_contrato", "Fecha de terminación"],
      ["fecha_inicio_liquidacion", "Inicio de liquidación"],
      ["fecha_fin_liquidacion", "Fin de liquidación"],
      ["liquidaci_n", "¿Requiere liquidación?"],
      ["duraci_n_del_contrato", "Duración"],
      ["dias_adicionados", "Días adicionados (prórrogas)"],
      ["el_contrato_puede_ser_prorrogado", "¿Puede prorrogarse?"],
    ],
  },
  {
    label: "Valores",
    fields: [
      ["valor_del_contrato", "Valor inicial"],
      ["valor_facturado", "Valor facturado"],
      ["valor_pagado", "Valor pagado"],
      ["valor_pendiente_de_pago", "Pendiente de pago"],
      ["valor_pendiente_de_ejecucion", "Pendiente de ejecución"],
      ["valor_de_pago_adelantado", "Valor anticipo"],
      ["habilita_pago_adelantado", "¿Anticipo habilitado?"],
      ["origen_de_los_recursos", "Origen recursos"],
      ["destino_gasto", "Destino del gasto"],
    ],
  },
  {
    label: "Contratista",
    fields: [
      ["proveedor_adjudicado", "Razón social"],
      ["tipodocproveedor", "Tipo identificación"],
      ["documento_proveedor", "Número identificación"],
      ["nombre_representante_legal", "Representante legal"],
      ["domicilio_representante_legal", "Domicilio"],
      ["departamento", "Departamento"],
      ["ciudad", "Ciudad"],
      ["es_pyme", "¿Es PYME?"],
    ],
  },
  {
    label: "Supervisión y orden",
    fields: [
      ["nombre_supervisor", "Supervisor"],
      ["n_mero_de_documento_supervisor", "ID supervisor"],
      ["nombre_ordenador_del_gasto", "Ordenador del gasto"],
      ["nombre_ordenador_de_pago", "Ordenador de pago"],
    ],
  },
  {
    label: "Otros",
    fields: [
      ["rama", "Rama"],
      ["orden", "Orden"],
      ["sector", "Sector"],
      ["entidad_centralizada", "Entidad centralizada"],
      ["reversion", "¿Reversión?"],
      ["obligaci_n_ambiental", "Obligación ambiental"],
      ["espostconflicto", "Post-conflicto"],
      ["ultima_actualizacion", "Última actualización SECOP"],
    ],
  },
];

/** Set de field names ya cubiertos por las SECTIONS curadas. Cualquier
 *  campo del API jbjy-vk9h que no esté acá se renderiza al final en
 *  "Otros campos del API" — así nunca se "comen" datos del SECOP.
 *  La regla cardinal "espejo y reflejo fiel" exige que TODO lo que el
 *  API devuelva quede expuesto al usuario, aunque sea en una sección
 *  expandible secundaria. */
const CURATED_FIELDS: Set<string> = new Set(
  SECTIONS.flatMap((s) => s.fields.map(([k]) => k)),
);

/** Fields administrativos / de sistema que NUNCA es útil mostrar al
 *  usuario. Los excluimos explícitamente del "Otros campos" para no
 *  ensuciar el modal con basura. */
const NOISE_FIELDS: Set<string> = new Set([
  "_id",
  "_notas", // se computa en backend; ya se muestra como "Notas"
  ":@computed_region_y8tx_xa3w",
  ":@computed_region_b8mb_y23g",
  ":@computed_region_kpa3_pdzn",
  ":@computed_region_ck25_dyt8",
  ":@computed_region_g8jr_8txm",
  ":@computed_region_yyfu_pwt8",
]);

/** Money-shaped fields adicionales que pueden aparecer en "Otros campos". */
const MORE_MONEY_FIELDS = new Set([
  "saldo_cdp",
  "saldo_vigencia",
  "valor_amortizado",
  "presupuesto_general_de_la_nacion_pgn",
  "recursos_de_credito",
  "recursos_propios",
  "recursos_propios_alcald_as_gobernaciones_y_resguardos_ind_genas_",
  "sistema_general_de_participaciones",
  "sistema_general_de_regal_as",
]);

const MONEY_FIELDS = new Set([
  "valor_del_contrato",
  "valor_facturado",
  "valor_pagado",
  "valor_pendiente_de_pago",
  "valor_pendiente_de_ejecucion",
  "valor_de_pago_adelantado",
  ...MORE_MONEY_FIELDS,
]);
const DATE_FIELDS = new Set([
  "fecha_de_firma",
  "fecha_de_inicio_del_contrato",
  "fecha_de_fin_del_contrato",
  "fecha_inicio_liquidacion",
  "fecha_fin_liquidacion",
  "ultima_actualizacion",
]);

function fmtValue(field: string, raw: unknown): string {
  if (raw === null || raw === undefined || raw === "") return "—";
  const s = String(raw).trim();
  if (s.toLowerCase() === "no definido" || s.toLowerCase() === "nan") return "—";
  if (MONEY_FIELDS.has(field)) {
    const n = Number(s);
    if (!isFinite(n)) return s;
    return moneyCO.format(n);
  }
  if (DATE_FIELDS.has(field)) return fmtDate(s);
  return s;
}

export function DetailDialog({ contractId, open, onOpenChange }: Props) {
  const { data, error, isLoading } = useSWR<ContractDetail>(
    open && contractId ? `contract:${contractId}` : null,
    () => api.contract(contractId!)
  );

  const contract = data?.contratos?.[0] || {};
  const url =
    (contract as Record<string, unknown>).urlproceso?.toString() ?? "";

  // Estado del toggle de "Otros campos del API". Cerrado por default
  // para no abrumar — pero la data SIEMPRE está disponible al click.
  const [showAllApiFields, setShowAllApiFields] = React.useState(false);

  // Calculamos los campos del API NO cubiertos por SECTIONS — son los
  // 29 campos que antes se "comían". Filtramos vacíos y ruido conocido.
  const otrosCamposApi = React.useMemo(() => {
    const out: Array<[string, unknown]> = [];
    for (const [k, v] of Object.entries(contract as Record<string, unknown>)) {
      if (CURATED_FIELDS.has(k)) continue;
      if (NOISE_FIELDS.has(k)) continue;
      if (v === null || v === undefined || v === "") continue;
      const s = String(v).trim();
      if (!s) continue;
      const sl = s.toLowerCase();
      if (sl === "no definido" || sl === "nan" || sl === "null") continue;
      out.push([k, v]);
    }
    return out.sort((a, b) => a[0].localeCompare(b[0]));
  }, [contract]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <div className="eyebrow text-burgundy">Detalle del contrato</div>
          <DialogTitle>
            {(contract as Record<string, unknown>).referencia_del_contrato as string ??
              contractId ??
              "—"}
          </DialogTitle>
          <DialogDescription>
            {(contract as Record<string, unknown>).proveedor_adjudicado as string ?? ""}
          </DialogDescription>
          <div className="flex items-center gap-3 mt-2">
            {url && (
              <a
                href={url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-sm text-burgundy hover:underline"
              >
                Abrir en SECOP II <ExternalLink className="h-3.5 w-3.5" />
              </a>
            )}
            {data?.secop_hash && (
              <span className="inline-flex items-center gap-1 text-[11px] font-mono text-ink-soft">
                <ShieldCheck className="h-3.5 w-3.5 text-emerald-700" />
                {data.secop_hash.slice(0, 16)}…
              </span>
            )}
          </div>
        </DialogHeader>

        <div className="overflow-y-auto px-6 pb-6 max-h-[70vh]">
          {isLoading && (
            <div className="flex items-center gap-2 py-12 text-ink-soft">
              <Loader2 className="h-4 w-4 animate-spin" /> Consultando SECOP…
            </div>
          )}
          {error && (
            <div className="py-8 text-rose-700 text-sm">
              No pude consultar el detalle. Reintentar más tarde.
            </div>
          )}
          {data && (
            <div className="space-y-6">
              {data.needs_review.length > 0 && (
                <div className="border-l-4 border-amber-400 bg-amber-50 px-4 py-3 rounded">
                  <div className="text-[11px] font-semibold uppercase tracking-wider text-amber-700">
                    Celdas marcadas para revisión
                  </div>
                  <div className="mt-1 text-sm text-ink">
                    {data.needs_review.join(", ")}
                  </div>
                </div>
              )}

              {SECTIONS.map((section) => {
                const rows = section.fields
                  .map(([field, label]) => {
                    const value = (contract as Record<string, unknown>)[field];
                    if (value === null || value === undefined || value === "") return null;
                    return [field, label, value] as const;
                  })
                  .filter(
                    (r): r is readonly [string, string, NonNullable<unknown>] =>
                      r !== null,
                  );
                if (!rows.length) return null;
                return (
                  <section key={section.label}>
                    <div className="eyebrow mb-2">{section.label}</div>
                    <div className="border border-rule rounded-md overflow-hidden">
                      <table className="w-full text-sm">
                        <tbody>
                          {rows.map(([field, label, value], i) => {
                            const conf = data.feab_confidence?.[label];
                            const src = data.feab_sources?.[label];
                            return (
                              <tr
                                key={field}
                                className={cn(
                                  "border-b border-rule/50 last:border-0",
                                  i % 2 === 0 ? "bg-background" : "bg-surface"
                                )}
                              >
                                <td className="px-3 py-2 w-1/3 text-ink-soft text-xs uppercase tracking-wide">
                                  {label}
                                </td>
                                <td className="px-3 py-2 text-ink">
                                  {fmtValue(field, value)}
                                </td>
                                <td className="px-3 py-2 w-32">
                                  {conf && (
                                    <Badge className={confidenceColor(conf)}>
                                      {conf}
                                    </Badge>
                                  )}
                                  {src && (
                                    <div className="text-[10px] font-mono text-ink-soft mt-1">
                                      {src}
                                    </div>
                                  )}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </section>
                );
              })}

              {/* Otros campos del API jbjy-vk9h que las SECTIONS curadas no
                  cubren. Antes este bloque NO existía y el modal mostraba
                  44/73 campos — los 29 restantes ("descripcion_del_proceso",
                  "condiciones_de_entrega", etc.) quedaban invisibles para
                  la Dra aunque el API los devolviera. Cardinal violation.
                  Ahora se muestran SIEMPRE, escondidos detrás de un toggle
                  para no abrumar el modal por default. */}
              {otrosCamposApi.length > 0 && (
                <section>
                  <button
                    onClick={() => setShowAllApiFields((s) => !s)}
                    className="inline-flex items-center gap-1 text-xs text-burgundy hover:underline"
                  >
                    {showAllApiFields ? (
                      <ChevronDown className="h-3 w-3" />
                    ) : (
                      <ChevronRight className="h-3 w-3" />
                    )}
                    Otros campos del API SECOP ({otrosCamposApi.length})
                  </button>
                  {showAllApiFields && (
                    <div className="mt-2 border border-rule rounded-md overflow-hidden">
                      <table className="w-full text-sm">
                        <tbody>
                          {otrosCamposApi.map(([field, value], i) => (
                            <tr
                              key={field}
                              className={cn(
                                "border-b border-rule/50 last:border-0",
                                i % 2 === 0 ? "bg-background" : "bg-surface",
                              )}
                            >
                              <td className="px-3 py-2 w-1/3 text-ink-soft text-[10px] uppercase tracking-wide font-mono">
                                {field.replace(/_/g, " ")}
                              </td>
                              <td className="px-3 py-2 text-ink whitespace-pre-wrap">
                                {fmtValue(field, value)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </section>
              )}

              {/* Adiciones */}
              {Object.values(data.adiciones_by_contrato).some((a) => a.length > 0) && (
                <section>
                  <div className="eyebrow mb-2">
                    Adiciones / Modificatorios al contrato
                  </div>
                  <div className="border border-rule rounded-md overflow-hidden">
                    <table className="w-full text-sm">
                      <thead className="bg-surface text-[11px] uppercase tracking-wider text-ink-soft">
                        <tr>
                          <th className="text-left px-3 py-2">Tipo</th>
                          <th className="text-left px-3 py-2">Valor</th>
                          <th className="text-left px-3 py-2">Fecha</th>
                          <th className="text-left px-3 py-2">Descripción</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.values(data.adiciones_by_contrato)
                          .flat()
                          .map((a, i) => (
                            <tr
                              key={i}
                              className="border-b border-rule/50 last:border-0"
                            >
                              <td className="px-3 py-2">{(a.tipo as string) ?? "—"}</td>
                              <td className="px-3 py-2 font-mono">
                                {moneyCO.format(Number(a.valor ?? 0))}
                              </td>
                              <td className="px-3 py-2 font-mono text-ink-soft">
                                {fmtDate((a.fecha_adicion as string) ?? "")}
                              </td>
                              <td className="px-3 py-2 text-xs text-ink-soft">
                                {((a.descripcion_adicion as string) ?? "").slice(0, 80)}
                              </td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              )}

              {/* Modificatorios al PROCESO (distintos a adiciones de contrato).
                  Vienen del dataset SECOP de modificatorios de proceso. */}
              {data.mods_proceso?.length > 0 && (
                <section>
                  <div className="eyebrow mb-2">
                    Modificatorios al proceso ({data.mods_proceso.length})
                  </div>
                  <div className="border border-rule rounded-md overflow-hidden">
                    <table className="w-full text-sm">
                      <thead className="bg-surface text-[11px] uppercase tracking-wider text-ink-soft">
                        <tr>
                          <th className="text-left px-3 py-2">Tipo</th>
                          <th className="text-left px-3 py-2">Fecha</th>
                          <th className="text-left px-3 py-2">Descripción</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.mods_proceso.map((m, i) => (
                          <tr
                            key={i}
                            className="border-b border-rule/50 last:border-0"
                          >
                            <td className="px-3 py-2">
                              {((m.tipo_modificacion as string) ??
                                (m.tipo as string)) ??
                                "—"}
                            </td>
                            <td className="px-3 py-2 font-mono text-ink-soft">
                              {fmtDate(
                                (m.fecha_modificacion as string) ??
                                  (m.fecha as string) ??
                                  "",
                              )}
                            </td>
                            <td className="px-3 py-2 text-xs text-ink-soft">
                              {((m.descripcion as string) ??
                                (m.justificacion as string) ??
                                "").slice(0, 120)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              )}

              {/* DATOS DEL PORTAL — cascada de fuentes públicas:
                  1. SECOP Integrado (rpmr-utcd) — sin captcha, datos.gov.co
                  2. Portal scrape snapshot — community.secop.gov.co
                  3. Botón "Leer del portal" si nada tiene el proceso

                  Cada link expone campos distintos; renderizamos TODO
                  lo capturado sin alucinar / asumir / inventar. */}
              {data.notice_uid && (
                <PortalSection noticeUid={data.notice_uid} />
              )}

              {/* OBSERVACIONES de la Dra (notas escritas a mano en el Excel).
                  Vienen del Excel master, no de SECOP. */}
              {data.observaciones_dra?.length > 0 && (
                <section>
                  <div className="eyebrow mb-2">
                    Observaciones de la Dra ({data.observaciones_dra.length})
                  </div>
                  <div className="border border-rule rounded-md divide-y divide-rule/50">
                    {data.observaciones_dra.map((o, i) => (
                      <div key={i} className="p-3">
                        <div className="text-[10px] font-mono text-ink-soft uppercase tracking-wider mb-1">
                          {o.sheet} · fila {o.row}
                        </div>
                        <div className="text-sm text-ink whitespace-pre-wrap">
                          {o.text}
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              <div className="text-[10px] font-mono text-ink-soft pt-4 border-t border-rule">
                Hash SECOP completo: {data.secop_hash}
                <br />
                Code version: {data.code_version} · Consultado:{" "}
                {data.fetched_at}
              </div>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}


/* ─────────────────────────────────────────────────────────────────────
 * PortalSection — espejo del HTML del portal SECOP para un proceso.
 *
 * - Cada proceso del portal tiene campos diferentes; renderizamos el
 *   `all_labels` completo (label normalizado → valor) sin curar.
 * - Si el snapshot no existe aún, mostramos un botón "Leer ahora" que
 *   dispara el scraper en backend.
 * - Status badge: ok_completo (verde) / ok_parcial (ámbar) / errored (rojo).
 * - "Re-leer del portal" fuerza un re-scrape (--force) cuando la Dra
 *   sospecha que cambió algo.
 * - NUNCA inventar valores: vacío → "—".
 * ──────────────────────────────────────────────────────────────────── */

const PORTAL_STATUS_LABEL: Record<string, { label: string; cls: string }> = {
  ok_completo: { label: "Espejo completo", cls: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  ok_parcial:  { label: "Espejo parcial",  cls: "bg-amber-50 text-amber-700 border-amber-200" },
  bloqueado_captcha: { label: "Bloqueado por captcha", cls: "bg-rose-50 text-rose-700 border-rose-200" },
  error_red: { label: "Error de red", cls: "bg-rose-50 text-rose-700 border-rose-200" },
  no_disponible: { label: "No disponible", cls: "bg-stone-50 text-stone-700 border-stone-200" },
};

function PortalSection({ noticeUid }: { noticeUid: string }) {
  // Cascada: primero consulta SECOP Integrado (rpmr-utcd, sin captcha).
  // Si está, mostramos esos campos como fuente principal. En paralelo
  // pedimos el snapshot del portal scrape (puede estar o no). Solo si
  // NINGUNO tiene el proceso, ofrecemos el botón "Leer del portal".
  const { data: integ, error: integError, isLoading: integLoading } =
    useSWR(
      `integ:${noticeUid}`,
      () => api.contractIntegrado(noticeUid),
    );
  const { data, error, isLoading, mutate } = useSWR<PortalSnapshot>(
    `portal:${noticeUid}`,
    () => api.contractPortal(noticeUid),
  );
  const [scraping, setScraping] = React.useState(false);
  const [showAllLabels, setShowAllLabels] = React.useState(false);

  async function triggerScrape(force = false) {
    setScraping(true);
    try {
      await api.portalScrape({ uid: noticeUid, force });
      // Espera 3s y refresca, luego sigue refrescando cada 5s mientras esté corriendo
      const poll = async (attempts: number): Promise<void> => {
        await new Promise((r) => setTimeout(r, 3000));
        const snap = await api.contractPortal(noticeUid).catch(() => null);
        if (snap?.available && snap.status === "ok_completo") {
          mutate(snap);
          return;
        }
        if (attempts > 0) return poll(attempts - 1);
        mutate();
      };
      await poll(20); // hasta ~60s
    } finally {
      setScraping(false);
    }
  }

  // Render del Integrado siempre que esté disponible (primero en la
  // cascada, sin captcha). Lo mostramos antes del snapshot del portal.
  const integFields = integ?.available ? (integ.fields ?? {}) : {};
  const integEntries = Object.entries(integFields).filter(
    ([k, v]) => v && k !== "_notice_uid",
  );
  const integRender = integ?.available && integEntries.length > 0 && (
    <section>
      <div className="eyebrow mb-2 flex items-center gap-1.5">
        <Globe className="h-3 w-3" /> SECOP Integrado · datos.gov.co
        <span className="ml-1 inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium border bg-emerald-50 text-emerald-700 border-emerald-200">
          Sin captcha
        </span>
      </div>
      {integ.synced_at && (
        <div className="text-[10px] font-mono text-ink-soft mb-2">
          Sincronizado: {integ.synced_at} · {integEntries.length} campos · {integ.source}
        </div>
      )}
      <div className="border border-rule rounded-md overflow-hidden mb-3">
        <table className="w-full text-sm">
          <tbody>
            {integEntries.map(([k, v], i) => (
              <tr
                key={k}
                className={cn(
                  "border-b border-rule/50 last:border-0",
                  i % 2 === 0 ? "bg-background" : "bg-surface",
                )}
              >
                <td className="px-3 py-2 w-1/3 text-ink-soft text-xs uppercase tracking-wide">
                  {k.replace(/_/g, " ")}
                </td>
                <td className="px-3 py-2 text-ink whitespace-pre-wrap">{v}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );

  if (isLoading || integLoading) {
    return (
      <section>
        <div className="eyebrow mb-2 flex items-center gap-1.5">
          <Globe className="h-3 w-3" /> Datos del portal SECOP
        </div>
        <div className="flex items-center gap-2 text-ink-soft text-xs py-3">
          <Loader2 className="h-3.5 w-3.5 animate-spin" /> Consultando datos públicos…
        </div>
      </section>
    );
  }

  if (error) {
    return (
      <>
        {integRender}
        <section>
          <div className="eyebrow mb-2 flex items-center gap-1.5">
            <Globe className="h-3 w-3" /> Snapshot del portal
          </div>
          <div className="text-rose-700 text-xs py-3">
            No pude consultar el snapshot del portal.
          </div>
        </section>
      </>
    );
  }

  if (!data?.available) {
    // Si Integrado YA tiene los datos, mostramos eso y solo
    // ofrecemos el portal scrape como bonus (más detalle: documentos,
    // notificaciones, etc.). Si Integrado NO tiene, el portal scrape
    // pasa a ser la única opción.
    return (
      <>
        {integRender}
        <section>
          <div className="eyebrow mb-2 flex items-center gap-1.5">
            <Globe className="h-3 w-3" /> Snapshot detallado del portal
            {integ?.available && (
              <span className="text-[10px] text-ink-soft italic ml-1">
                (opcional — ya tenés los datos arriba)
              </span>
            )}
          </div>
          <div className="border border-dashed border-rule rounded-md p-4 bg-surface">
            <p className="text-sm text-ink-soft mb-3">
              {integ?.available
                ? "Para ver documentos del proceso (pliegos, adendas, modificatorios) " +
                  "podés leer el portal — agrega información que el dataset Integrado no tiene."
                : "Este proceso no está en el dataset Integrado ni en el snapshot del " +
                  "portal. Lectura del portal es la única fuente que queda."}
            </p>
            <Button
              onClick={() => triggerScrape(false)}
              disabled={scraping}
              className="gap-2"
              size="sm"
              variant={integ?.available ? "outline" : "default"}
            >
              {scraping ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Download className="h-3.5 w-3.5" />
              )}
              {integ?.available
                ? "Leer documentos del portal"
                : "Leer del portal ahora"}
            </Button>
            <p className="text-[11px] text-ink-soft mt-2 italic">
              * Abre Chrome visible. Si SECOP pide captcha, el solver
              automático lo intenta (audio en español); si falla, lo
              resolvés una vez y queda guardado para los siguientes.
            </p>
          </div>
        </section>
      </>
    );
  }

  const status = data.status ?? "ok_completo";
  const statusInfo = PORTAL_STATUS_LABEL[status] ?? PORTAL_STATUS_LABEL.ok_completo;
  const fields = data.fields ?? {};
  const allLabels = data.all_labels ?? {};
  const docs = data.documents ?? [];
  const notifs = data.notificaciones ?? [];
  const fieldEntries = Object.entries(fields).filter(([, v]) => v && v.trim());
  const labelEntries = Object.entries(allLabels).filter(([, v]) => v && v.trim());
  const labelEntriesNotInFields = labelEntries.filter(
    ([k]) => !fieldEntries.some(([fk]) => fk.toLowerCase() === k.toLowerCase()),
  );

  return (
    <>
    {integRender}
    <section className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <div className="eyebrow flex items-center gap-1.5">
          <Globe className="h-3 w-3" /> Snapshot del portal SECOP
          <span
            className={cn(
              "ml-1 inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium border",
              statusInfo.cls,
            )}
          >
            {statusInfo.label}
          </span>
          {data.missing_fields && data.missing_fields.length > 0 && (
            <span className="ml-1 text-[10px] text-amber-700">
              · faltan: {data.missing_fields.join(", ")}
            </span>
          )}
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => triggerScrape(true)}
          disabled={scraping}
          className="gap-1 text-xs"
          title="Re-leer del portal (forzar)"
        >
          {scraping ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : (
            <RefreshCw className="h-3 w-3" />
          )}
          Re-leer
        </Button>
      </div>

      {data.scraped_at && (
        <div className="text-[10px] font-mono text-ink-soft">
          Leído del portal: {data.scraped_at} · {labelEntries.length} campos ·{" "}
          {docs.length} documentos · {notifs.length} notificaciones
        </div>
      )}

      {fieldEntries.length > 0 && (
        <div className="border border-rule rounded-md overflow-hidden">
          <table className="w-full text-sm">
            <tbody>
              {fieldEntries.map(([k, v], i) => (
                <tr
                  key={k}
                  className={cn(
                    "border-b border-rule/50 last:border-0",
                    i % 2 === 0 ? "bg-background" : "bg-surface",
                  )}
                >
                  <td className="px-3 py-2 w-1/3 text-ink-soft text-xs uppercase tracking-wide">
                    {k.replace(/_/g, " ")}
                  </td>
                  <td className="px-3 py-2 text-ink whitespace-pre-wrap">
                    {v}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {labelEntriesNotInFields.length > 0 && (
        <div>
          <button
            onClick={() => setShowAllLabels((s) => !s)}
            className="inline-flex items-center gap-1 text-xs text-burgundy hover:underline"
          >
            {showAllLabels ? (
              <ChevronDown className="h-3 w-3" />
            ) : (
              <ChevronRight className="h-3 w-3" />
            )}
            Ver TODOS los campos crudos del portal ({labelEntriesNotInFields.length} más)
          </button>
          {showAllLabels && (
            <div className="mt-2 border border-rule rounded-md overflow-hidden">
              <table className="w-full text-xs">
                <tbody>
                  {labelEntriesNotInFields.map(([k, v], i) => (
                    <tr
                      key={k}
                      className={cn(
                        "border-b border-rule/50 last:border-0",
                        i % 2 === 0 ? "bg-background" : "bg-surface",
                      )}
                    >
                      <td className="px-3 py-1.5 w-1/2 text-ink-soft font-mono text-[10px]">
                        {k}
                      </td>
                      <td className="px-3 py-1.5 text-ink whitespace-pre-wrap">
                        {v}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {docs.length > 0 && (
        <div>
          <div className="eyebrow mb-1.5">Documentos del proceso ({docs.length})</div>
          <ul className="border border-rule rounded-md divide-y divide-rule/50">
            {docs.map((d, i) => (
              <li key={i} className="px-3 py-2 flex items-center justify-between gap-2 text-xs">
                <span className="text-ink truncate flex-1">{d.name}</span>
                {d.url && (
                  <a
                    href={d.url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 text-burgundy hover:underline shrink-0"
                  >
                    <Download className="h-3 w-3" /> Descargar
                  </a>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {notifs.length > 0 && (
        <div>
          <div className="eyebrow mb-1.5">Notificaciones del proceso ({notifs.length})</div>
          <div className="border border-rule rounded-md overflow-hidden">
            <table className="w-full text-xs">
              <thead className="bg-surface text-[10px] uppercase tracking-wider text-ink-soft">
                <tr>
                  <th className="text-left px-3 py-1.5">Proceso</th>
                  <th className="text-left px-3 py-1.5">Evento</th>
                  <th className="text-left px-3 py-1.5">Fecha</th>
                </tr>
              </thead>
              <tbody>
                {notifs.map((n, i) => (
                  <tr key={i} className="border-b border-rule/50 last:border-0">
                    <td className="px-3 py-1.5 font-mono text-[10px]">{n.proceso}</td>
                    <td className="px-3 py-1.5">{n.evento}</td>
                    <td className="px-3 py-1.5 font-mono text-ink-soft">{n.fecha}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
    </>
  );
}
