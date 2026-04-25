"use client";

import * as React from "react";
import useSWR from "swr";
import { ExternalLink, Plus, TrendingUp } from "lucide-react";

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
    <div className="border border-rule rounded-lg bg-surface overflow-hidden">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-px bg-rule">
        <div className="bg-surface p-5">
          <div className="eyebrow flex items-center gap-1.5">
            <TrendingUp className="h-3 w-3" />
            Modificatorios
          </div>
          <div className="serif text-3xl font-semibold text-ink mt-1">
            {data.total_modificados}
          </div>
          <div className="text-xs text-ink-soft">contratos con modificación</div>
        </div>
        <div className="bg-surface p-5">
          <div className="eyebrow flex items-center gap-1.5">
            <Plus className="h-3 w-3" />
            Días adicionados
          </div>
          <div className="serif text-3xl font-semibold text-ink mt-1">
            {data.total_dias_adicionados.toLocaleString("es-CO")}
          </div>
          <div className="text-xs text-ink-soft">total agregado en prórrogas</div>
        </div>
        <div className="bg-surface p-5">
          <div className="eyebrow">Último modificatorio</div>
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
                className="text-xs text-burgundy hover:underline truncate block max-w-full mt-0.5"
                title={data.ultimo.objeto}
              >
                {data.ultimo.proveedor} — {data.ultimo.referencia}
              </button>
            </>
          ) : (
            <div className="text-sm text-ink-soft italic mt-1">Sin registros.</div>
          )}
        </div>
      </div>

      {data.items.length > 0 && (
        <details className="border-t border-rule">
          <summary className="px-5 py-3 cursor-pointer text-xs uppercase tracking-wider text-burgundy hover:bg-background/50 select-none">
            Ver últimos {data.items.length} modificatorios
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
