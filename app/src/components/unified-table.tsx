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
  type WatchedAppearance,
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
  appearances: WatchedAppearance[];
  appearances_count: number;
  watched: boolean;
  watch_url: string | null;

  // Verify status taxonomy (derived)
  verifyStatus: "verificado" | "contrato_firmado" | "borrador" | "no_en_api";
}


/**
 * When a sheet filter is active, expand each watched row to ONE ROW
 * per appearance in the matching sheet(s). This makes the count
 * match the Excel exactly — if FEAB 2024 has 85 rows pointing at
 * SECOP URLs, the table shows 85 lines, not the 66 dedup-by-process.
 */
export function expandRowsByAppearance(
  rows: UnifiedRow[],
  selectedSheets: string[],
): UnifiedRow[] {
  if (selectedSheets.length === 0) return rows;
  const out: UnifiedRow[] = [];
  for (const r of rows) {
    if (!r.watched || r.appearances.length === 0) {
      // Orphan or empty: keep as one line if any of its sheets matches
      const hit = r.sheets.some((s) => selectedSheets.includes(s));
      if (hit || r.sheets.length === 0) out.push(r);
      continue;
    }
    const matching = r.appearances.filter((a) =>
      selectedSheets.includes(a.sheet),
    );
    for (const a of matching) {
      out.push({
        ...r,
        key: `${r.key}#${a.sheet}#${a.row ?? "manual"}`,
        // Override sheet/vigencia to the appearance's specific values
        sheets: [a.sheet],
        vigencias: a.vigencia ? [a.vigencia] : r.vigencias,
      });
    }
  }
  return out;
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
 *
 * Three-tier fallback for each cell:
 *   1. SECOP API contract  (most authoritative)
 *   2. Excel data           (Dra's master file — used when API has no contract)
 *   3. null                 (the row is from a brand-new manual add)
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

    const ex = w.excel_data ?? null;
    const apiDias = parseInt(String(contract?.dias_adicionados ?? "0"), 10);
    const exDias = parseInt(String(ex?.dias_prorrogas ?? "0"), 10);
    const dias =
      Number.isFinite(apiDias) && apiDias > 0
        ? apiDias
        : Number.isFinite(exDias) && exDias > 0
          ? exDias
          : null;
    const apiLiq =
      String(contract?.liquidaci_n ?? "")
        .trim()
        .toLowerCase() === "si";
    const exLiq =
      String(ex?.liquidacion ?? "")
        .trim()
        .toLowerCase()
        .startsWith("s");
    const liq = apiLiq || exLiq;

    // Compose human-readable "Notas" line. Prefer API-computed; else
    // build from Excel signals.
    let notas: string | null = (contract?._notas as string) ?? null;
    if (!notas) {
      const parts: string[] = [];
      const estado =
        (contract?.estado_contrato as string) ?? ex?.estado ?? "";
      if (/modific/i.test(estado)) parts.push("Modificado");
      if (dias && dias > 0) parts.push(`+${dias} días`);
      if (liq) parts.push("Liquidado");
      notas = parts.length ? parts.join(" · ") : null;
    }

    const valorRaw = contract?.valor_del_contrato ?? ex?.valor_total ??
      ex?.valor_inicial;
    const valor = valorRaw != null && valorRaw !== ""
      ? Number(valorRaw)
      : null;

    rows.push({
      key: contract?.id_contrato ?? w.url ?? `${w.process_id ?? "noid"}-${rows.length}`,
      process_id: w.process_id,
      id_contrato: contract?.id_contrato ?? null,
      notice_uid: w.notice_uid ?? contract?.proceso_de_compra ?? null,
      url: w.url,
      objeto:
        (contract?.objeto_del_contrato as string) ?? ex?.objeto ?? null,
      proveedor:
        (contract?.proveedor_adjudicado as string) ?? ex?.proveedor ?? null,
      valor: valor != null && Number.isFinite(valor) ? valor : null,
      fecha_firma:
        ((contract?.fecha_de_firma as string) ?? "").slice(0, 10) ||
        (ex?.fecha_firma ?? null) ||
        null,
      estado:
        (contract?.estado_contrato as string) ?? ex?.estado ?? null,
      modalidad:
        (contract?.modalidad_de_contratacion as string) ??
        ex?.modalidad ??
        null,
      notas,
      dias_adicionados: dias,
      liquidado: liq,
      sheets: w.sheets ?? [],
      vigencias: w.vigencias ?? [],
      appearances: w.appearances ?? [],
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
      appearances: [],
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
                <th className="text-left px-3 py-2 w-40">Notice UID</th>
                <th className="text-left px-3 py-2">Objeto</th>
                <th className="text-left px-3 py-2 w-44">Proveedor</th>
                <th className="text-right px-3 py-2 w-32">Valor (COP)</th>
                <th className="text-left px-3 py-2 w-24">Firma</th>
                <th className="text-left px-3 py-2 w-28">Estado</th>
                <th className="text-left px-3 py-2 w-40">Notas</th>
                <th className="text-left px-3 py-2 w-28">Verificación</th>
                <th className="text-left px-3 py-2 w-28">Hoja</th>
                <th className="text-right px-3 py-2 w-44">Acciones</th>
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
                    <td className="px-3 py-2 font-mono text-[10px] text-ink-soft">
                      {r.notice_uid ?? "—"}
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
                    </td>
                    <td className="px-3 py-2 text-[11px] text-ink-soft italic">
                      {r.notas ?? <span className="not-italic">—</span>}
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
                        <div className="flex items-center justify-end gap-1">
                          {r.url && (
                            <a
                              href={r.url}
                              target="_blank"
                              rel="noreferrer"
                              className="inline-flex items-center gap-1 px-2 h-7 rounded text-[11px] text-burgundy hover:bg-burgundy/10 border border-transparent hover:border-burgundy/30"
                              title="Abrir el link del proceso en el portal SECOP II"
                            >
                              <ExternalLink className="h-3.5 w-3.5" />
                              Abrir
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
                                className="inline-flex items-center gap-1 px-2 h-7 rounded text-[11px] text-burgundy hover:bg-burgundy/10 border border-transparent hover:border-burgundy/30 disabled:opacity-50"
                                title="Corregir el link del proceso si está mal"
                              >
                                <Pencil className="h-3.5 w-3.5" />
                                Editar
                              </button>
                              <button
                                onClick={() =>
                                  r.watch_url && onRemove(r.watch_url)
                                }
                                disabled={busy}
                                className="inline-flex items-center gap-1 px-2 h-7 rounded text-[11px] text-rose-700 hover:bg-rose-50 border border-transparent hover:border-rose-300 disabled:opacity-50"
                                title="Quitar este proceso de tu lista"
                              >
                                <Trash2 className="h-3.5 w-3.5" />
                                Quitar
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
