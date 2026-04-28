"use client";

import * as React from "react";
import useSWR from "swr";
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
import { api, type WatchedItem, type WatchedAppearance } from "@/lib/api";
import { cn, fmtDate } from "@/lib/utils";

/**
 * "Mis procesos seguidos" — manual watch list.
 *
 * The Dra. paste a SECOP URL → it gets parsed, deduped, persisted on
 * the server (`.cache/watched_urls.json`) and shown in the list.
 * Click X to remove. The watched list is independent from the live
 * FEAB inventory (which auto-discovers all 287 contracts by NIT).
 */
export function WatchListPanel({
  onPickProcessId,
}: {
  onPickProcessId: (id: string) => void;
}) {
  const { data, isLoading, mutate } = useSWR<{ items: WatchedItem[] }>(
    "watch",
    api.watchList,
    { refreshInterval: 0 }
  );

  const [url, setUrl] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [feedback, setFeedback] = React.useState<{
    kind: "ok" | "info" | "error";
    text: string;
  } | null>(null);

  async function handleAdd() {
    const trimmed = url.trim();
    if (!trimmed) return;
    setBusy(true);
    setFeedback(null);
    try {
      const res = await api.watchAdd(trimmed);
      if (res.added) {
        setFeedback({
          kind: "ok",
          text: `Agregado · ${res.item.process_id ?? "URL aceptada"}`,
        });
      } else {
        setFeedback({
          kind: "info",
          text: res.reason ?? "Esa URL ya estaba en tu lista.",
        });
      }
      setUrl("");
      mutate();
    } catch (err) {
      setFeedback({
        kind: "error",
        text: err instanceof Error ? err.message : "No pude agregar la URL.",
      });
    } finally {
      setBusy(false);
    }
  }

  async function handleRemove(item: WatchedItem) {
    setBusy(true);
    try {
      await api.watchRemove(item.url);
      mutate();
      setFeedback({ kind: "ok", text: "URL retirada de tu lista." });
    } catch (err) {
      setFeedback({
        kind: "error",
        text: err instanceof Error ? err.message : "No pude eliminar.",
      });
    } finally {
      setBusy(false);
    }
  }

  async function handleUpdate(oldUrl: string, newUrl: string) {
    setBusy(true);
    setFeedback(null);
    try {
      const res = await api.watchUpdate(oldUrl, { newUrl });
      setFeedback({
        kind: "ok",
        text: `Link actualizado · ${res.item.process_id ?? "URL aceptada"}`,
      });
      mutate();
    } catch (err) {
      setFeedback({
        kind: "error",
        text:
          err instanceof Error ? err.message : "No pude actualizar el link.",
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="border border-rule rounded-lg bg-surface overflow-hidden">
      <div className="px-5 py-4 border-b border-rule">
        <div className="eyebrow mb-2">Mis procesos seguidos</div>
        <p className="text-xs text-ink-soft mb-3">
          Pega una URL del SECOP II para agregar el proceso a tu lista. El
          programa la guarda y verifica que no esté duplicada. La verdad de
          los datos siempre viene del SECOP en vivo.
        </p>
        <div className="flex gap-2">
          <Input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                handleAdd();
              }
            }}
            placeholder="https://community.secop.gov.co/Public/Tendering/..."
            className="flex-1"
            disabled={busy}
          />
          <Button
            onClick={handleAdd}
            disabled={busy || !url.trim()}
            className="gap-2"
          >
            <Plus className="h-4 w-4" />
            Agregar
          </Button>
        </div>
        {feedback && (
          <div
            className={cn(
              "mt-2 text-xs px-3 py-1.5 rounded border",
              feedback.kind === "ok" &&
                "bg-emerald-50 text-emerald-700 border-emerald-200",
              feedback.kind === "info" &&
                "bg-amber-50 text-amber-800 border-amber-200",
              feedback.kind === "error" &&
                "bg-rose-50 text-rose-700 border-rose-200"
            )}
          >
            {feedback.text}
          </div>
        )}
      </div>

      <div>
        {isLoading ? (
          <div className="px-5 py-6 text-xs text-ink-soft italic">
            Cargando lista…
          </div>
        ) : !data?.items.length ? (
          <div className="px-5 py-6 text-xs text-ink-soft italic">
            Tu lista está vacía. Pega una URL del SECOP arriba para empezar.
          </div>
        ) : (
          <FilteredWatchTable
            items={data.items}
            onPickProcessId={onPickProcessId}
            handleRemove={handleRemove}
            handleUpdate={handleUpdate}
            busy={busy}
          />
        )}
      </div>
    </div>
  );
}


