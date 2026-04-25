"use client";

import * as React from "react";
import useSWR from "swr";
import { ExternalLink, Loader2, ShieldCheck } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { api, type ContractDetail } from "@/lib/api";
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

const MONEY_FIELDS = new Set([
  "valor_del_contrato",
  "valor_facturado",
  "valor_pagado",
  "valor_pendiente_de_pago",
  "valor_pendiente_de_ejecucion",
  "valor_de_pago_adelantado",
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

              {/* Adiciones */}
              {Object.values(data.adiciones_by_contrato).some((a) => a.length > 0) && (
                <section>
                  <div className="eyebrow mb-2">
                    Adiciones / Modificatorios
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
