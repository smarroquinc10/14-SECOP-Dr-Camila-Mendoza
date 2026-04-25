"use client";

import * as React from "react";
import {
  Check,
  ExternalLink,
  Pencil,
  Plus,
  Trash2,
  X as XIcon,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  api,
  type Contract,
  type WatchedItem,
} from "@/lib/api";
import { cn, fmtDate, moneyCO } from "@/lib/utils";

/**
 * Unified row: one entry that may come from the watch list, the SECOP
 * contracts API, or both. The Dra cares about ONE list — her processes
 * — so we merge the two sources by process_id / proceso_de_compra and
 * surface every relevant field side by side.
 */
export interface UnifiedRow {
  // Stable key used by React. Prefer id_contrato; fall back to URL.
  key: string;

  // Identification
  process_id: string | null;
  id_contrato: string | null;
  notice_uid: string | null;
  url: string | null;

  // From SECOP contracts dataset (if matched)
  objeto: string | null;
  proveedor: string | null;
  valor: number | null;
  fecha_firma: string | null;
  estado: string | null;
  modalidad: string | null;
  notas: string | null;
  dias_adicionados: number | null;
  liquidado: boolean;

  // From watch list (if present)
  sheets: string[];
  vigencias: string[];
  appearances_count: number;
  watched: boolean;
  watch_url: string | null;

  // Verify status taxonomy (derived)
  verifyStatus: "verificado" | "contrato_firmado" | "borrador" | "no_en_api";
}


function classifyStatus(
  watch: WatchedItem | null,
  contract: Contract | null,
): UnifiedRow["verifyStatus"] {
  // 1. If we have an API contract, it IS in the public API.
  if (contract?.id_contrato) return "contrato_firmado";
  // 2. If watch has notice_uid resolved, it's verified against datos.gov.co.
  if (watch?.notice_uid) return "verificado";
  // 3. If process_id is a workspace ID (REQ/BDOS), it's a draft.
  const pid = watch?.process_id ?? "";
  if (pid.startsWith("CO1.REQ.") || pid.startsWith("CO1.BDOS.")) {
    return "borrador";
  }
  // 4. Otherwise: not in the public API.
  return "no_en_api";
}


/**
 * Merge the watch list with SECOP contracts into one row-per-process
 * list. A contract whose `proceso_de_compra` matches a watched item's
 * process_id (or notice_uid, or URL) is folded into that watch row.
 * Orphan contracts (in SECOP, not in watch) get added at the end.
 */
