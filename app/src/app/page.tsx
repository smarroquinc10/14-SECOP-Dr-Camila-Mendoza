"use client";

import * as React from "react";
import useSWR from "swr";
import {
  CheckCircle2,
  Loader2,
  RefreshCcw,
  ShieldCheck,
  ShieldAlert,
} from "lucide-react";

import { DetailDialog } from "@/components/detail-dialog";
import { ModsPanel } from "@/components/mods-panel";
import { SlicerPills } from "@/components/slicer-pills";
import {
  buildUnifiedRows,
  expandRowsByAppearance,
  UnifiedTable,
  type UnifiedRow,
} from "@/components/unified-table";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  api,
  type Contract,
  type WatchedItem,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const TODAY = new Intl.DateTimeFormat("es-CO", {
  weekday: "long",
  day: "numeric",
  month: "long",
  year: "numeric",
}).format(new Date());

export default function HomePage() {
  // ---- Live data from FastAPI ------------------------------------------
  const { data: feab } = useSWR("feab", api.feab, { refreshInterval: 0 });
  const {
    data: contracts = [],
    isLoading: loadingContracts,
    mutate: reloadContracts,
  } = useSWR<Contract[]>("contracts:500", () => api.contracts(500));
  const {
    data: watch,
    isLoading: loadingWatch,
    mutate: reloadWatch,
  } = useSWR<{ items: WatchedItem[] }>("watch", api.watchList);
  const watched = watch?.items ?? [];
  const { data: audit } = useSWR("audit:50", () => api.auditLog(50), {
    refreshInterval: 60_000,
  });
  const { data: ultActualiz, mutate: reloadUltActualiz } = useSWR(
    "ultima-actualizacion",
    api.ultimaActualizacion,
    { refreshInterval: 30_000 }
  );

  // Verify progress: poll every 3s while a verify_watch_list.py run is
  // active, every 30s otherwise (in case the user kicks one off via CLI).
  const { data: verifyProgress, mutate: reloadVerifyProgress } = useSWR(
    "verify-progress",
    api.verifyProgress,
    { refreshInterval: 3_000 }
  );

  const isLoading = loadingContracts || loadingWatch;

  // ---- Filter state -----------------------------------------------------
  const [search, setSearch] = React.useState("");
  const [years, setYears] = React.useState<string[]>([]);
  const [states, setStates] = React.useState<string[]>([]);
  const [modalities, setModalities] = React.useState<string[]>([]);
  const [sheets, setSheets] = React.useState<string[]>([]);
  const [selected, setSelected] = React.useState<string | null>(null);
  // Cardinal rules (no toggle, always ON):
  //   - Always show only the Dra's tracked processes (Excel-imported).
  //   - "Modificados" gets filtered from the column header (Excel-style),
  //     no separate toggle needed.
  const onlyMine = true;
  const onlyMod = false;

  // ---- Build unified rows + busy/feedback state for actions -----------
  const allRows = React.useMemo(
    () => buildUnifiedRows(watched, contracts),
    [watched, contracts]
  );

  const totalAppearances = React.useMemo(
    () => watched.reduce((acc, w) => acc + (w.appearances?.length ?? 0), 0),
    [watched]
  );

  // ---- Distinct option sets for slicers --------------------------------
  const yearOptions = React.useMemo(
    () =>
      Array.from(
        new Set(
          allRows
            .flatMap((r) => [
              ...r.vigencias,
              r.fecha_firma ? r.fecha_firma.slice(0, 4) : "",
            ])
            .filter(Boolean)
        )
      ).sort((a, b) => b.localeCompare(a)),
    [allRows]
  );
  const stateOptions = React.useMemo(
    () =>
      Array.from(new Set(allRows.map((r) => r.estado ?? "").filter(Boolean))).sort(),
    [allRows]
  );
  const modalityOptions = React.useMemo(
    () =>
      Array.from(
        new Set(allRows.map((r) => r.modalidad ?? "").filter(Boolean))
      ).sort(),
    [allRows]
  );
  const sheetOptions = React.useMemo(() => {
    const counts = new Map<string, number>();
    for (const r of allRows) {
      for (const s of r.sheets) counts.set(s, (counts.get(s) ?? 0) + 1);
    }
    return Array.from(counts.keys()).sort((a, b) => b.localeCompare(a));
  }, [allRows]);

  // ---- Apply filters ----------------------------------------------------
  const filtered = React.useMemo(() => {
    const base = allRows.filter((r) => {
      if (onlyMine && !r.watched) return false;
      if (search) {
        const blob = (
          (r.id_contrato ?? "") +
          (r.process_id ?? "") +
          (r.objeto ?? "") +
          (r.proveedor ?? "")
        ).toLowerCase();
        if (!blob.includes(search.toLowerCase())) return false;
      }
      if (years.length) {
        const rowYears = new Set([
          ...r.vigencias,
          r.fecha_firma ? r.fecha_firma.slice(0, 4) : "",
        ]);
        if (!years.some((y) => rowYears.has(y))) return false;
      }
      if (states.length && !states.includes(r.estado ?? "")) return false;
      if (modalities.length && !modalities.includes(r.modalidad ?? ""))
        return false;
      if (sheets.length && !sheets.some((s) => r.sheets.includes(s)))
        return false;
      if (onlyMod) {
        const isMod =
          /modific/i.test(r.estado ?? "") ||
          (r.dias_adicionados != null && r.dias_adicionados > 0);
        if (!isMod) return false;
      }
      return true;
    });
    // When the user picks one or more sheet pills, expand every row
    // by its appearances in those sheets so the count matches the
    // Excel exactly (e.g. FEAB 2024 → 85 rows, not 66 dedup-by-process).
    return expandRowsByAppearance(base, sheets);
  }, [allRows, search, years, states, modalities, sheets, onlyMod, onlyMine]);

  // ---- Refresh + watch CRUD --------------------------------------------
  const [refreshing, setRefreshing] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [feedback, setFeedback] = React.useState<{
    kind: "ok" | "info" | "error";
    text: string;
  } | null>(null);
  const [lastRefresh, setLastRefresh] = React.useState<string | null>(null);

  async function handleRefresh() {
    // Trigger the watch-list verify (re-checks every URL against SECOP).
    // Returns immediately; the JSONL writer pushes progress that the
    // verify-progress polling picks up.
    setRefreshing(true);
    try {
      await api.verifyWatch();
      // Wait briefly for the spawned process to start writing the JSONL,
      // then refresh related data.
      await new Promise((r) => setTimeout(r, 1500));
      await Promise.all([reloadVerifyProgress(), reloadUltActualiz()]);
      setLastRefresh(new Date().toISOString());
    } catch (err) {
      console.error(err);
    } finally {
      setRefreshing(false);
    }
  }

  async function handleAdd(url: string) {
    setBusy(true);
    setFeedback(null);
    try {
      const res = await api.watchAdd(url);
      setFeedback(
        res.added
          ? { kind: "ok", text: `Agregado · ${res.item.process_id ?? "URL aceptada"}` }
          : { kind: "info", text: res.reason ?? "Esa URL ya estaba en tu lista." }
      );
      await reloadWatch();
    } catch (err) {
      setFeedback({
        kind: "error",
        text: err instanceof Error ? err.message : "No pude agregar la URL.",
      });
    } finally {
      setBusy(false);
    }
  }

  async function handleUpdate(oldUrl: string, newUrl: string) {
    setBusy(true);
    setFeedback(null);
    try {
      const res = await api.watchUpdate(oldUrl, newUrl);
      setFeedback({
        kind: "ok",
        text: `Link actualizado · ${res.item.process_id ?? "URL aceptada"}`,
      });
      await reloadWatch();
    } catch (err) {
      setFeedback({
        kind: "error",
        text: err instanceof Error ? err.message : "No pude actualizar.",
      });
    } finally {
      setBusy(false);
    }
  }

  async function handleRemove(url: string) {
    setBusy(true);
    setFeedback(null);
    try {
      await api.watchRemove(url);
      setFeedback({ kind: "ok", text: "URL retirada de tu lista." });
      await reloadWatch();
    } catch (err) {
      setFeedback({
        kind: "error",
        text: err instanceof Error ? err.message : "No pude eliminar.",
      });
    } finally {
      setBusy(false);
    }
  }

  function fmtTimestamp(iso: string | null | undefined): string {
    if (!iso) return "—";
    const d = new Date(iso);
    return new Intl.DateTimeFormat("es-CO", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(d);
  }

  const pageFiltersActive =
    !!search ||
    years.length > 0 ||
    states.length > 0 ||
    modalities.length > 0 ||
    sheets.length > 0 ||
    onlyMod;

  return (
    <main className="min-h-screen bg-background">
      <div className="h-1 bg-secondary" />

      {/* Header */}
      <div className="mx-auto max-w-7xl px-8 pt-12 pb-6">
        <div className="eyebrow mb-3">
          Auditoría · Gestión Contractual · SECOP
        </div>
        <h1 className="serif text-5xl font-bold tracking-tight text-ink mb-2">
          Bienvenida, Dra. María Camila Mendoza Zubiría
        </h1>
        <div className="eyebrow text-ink-soft">{TODAY}</div>
      </div>

      <div className="rule mx-auto max-w-7xl mb-8" />

      {/* Action bar + audit chip */}
      <div className="mx-auto max-w-7xl px-8 mb-8 flex flex-wrap items-center gap-4">
        <Button
          size="lg"
          variant="outline"
          onClick={handleRefresh}
          disabled={refreshing}
          className="gap-2"
        >
          {refreshing ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <RefreshCcw className="h-4 w-4" />
          )}
          {refreshing ? "Refrescando…" : "Refrescar desde SECOP"}
        </Button>

        {feab && (
          <div className="text-sm text-ink-soft">
            <span className="font-mono">{feab.contratos}</span> contratos ·{" "}
            <span className="font-mono">{feab.procesos}</span> procesos ·{" "}
            <span className="font-mono">{watched.length}</span> en seguimiento
          </div>
        )}

        {ultActualiz?.ultima_consulta && (
          <div className="flex flex-col text-[11px] text-ink-soft border-l border-rule pl-3">
            <span className="eyebrow">Última actividad</span>
            <span className="font-mono text-ink">
              {fmtTimestamp(ultActualiz.ultima_consulta)}
            </span>
            {ultActualiz.ultimo_replace && (
              <span className="text-[10px] mt-0.5">
                Refresh: {fmtTimestamp(ultActualiz.ultimo_replace)}
              </span>
            )}
          </div>
        )}

        <div className="flex-1" />

        {audit && (
          <a
            href="#audit"
            className={cn(
              "inline-flex items-center gap-2 px-3 py-1.5 rounded-md border text-xs",
              audit.intact
                ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                : "border-rose-200 bg-rose-50 text-rose-700"
            )}
            title={
              audit.intact
                ? "Hash-chain del audit log íntegro"
                : "ALERTA: chain rota — revisar problemas"
            }
          >
            {audit.intact ? (
              <ShieldCheck className="h-3.5 w-3.5" />
            ) : (
              <ShieldAlert className="h-3.5 w-3.5" />
            )}
            {audit.total} entradas · {audit.intact ? "íntegro" : "alerta"}
          </a>
        )}
      </div>

      {/* Verify progress bar — only visible while a refresh is in flight,
          OR for ~30s after a completed run so the Dra sees the result. */}
      {verifyProgress && (verifyProgress.running ||
        (verifyProgress.processed > 0 &&
          (verifyProgress.last_update_age_seconds ?? 999) < 30)) && (
        <div className="mx-auto max-w-7xl px-8 mb-6">
          <div
            className={cn(
              "border rounded-lg p-4",
              verifyProgress.running
                ? "border-burgundy/30 bg-burgundy/5"
                : "border-emerald-300 bg-emerald-50"
            )}
          >
            <div className="flex items-center justify-between text-xs mb-2">
              <span className="font-medium text-ink">
                {verifyProgress.running
                  ? "Refrescando contra SECOP…"
                  : "Refresco completado"}
              </span>
              <span className="font-mono text-ink-soft">
                {verifyProgress.processed} / {verifyProgress.total} ·{" "}
                {verifyProgress.percent}%
                {verifyProgress.eta_seconds != null &&
                  verifyProgress.running && (
                    <>
                      {" · "}
                      ETA{" "}
                      {verifyProgress.eta_seconds < 60
                        ? `${Math.round(verifyProgress.eta_seconds)}s`
                        : `${Math.round(verifyProgress.eta_seconds / 60)}m`}
                    </>
                  )}
              </span>
            </div>
            <div className="h-2 bg-stone-100 rounded-full overflow-hidden">
              <div
                className={cn(
                  "h-full transition-all duration-300 rounded-full",
                  verifyProgress.running ? "bg-burgundy" : "bg-emerald-500"
                )}
                style={{ width: `${verifyProgress.percent}%` }}
              />
            </div>
            {!verifyProgress.running && verifyProgress.processed > 0 && (
              <div className="text-[11px] text-ink-soft mt-2 italic">
                Cada link se consultó en datos.gov.co. Los notice_uid
                se actualizaron en tu lista.
              </div>
            )}
          </div>
        </div>
      )}

      {/* Modificatorios summary panel — context first */}
      <div className="mx-auto max-w-7xl px-8 mb-6">
        <ModsPanel onPickContract={(id) => setSelected(id)} />
      </div>

      {/* FILTROS arriba — antes de la tabla unificada */}
      <div className="mx-auto max-w-7xl px-8 mb-6">
        <div className="border border-rule rounded-lg bg-surface p-5 space-y-5">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="md:col-span-2">
              <span className="eyebrow mb-2 block">Buscar</span>
              <Input
                placeholder="Proveedor, objeto, código…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
          </div>

          <SlicerPills
            label="Vigencia / Año de firma"
            options={yearOptions}
            selected={years}
            onChange={setYears}
          />
          <SlicerPills
            label="Estado del contrato"
            options={stateOptions}
            selected={states}
            onChange={setStates}
          />
          <SlicerPills
            label="Modalidad de contratación"
            options={modalityOptions}
            selected={modalities}
            onChange={setModalities}
          />
          {sheetOptions.length > 0 && (
            <SlicerPills
              label="Hoja Excel (donde la Dra registró el proceso)"
              options={sheetOptions}
              selected={sheets}
              onChange={setSheets}
            />
          )}

          {pageFiltersActive && (
            <div className="flex justify-end">
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setSearch("");
                  setYears([]);
                  setStates([]);
                  setModalities([]);
                  setSheets([]);
                }}
              >
                Limpiar filtros
              </Button>
            </div>
          )}
        </div>
      </div>

      {feedback && (
        <div className="mx-auto max-w-7xl px-8 mb-4">
          <div
            className={cn(
              "text-sm px-4 py-2 rounded-md border",
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
        </div>
      )}

      {/* TABLA UNIFICADA */}
      <div className="mx-auto max-w-7xl px-8 pb-12">
        <div className="flex items-baseline justify-between mb-4">
          <h2 className="serif text-2xl font-semibold text-ink">
            {onlyMine ? "Mis procesos seguidos" : "Inventario completo"}
          </h2>
          <span className="text-xs text-ink-soft">
            {filtered.length} de {allRows.length} mostrados
          </span>
        </div>

        {isLoading ? (
          <div className="flex items-center gap-2 py-16 text-ink-soft">
            <Loader2 className="h-5 w-5 animate-spin" /> Cargando datos…
          </div>
        ) : (
          <UnifiedTable
            rows={filtered}
            onPick={(id) => setSelected(id)}
            onAdd={handleAdd}
            onUpdate={handleUpdate}
            onRemove={handleRemove}
            busy={busy}
            totalAppearances={totalAppearances}
          />
        )}
      </div>

      <DetailDialog
        contractId={selected}
        open={!!selected}
        onOpenChange={(o) => !o && setSelected(null)}
      />

      {/* Footer */}
      <div className="rule mx-auto max-w-7xl my-8" />
      <div className="mx-auto max-w-7xl px-8 pb-12 text-center text-xs text-ink-soft">
        <span className="serif font-medium text-burgundy">
          Dra Cami Contractual
        </span>{" "}
        · Datos oficiales:{" "}
        <code className="font-mono">datos.gov.co / SECOP II</code> ·{" "}
        {new Date().toISOString().slice(0, 10)}
        {lastRefresh && (
          <span className="ml-3 text-emerald-700">
            <CheckCircle2 className="inline h-3 w-3 mr-1" />
            Última actualización: {lastRefresh.slice(11, 16)} UTC
          </span>
        )}
      </div>
    </main>
  );
}
