"use client";

import * as React from "react";
import useSWR from "swr";
import { ExternalLink, TrendingUp } from "lucide-react";

import { api, type ModSummary } from "@/lib/api";
import { fmtDate, moneyCO } from "@/lib/utils";

/**
 * Top-of-page panel: summary of every contract that has been modified.
 *
 * Shows:
 *  - Total contracts modified across the FEAB portfolio
 *  - Total días added across all prórrogas
 *  - The MOST RECENT modificatorio (with provider + date)
 *  - Last 5 modificatorios in a compact list
 */
export function ModsPanel({
  onPickContract,
}: {
  onPickContract: (id: string) => void;
}) {
  const { data, isLoading } = useSWR<ModSummary>(
    "mods:20",
    () => api.modificatoriosRecientes(20),
    { refreshInterval: 60_000 }
  );

  if (isLoading || !data) {
    return (
      <div className="border border-rule rounded-lg bg-surface p-5 animate-pulse">
        <div className="h-3 w-32 bg-stone-200 rounded mb-3" />
        <div className="h-6 w-72 bg-stone-200 rounded" />
      </div>
    );
  }

  return (
    <div className="border-2 border-amber-300 rounded-lg bg-amber-50/30 overflow-hidden shadow-sm">
      {/* Header explicativo — feedback de la Dra: "los modificatorios son
          lo más relevante, ella no tiene que abrir link por link". Esta
          sección le permite ver de un vistazo qué contratos cambiaron sin
          ir al SECOP. */}
      <div className="bg-amber-100/60 px-5 py-3 border-b border-amber-200">
        <h3 className="serif text-base font-semibold text-amber-900 flex items-center gap-2">
          <TrendingUp className="h-4 w-4" />
          Modificatorios — lo más relevante a revisar
        </h3>
        <p className="text-xs text-amber-800 mt-0.5">
          Contratos del FEAB que cambiaron en SECOP (prórrogas, días adicionados,
          adiciones de valor, etc). Acá los ves todos sin abrir link por link.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-px bg-rule">
        <div
          className="bg-surface p-5"
          title="Cantidad de contratos del FEAB que tienen al menos una modificación registrada en SECOP (prórroga, adición de valor, cambio de plazo o estado 'modificado')."
        >
          <div className="eyebrow flex items-center gap-1.5">
            <TrendingUp className="h-3 w-3" />
            Contratos modificados
          </div>
          <div className="serif text-3xl font-semibold text-ink mt-1">
            {data.total_modificados}
          </div>
          <div className="text-xs text-ink-soft">
            del FEAB con cambios registrados en SECOP
          </div>
        </div>
        <div className="bg-surface p-5">
          <div className="eyebrow">Último modificatorio detectado</div>
          {data.ultimo ? (
            <>
              <div className="font-mono text-base text-ink mt-1">
                {fmtDate(
                  data.ultimo.fecha_notificacion_prorroga ||
                    data.ultimo.fecha_actualizacion ||
                    data.ultimo.fecha_fin
                )}
              </div>
              <button
                onClick={() => onPickContract(data.ultimo!.id_contrato)}
                className="text-xs text-burgundy hover:underline truncate block max-w-full mt-0.5 text-left"
                title={`Click para ver detalle completo · ${data.ultimo.objeto ?? ""}`}
              >
                {data.ultimo.proveedor} — {data.ultimo.referencia}
              </button>
              <div className="text-[10px] text-ink-soft mt-1 italic">
                Click el nombre → ver detalle del contrato
              </div>
            </>
          ) : (
            <div className="text-sm text-ink-soft italic mt-1">Sin registros.</div>
          )}
        </div>
      </div>

      {data.items.length > 0 && (
        <details className="border-t border-rule">
          <summary className="px-5 py-3 cursor-pointer text-xs uppercase tracking-wider text-burgundy hover:bg-background/50 select-none flex items-center gap-2">
            <span>▶ Ver detalle de los últimos {data.items.length} modificatorios</span>
            <span className="text-[10px] normal-case tracking-normal text-ink-soft italic">
              fecha · contrato · proveedor · días añadidos · valor
            </span>
          </summary>
          <div className="border-t border-rule">
            <table className="w-full text-sm">
              <thead className="bg-background text-[11px] uppercase tracking-wider text-ink-soft">
                <tr>
                  <th className="text-left px-4 py-2">Fecha</th>
                  <th className="text-left px-4 py-2">Contrato</th>
                  <th className="text-left px-4 py-2">Proveedor</th>
                  <th className="text-right px-4 py-2">Días +</th>
                  <th className="text-right px-4 py-2">Valor</th>
                  <th className="text-left px-4 py-2 w-16">SECOP</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((it) => (
                  <tr
                    key={it.id_contrato}
                    onClick={() => onPickContract(it.id_contrato)}
                    className="border-t border-rule/60 hover:bg-background cursor-pointer"
                  >
                    <td className="px-4 py-2 font-mono text-ink-soft">
                      {fmtDate(
                        it.fecha_notificacion_prorroga ||
                          it.fecha_actualizacion ||
                          it.fecha_fin
                      )}
                    </td>
                    <td className="px-4 py-2 font-mono text-xs">
                      {it.referencia ?? it.id_contrato}
                    </td>
                    <td className="px-4 py-2 truncate max-w-xs">{it.proveedor}</td>
                    <td className="px-4 py-2 font-mono text-right">
                      {it.dias_adicionados > 0 ? `+${it.dias_adicionados}` : "—"}
                    </td>
                    <td className="px-4 py-2 font-mono text-right text-xs tabular-nums">
                      {moneyCO.format(Number(it.valor ?? 0))}
                    </td>
                    <td className="px-4 py-2">
                      {it.url && (
                        <a
                          href={it.url}
                          target="_blank"
                          rel="noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="inline-flex items-center gap-1 text-xs text-burgundy hover:underline"
                        >
                          Abrir <ExternalLink className="h-3 w-3" />
                        </a>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </div>
  );
}