export function buildUnifiedRows(
  watched: WatchedItem[],
  contracts: Contract[],
): UnifiedRow[] {
  // Index contracts by every key we may match against
  const byIdContrato = new Map<string, Contract>();
  const byProceso = new Map<string, Contract>();
  for (const c of contracts) {
    if (c.id_contrato) byIdContrato.set(c.id_contrato, c);
    if (c.proceso_de_compra && !byProceso.has(c.proceso_de_compra as string)) {
      byProceso.set(c.proceso_de_compra as string, c);
    }
  }

  const usedContracts = new Set<string>();
  const rows: UnifiedRow[] = [];

  for (const w of watched) {
    let contract: Contract | null = null;
    if (w.process_id) {
      contract =
        byIdContrato.get(w.process_id) ?? byProceso.get(w.process_id) ?? null;
    }
    if (!contract && w.notice_uid) {
      contract = byProceso.get(w.notice_uid) ?? null;
    }
    if (contract?.id_contrato) usedContracts.add(contract.id_contrato);

    const dias = parseInt(String(contract?.dias_adicionados ?? "0"), 10);
    const liq =
      String(contract?.liquidaci_n ?? "")
        .trim()
        .toLowerCase() === "si";

    rows.push({
      key: contract?.id_contrato ?? w.url,
      process_id: w.process_id,
      id_contrato: contract?.id_contrato ?? null,
      notice_uid: w.notice_uid ?? contract?.proceso_de_compra ?? null,
      url: w.url,
      objeto: (contract?.objeto_del_contrato as string) ?? null,
      proveedor: (contract?.proveedor_adjudicado as string) ?? null,
      valor: contract?.valor_del_contrato
        ? Number(contract.valor_del_contrato)
        : null,
      fecha_firma: ((contract?.fecha_de_firma as string) ?? "").slice(0, 10) ||
        null,
      estado: (contract?.estado_contrato as string) ?? null,
      modalidad: (contract?.modalidad_de_contratacion as string) ?? null,
      notas: (contract?._notas as string) ?? null,
      dias_adicionados: Number.isFinite(dias) && dias > 0 ? dias : null,
      liquidado: liq,
      sheets: w.sheets ?? [],
      vigencias: w.vigencias ?? [],
      appearances_count: w.appearances?.length ?? 0,
      watched: true,
      watch_url: w.url,
      verifyStatus: classifyStatus(w, contract),
    });
  }

  // Add orphan contracts (in SECOP, not in watch list)
  for (const c of contracts) {
    if (!c.id_contrato || usedContracts.has(c.id_contrato)) continue;
    const dias = parseInt(String(c.dias_adicionados ?? "0"), 10);
    const liq =
      String(c.liquidaci_n ?? "")
        .trim()
        .toLowerCase() === "si";
    rows.push({
      key: c.id_contrato,
      process_id: c.id_contrato,
      id_contrato: c.id_contrato,
      notice_uid: (c.proceso_de_compra as string) ?? null,
      url: (c.urlproceso as string) ?? null,
      objeto: (c.objeto_del_contrato as string) ?? null,
      proveedor: (c.proveedor_adjudicado as string) ?? null,
      valor: c.valor_del_contrato ? Number(c.valor_del_contrato) : null,
      fecha_firma: ((c.fecha_de_firma as string) ?? "").slice(0, 10) || null,
      estado: (c.estado_contrato as string) ?? null,
      modalidad: (c.modalidad_de_contratacion as string) ?? null,
      notas: (c._notas as string) ?? null,
      dias_adicionados: Number.isFinite(dias) && dias > 0 ? dias : null,
      liquidado: liq,
      sheets: [],
      vigencias: [],
      appearances_count: 0,
      watched: false,
      watch_url: null,
      verifyStatus: "contrato_firmado",
    });
  }

  return rows;
}


function StatusBadge({ status }: { status: UnifiedRow["verifyStatus"] }) {
  const config: Record<
    UnifiedRow["verifyStatus"],
    { label: string; cls: string; title: string }
  > = {
    contrato_firmado: {
      label: "Contrato firmado",
      cls: "bg-emerald-50 text-emerald-700 border-emerald-200",
      title: "Contrato existe en el dataset jbjy-vk9h de datos.gov.co",
    },
    verificado: {
      label: "Proceso verificado",
      cls: "bg-sky-50 text-sky-700 border-sky-200",
      title: "Proceso publicado con notice_uid resuelto en datos.gov.co",
    },
    borrador: {
      label: "Borrador SECOP",
      cls: "bg-amber-50 text-amber-700 border-amber-200",
      title:
        "CO1.REQ.* / CO1.BDOS.* — proceso en preparación, sin notice_uid público todavía",
    },
    no_en_api: {
      label: "No en API público",
      cls: "bg-rose-50 text-rose-700 border-rose-200",
      title:
        "El process_id no aparece en datos.gov.co. Validá manualmente abriendo el link al portal.",
    },
  };
  const c = config[status];
  return (
    <span
      className={cn(
        "inline-flex items-center px-2 py-0.5 rounded text-[10px] border whitespace-nowrap",
        c.cls,
      )}
      title={c.title}
    >
      {c.label}
    </span>
  );
}