/**
 * Watch list table with sheet filter pills above. Filter by sheet
 * (FEAB 2026, FEAB 2025, …): the count next to each pill is the
 * number of processes that appeared in that sheet of the Excel —
 * matching the Dra's view exactly. A process that appears on 3
 * sheets is one row in the watch list but contributes to all 3
 * sheet counts (no data eaten, no duplicates invented).
 */
function FilteredWatchTable({
  items,
  onPickProcessId,
  handleRemove,
  handleUpdate,
  busy,
}: {
  items: WatchedItem[];
  onPickProcessId: (id: string) => void;
  handleRemove: (it: WatchedItem) => void;
  handleUpdate: (oldUrl: string, newUrl: string) => Promise<void>;
  busy: boolean;
}) {
  const [sheetFilter, setSheetFilter] = React.useState<string | null>(null);
  const [editingUrl, setEditingUrl] = React.useState<string | null>(null);
  const [editDraft, setEditDraft] = React.useState("");

  // Count APPEARANCES per sheet (matches Excel row counts exactly).
  // A process that's in 2 rows of FEAB 2024 contributes 2 to "FEAB 2024",
  // mirroring what the Dra sees if she opens that sheet.
  const sheetCounts = React.useMemo(() => {
    const counts = new Map<string, number>();
    for (const it of items) {
      const apps = it.appearances ?? [];
      if (apps.length === 0) {
        const sheets = it.sheets?.length ? it.sheets : ["(sin hoja)"];
        for (const s of sheets) counts.set(s, (counts.get(s) ?? 0) + 1);
      } else {
        for (const a of apps) {
          counts.set(a.sheet, (counts.get(a.sheet) ?? 0) + 1);
        }
      }
    }
    return Array.from(counts.entries()).sort((a, b) => {
      if (a[0] === "(sin hoja)") return 1;
      if (b[0] === "(sin hoja)") return -1;
      return b[0].localeCompare(a[0]);
    });
  }, [items]);

  // Total apariciones (sum of all sheet counts).
  const totalAppearances = React.useMemo(
    () => sheetCounts.reduce((sum, [, c]) => sum + c, 0),
    [sheetCounts]
  );

  // Filtered rows: when no filter, show one row per UNIQUE item (491).
  // When filtering by a sheet, expand to one row per APPEARANCE in that
  // sheet — this is the "espejo del Excel" mode the Dra wants.
  type Row = { item: WatchedItem; appearance: WatchedAppearance | null };
  const filtered: Row[] = React.useMemo(() => {
    if (!sheetFilter) {
      return items.map((it) => ({ item: it, appearance: null }));
    }
    const out: Row[] = [];
    for (const it of items) {
      const apps = it.appearances ?? [];
      if (apps.length === 0) {
        const sheets = it.sheets?.length ? it.sheets : ["(sin hoja)"];
        if (sheets.includes(sheetFilter)) {
          out.push({ item: it, appearance: null });
        }
      } else {
        for (const a of apps) {
          if (a.sheet === sheetFilter) {
            out.push({ item: it, appearance: a });
          }
        }
      }
    }
    return out;
  }, [items, sheetFilter]);

  return (
    <>
      <div className="px-5 py-3 border-b border-rule/60 flex items-center gap-2 flex-wrap">
        <span className="text-[11px] uppercase tracking-wider text-ink-soft mr-1">
          Hoja Excel:
        </span>
        <button
          onClick={() => setSheetFilter(null)}
          className={cn(
            "text-xs px-2.5 py-1 rounded-full border transition-colors",
            sheetFilter === null
              ? "bg-burgundy text-white border-burgundy"
              : "bg-background border-rule hover:border-burgundy/50"
          )}
          title={`${items.length} procesos únicos · ${totalAppearances} apariciones en el Excel`}
        >
          Todas{" "}
          <span className="text-[10px] opacity-70">
            ({items.length} únicos)
          </span>
        </button>
        {sheetCounts.map(([sheet, count]) => (
          <button
            key={sheet}
            onClick={() => setSheetFilter(sheet)}
            className={cn(
              "text-xs px-2.5 py-1 rounded-full border transition-colors",
              sheetFilter === sheet
                ? "bg-burgundy text-white border-burgundy"
                : "bg-background border-rule hover:border-burgundy/50"
            )}
            title={`${count} proceso${count === 1 ? "" : "s"} en la hoja ${sheet}`}
          >
            {sheet} <span className="text-[10px] opacity-70">({count})</span>
          </button>
        ))}
      </div>

      <table className="w-full text-sm">
        <thead className="bg-background text-[11px] uppercase tracking-wider text-ink-soft">
          <tr>
            <th className="text-left px-4 py-2 w-24">Vigencia</th>
            <th className="text-left px-4 py-2">Proceso</th>
            <th className="text-left px-4 py-2 w-32">Estado API</th>
            <th className="text-left px-4 py-2">Notice UID</th>
            <th className="text-left px-4 py-2 w-32">Hojas</th>
            <th className="text-left px-4 py-2 w-20">SECOP</th>
            <th className="text-right px-4 py-2 w-16"></th>
          </tr>
        </thead>
        <tbody>
          {filtered.map(({ item: it, appearance: a }) => {
            // When viewing a sheet, show the per-row vigencia/url/row
            // from THAT appearance. When viewing all, show the
            // aggregate (vigencias.join + sheets.join).
            const vigencia = a ? a.vigencia : it.vigencias?.join(", ");
            const sheetsLabel = a ? a.sheet : it.sheets?.join(", ");
            const url = a ? a.url : it.url;
            const key = a ? `${it.url}#${a.sheet}#${a.row}` : it.url;

            // Derive verify status from the persisted schema.
            // The Dra needs to know at a glance which processes the
            // public datos.gov.co API can confirm and which require
            // manual review (e.g. portal scrape, archived NTCs).
            const isDraft =
              !!it.process_id &&
              (it.process_id.startsWith("CO1.REQ.") ||
                it.process_id.startsWith("CO1.BDOS."));
            let statusLabel: string;
            let statusClass: string;
            let statusTitle: string;
            if (it.notice_uid) {
              statusLabel = "Verificado";
              statusClass =
                "bg-emerald-50 text-emerald-700 border-emerald-200";
              statusTitle = `notice_uid resuelto contra datos.gov.co (${it.notice_uid})`;
            } else if (isDraft) {
              statusLabel = "Borrador SECOP";
              statusClass = "bg-sky-50 text-sky-700 border-sky-200";
              statusTitle =
                "Proceso en preparación / borrador interno (CO1.REQ.* o CO1.BDOS.*). Aún no tiene notice_uid publicado.";
            } else {
              statusLabel = "No en API público";
              statusClass = "bg-amber-50 text-amber-800 border-amber-200";
              statusTitle =
                "El process_id no aparece en datos.gov.co (proceso archivado o publicado solo en el portal web). Validá manualmente abriendo el link.";
            }

            return (
              <tr
                key={key}
                className="border-t border-rule/60 hover:bg-background"
              >
                <td className="px-4 py-2 font-mono text-xs">
                  {vigencia ? (
                    <span className="inline-flex items-center px-1.5 py-0.5 rounded bg-burgundy/10 text-burgundy">
                      {vigencia}
                    </span>
                  ) : (
                    <span className="text-ink-soft/50">—</span>
                  )}
                </td>
                <td className="px-4 py-2 font-mono text-xs">
                  {it.process_id ? (
                    <button
                      onClick={() => onPickProcessId(it.process_id!)}
                      className="text-burgundy hover:underline"
                    >
                      {it.process_id}
                    </button>
                  ) : (
                    <span className="text-ink-soft">URL personalizada</span>
                  )}
                  {a && (
                    <span className="block text-[10px] text-ink-soft mt-0.5 italic">
                      fila {a.row} de {a.sheet}
                    </span>
                  )}
                </td>
                <td className="px-4 py-2">
                  <span
                    className={cn(
                      "inline-flex items-center px-2 py-0.5 rounded text-[11px] border",
                      statusClass
                    )}
                    title={statusTitle}
                  >
                    {statusLabel}
                  </span>
                </td>
                <td className="px-4 py-2 font-mono text-xs text-ink-soft">
                  {it.notice_uid ?? "—"}
                </td>
                <td className="px-4 py-2 text-[11px] text-ink-soft">
                  {sheetsLabel ?? "—"}
                  {!a &&
                    it.appearances &&
                    it.appearances.length > 1 && (
                      <span className="block text-[10px] italic mt-0.5">
                        {it.appearances.length} apariciones
                      </span>
                    )}
                </td>
                <td className="px-4 py-2">
                  <a
                    href={url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 text-xs text-burgundy hover:underline"
                  >
                    Abrir <ExternalLink className="h-3 w-3" />
                  </a>
                </td>
                <td className="px-4 py-2 text-right">
                  {!a && editingUrl === it.url ? (
                    <div className="flex items-center justify-end gap-1">
                      <Input
                        autoFocus
                        value={editDraft}
                        onChange={(e) => setEditDraft(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Escape") setEditingUrl(null);
                          if (e.key === "Enter" && editDraft.trim()) {
                            handleUpdate(it.url, editDraft.trim()).then(() =>
                              setEditingUrl(null)
                            );
                          }
                        }}
                        className="h-7 text-[11px] w-64"
                        placeholder="Nueva URL SECOP…"
                      />
                      <button
                        onClick={() => {
                          if (editDraft.trim()) {
                            handleUpdate(it.url, editDraft.trim()).then(() =>
                              setEditingUrl(null)
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
                        onClick={() => setEditingUrl(null)}
                        className="inline-flex items-center justify-center h-7 w-7 rounded text-ink-soft hover:bg-stone-100"
                        title="Cancelar"
                      >
                        <XIcon className="h-4 w-4" />
                      </button>
                    </div>
                  ) : !a ? (
                    <div className="flex items-center justify-end gap-0.5">
                      <button
                        onClick={() => {
                          setEditingUrl(it.url);
                          setEditDraft(it.url);
                        }}
                        disabled={busy}
                        className="inline-flex items-center justify-center h-7 w-7 rounded text-burgundy hover:bg-burgundy/10 disabled:opacity-50"
                        title="Corregir URL del proceso"
                      >
                        <Pencil className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => handleRemove(it)}
                        disabled={busy}
                        className="inline-flex items-center justify-center h-7 w-7 rounded text-rose-700 hover:bg-rose-50 disabled:opacity-50"
                        title="Quitar de la lista"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  ) : null}
                </td>
              </tr>
            );
          })}
          {filtered.length === 0 && (
            <tr>
              <td
                colSpan={7}
                className="px-4 py-6 text-center text-xs text-ink-soft italic"
              >
                No hay procesos en esta hoja.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </>
  );
}
