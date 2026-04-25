"use client";

import * as React from "react";
import useSWR from "swr";
import { ExternalLink, FileSpreadsheet, Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, type WatchedItem } from "@/lib/api";
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
  const [importing, setImporting] = React.useState(false);
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

  async function handleImportFromExcel() {
    setImporting(true);
    setFeedback({
      kind: "info",
      text: "Leyendo el Excel y deduplicando contra tu lista…",
    });
    try {
      const res = await api.watchImportFromExcel();
      const sheetSummary = Object.entries(res.per_sheet)
        .map(([name, s]) => `${name}: +${s.added}`)
        .join(" · ");
      if (res.added > 0) {
        setFeedback({
          kind: "ok",
          text: `Importadas ${res.added} URLs nuevas · ${res.skipped_dupe} duplicadas · ${sheetSummary}`,
        });
      } else if (res.skipped_dupe > 0) {
        setFeedback({
          kind: "info",
          text: `Nada nuevo. ${res.skipped_dupe} URLs ya estaban en tu lista (${sheetSummary}).`,
        });
      } else {
        setFeedback({
          kind: "info",
          text: "No encontré URLs SECOP en el Excel.",
        });
      }
      mutate();
    } catch (err) {
      setFeedback({
        kind: "error",
        text: err instanceof Error ? err.message : "No pude importar.",
      });
    } finally {
      setImporting(false);
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
            disabled={busy || importing}
          />
          <Button
            onClick={handleAdd}
            disabled={busy || importing || !url.trim()}
            className="gap-2"
          >
            <Plus className="h-4 w-4" />
            Agregar
          </Button>
          <Button
            onClick={handleImportFromExcel}
            disabled={busy || importing}
            variant="outline"
            className="gap-2"
            title="Lee la columna LINK de cada hoja del Excel y agrega los procesos no duplicados"
          >
            <FileSpreadsheet className="h-4 w-4" />
            {importing ? "Importando…" : "Importar del Excel"}
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
          <table className="w-full text-sm">
            <thead className="bg-background text-[11px] uppercase tracking-wider text-ink-soft">
              <tr>
                <th className="text-left px-4 py-2">Proceso</th>
                <th className="text-left px-4 py-2">Notice UID</th>
                <th className="text-left px-4 py-2">Agregado</th>
                <th className="text-left px-4 py-2 w-20">SECOP</th>
                <th className="text-right px-4 py-2 w-16"></th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((it) => (
                <tr
                  key={it.url}
                  className="border-t border-rule/60 hover:bg-background"
                >
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
                    {it.note && (
                      <div className="text-[10px] text-ink-soft mt-0.5 italic">
                        {it.note}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-2 font-mono text-xs text-ink-soft">
                    {it.notice_uid ?? "—"}
                  </td>
                  <td className="px-4 py-2 font-mono text-xs text-ink-soft">
                    {fmtDate(it.added_at)}
                  </td>
                  <td className="px-4 py-2">
                    <a
                      href={it.url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 text-xs text-burgundy hover:underline"
                    >
                      Abrir <ExternalLink className="h-3 w-3" />
                    </a>
                  </td>
                  <td className="px-4 py-2 text-right">
                    <button
                      onClick={() => handleRemove(it)}
                      disabled={busy}
                      className="inline-flex items-center justify-center h-7 w-7 rounded text-rose-700 hover:bg-rose-50 disabled:opacity-50"
                      title="Quitar de la lista"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