export function UnifiedTable({
  rows,
  onPick,
  onAdd,
  onUpdate,
  onRemove,
  busy,
  totalAppearances,
}: {
  rows: UnifiedRow[];
  onPick: (id: string) => void;
  onAdd: (url: string) => Promise<void>;
  onUpdate: (oldUrl: string, newUrl: string) => Promise<void>;
  onRemove: (url: string) => Promise<void>;
  busy: boolean;
  totalAppearances: number;
}) {
  const [addUrl, setAddUrl] = React.useState("");
  const [editingKey, setEditingKey] = React.useState<string | null>(null);
  const [editDraft, setEditDraft] = React.useState("");

  return (
    <div className="border border-rule rounded-lg bg-surface overflow-hidden">
      <div className="px-5 py-4 border-b border-rule">
        <div className="flex items-center justify-between mb-3">
          <div>
            <div className="eyebrow">Procesos / Contratos</div>
            <p className="text-xs text-ink-soft mt-1">
              {rows.length} procesos en lista · {totalAppearances} apariciones
              en el Excel · contratos firmados confirmados contra SECOP
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          <Input
            value={addUrl}
            onChange={(e) => setAddUrl(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && addUrl.trim()) {
                e.preventDefault();
                onAdd(addUrl.trim()).then(() => setAddUrl(""));
              }
            }}
            placeholder="Pega URL del SECOP II para agregar otro proceso a tu lista…"
            className="flex-1"
            disabled={busy}
          />
          <Button
            onClick={() => addUrl.trim() && onAdd(addUrl.trim()).then(() => setAddUrl(""))}
            disabled={busy || !addUrl.trim()}
            className="gap-2"
          >
            <Plus className="h-4 w-4" />
            Agregar
          </Button>
        </div>
      </div>

      {rows.length === 0 ? (
        <div className="px-5 py-12 text-center text-xs text-ink-soft italic">
          No hay procesos que coincidan con los filtros.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-background text-[11px] uppercase tracking-wider text-ink-soft">
              <tr>
                <th className="text-left px-3 py-2 w-20">Vigencia</th>
                <th className="text-left px-3 py-2 w-44">Código</th>
                <th className="text-left px-3 py-2">Objeto</th>
                <th className="text-left px-3 py-2 w-44">Proveedor</th>
                <th className="text-right px-3 py-2 w-32">Valor (COP)</th>
                <th className="text-left px-3 py-2 w-24">Firma</th>
                <th className="text-left px-3 py-2 w-28">Estado</th>
                <th className="text-left px-3 py-2 w-28">Verificación</th>
                <th className="text-left px-3 py-2 w-28">Hoja</th>
                <th className="text-right px-3 py-2 w-32"></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const isEditing = editingKey === r.key;
                const vigencia = r.vigencias.join(", ") ||
                  (r.fecha_firma ? r.fecha_firma.slice(0, 4) : null);
                return (
                  <tr
                    key={r.key}
                    className="border-t border-rule/60 hover:bg-background"
                  >
                    <td className="px-3 py-2 font-mono text-xs">
                      {vigencia ? (
                        <span className="inline-flex items-center px-1.5 py-0.5 rounded bg-burgundy/10 text-burgundy">
                          {vigencia}
                        </span>
                      ) : (
                        <span className="text-ink-soft/50">—</span>
                      )}
                    </td>
                    <td className="px-3 py-2 font-mono text-[11px]">
                      <button
                        onClick={() =>
                          onPick(r.id_contrato ?? r.process_id ?? r.key)
                        }
                        className="text-burgundy hover:underline text-left"
                      >
                        {r.id_contrato ?? r.process_id ?? "—"}
                      </button>
                      {r.appearances_count > 1 && (
                        <span className="block text-[10px] text-ink-soft italic mt-0.5">
                          {r.appearances_count} apariciones
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-xs text-ink">
                      {r.objeto
                        ? r.objeto.slice(0, 80) + (r.objeto.length > 80 ? "…" : "")
                        : (
                          <span className="text-ink-soft italic">
                            (sin contrato firmado)
                          </span>
                        )}
                    </td>
                    <td className="px-3 py-2 text-xs">
                      {r.proveedor ?? <span className="text-ink-soft/50">—</span>}
                    </td>
                    <td className="px-3 py-2 font-mono text-xs text-right">
                      {r.valor != null ? moneyCO.format(r.valor) : (
                        <span className="text-ink-soft/50">—</span>
                      )}
                    </td>
                    <td className="px-3 py-2 font-mono text-[11px] text-ink-soft">
                      {r.fecha_firma ?? "—"}
                    </td>
                    <td className="px-3 py-2 text-xs">
                      {r.estado ? (
                        <span className="inline-flex items-center px-1.5 py-0.5 rounded bg-stone-100 text-ink whitespace-nowrap">
                          {r.estado}
                        </span>
                      ) : (
                        <span className="text-ink-soft/50">—</span>
                      )}
                      {r.notas && (
                        <div className="text-[10px] text-ink-soft mt-0.5 italic">
                          {r.notas}
                        </div>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      <StatusBadge status={r.verifyStatus} />
                    </td>
                    <td className="px-3 py-2 text-[11px] text-ink-soft">
                      {r.sheets.length > 0 ? (
                        r.sheets.join(", ")
                      ) : (
                        <span className="italic">solo SECOP</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-right">
                      {isEditing ? (
                        <div className="flex items-center justify-end gap-1">
                          <Input
                            autoFocus
                            value={editDraft}
                            onChange={(e) => setEditDraft(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === "Escape") setEditingKey(null);
                              if (e.key === "Enter" && editDraft.trim() && r.watch_url) {
                                onUpdate(r.watch_url, editDraft.trim()).then(() =>
                                  setEditingKey(null),
                                );
                              }
                            }}
                            className="h-7 text-[11px] w-56"
                            placeholder="Nueva URL SECOP…"
                          />
                          <button
                            onClick={() => {
                              if (editDraft.trim() && r.watch_url) {
                                onUpdate(r.watch_url, editDraft.trim()).then(() =>
                                  setEditingKey(null),
                                );
                              }
                            }}
                            disabled={busy || !editDraft.trim()}
                            className="inline-flex items-center justify-center h-7 w-7 rounded text-emerald-700 hover:bg-emerald-50 disabled:opacity-50"
                            title="Guardar"
                          >
                            <Check className="h-4 w-4" />
                          </button>
                          <button
                            onClick={() => setEditingKey(null)}
                            className="inline-flex items-center justify-center h-7 w-7 rounded text-ink-soft hover:bg-stone-100"
                            title="Cancelar"
                          >
                            <XIcon className="h-4 w-4" />
                          </button>
                        </div>
                      ) : (
                        <div className="flex items-center justify-end gap-0.5">
                          {r.url && (
                            <a
                              href={r.url}
                              target="_blank"
                              rel="noreferrer"
                              className="inline-flex items-center justify-center h-7 w-7 rounded text-burgundy hover:bg-burgundy/10"
                              title="Abrir en SECOP II"
                            >
                              <ExternalLink className="h-4 w-4" />
                            </a>
                          )}
                          {r.watched && r.watch_url && (
                            <>
                              <button
                                onClick={() => {
                                  setEditingKey(r.key);
                                  setEditDraft(r.watch_url ?? "");
                                }}
                                disabled={busy}
                                className="inline-flex items-center justify-center h-7 w-7 rounded text-burgundy hover:bg-burgundy/10 disabled:opacity-50"
                                title="Corregir URL del proceso"
                              >
                                <Pencil className="h-4 w-4" />
                              </button>
                              <button
                                onClick={() =>
                                  r.watch_url && onRemove(r.watch_url)
                                }
                                disabled={busy}
                                className="inline-flex items-center justify-center h-7 w-7 rounded text-rose-700 hover:bg-rose-50 disabled:opacity-50"
                                title="Quitar de tu lista de seguimiento"
                              >
                                <Trash2 className="h-4 w-4" />
                              </button>
                            </>
                          )}
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
