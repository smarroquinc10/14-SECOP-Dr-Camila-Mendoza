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

import { ContractsTable } from "@/components/contracts-table";
import { DetailDialog } from "@/components/detail-dialog";
import { ModsPanel } from "@/components/mods-panel";
import { SlicerPills } from "@/components/slicer-pills";
import { WatchListPanel } from "@/components/watch-list";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, type Contract } from "@/lib/api";
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
    isLoading,
    mutate: reloadContracts,
  } = useSWR<Contract[]>("contracts:500", () => api.contracts(500));
  const { data: audit } = useSWR("audit:50", () => api.auditLog(50), {
    refreshInterval: 60_000,
  });
  const { data: ultActualiz, mutate: reloadUltActualiz } = useSWR(
    "ultima-actualizacion",
    api.ultimaActualizacion,
    { refreshInterval: 30_000 }
  );

  // ---- Filter state -----------------------------------------------------
  const [search, setSearch] = React.useState("");
  const [years, setYears] = React.useState<string[]>([]);
  const [states, setStates] = React.useState<string[]>([]);
  const [modalities, setModalities] = React.useState<string[]>([]);
  const [onlyMod, setOnlyMod] = React.useState(false);
  const [selected, setSelected] = React.useState<string | null>(null);

  // Distinct option sets (computed once per data change)
  const yearOptions = React.useMemo(
    () =>
      Array.from(
        new Set(
          contracts
            .map((c) => (c.fecha_de_firma ?? "").slice(0, 4))
            .filter(Boolean)
        )
      ).sort((a, b) => b.localeCompare(a)),
    [contracts]
  );
  const stateOptions = React.useMemo(
    () =>
      Array.from(
        new Set(contracts.map((c) => c.estado_contrato ?? "").filter(Boolean))
      ).sort(),
    [contracts]
  );
  const modalityOptions = React.useMemo(
    () =>
      Array.from(
        new Set(
          contracts.map((c) => c.modalidad_de_contratacion ?? "").filter(Boolean)
        )
      ).sort(),
    [contracts]
  );

  // ---- Apply filters ----------------------------------------------------
  const filtered = React.useMemo(() => {
    return contracts.filter((c) => {
      if (search) {
        const blob = (
          (c.id_contrato ?? "") +
          (c.objeto_del_contrato ?? "") +
          (c.proveedor_adjudicado ?? "") +
          (c.referencia_del_contrato ?? "")
        ).toLowerCase();
        if (!blob.includes(search.toLowerCase())) return false;
      }
      if (years.length && !years.includes((c.fecha_de_firma ?? "").slice(0, 4)))
        return false;
      if (states.length && !states.includes(c.estado_contrato ?? "")) return false;
      if (
        modalities.length &&
        !modalities.includes(c.modalidad_de_contratacion ?? "")
      )
        return false;
      if (onlyMod && !(c.estado_contrato ?? "").toLowerCase().includes("modific"))
        return false;
      return true;
    });
  }, [contracts, search, years, states, modalities, onlyMod]);

  // ---- Refresh ---------------------------------------------------------
  const [refreshing, setRefreshing] = React.useState(false);
  const [lastRefresh, setLastRefresh] = React.useState<string | null>(null);

  async function handleRefresh() {
    setRefreshing(true);
    try {
      await api.refresh();
      // Wait a beat for the SECOP fetch to complete, then reload.
      await new Promise((r) => setTimeout(r, 2500));
      await Promise.all([reloadContracts(), reloadUltActualiz()]);
      setLastRefresh(new Date().toISOString());
    } catch (err) {
      console.error(err);
    } finally {
      setRefreshing(false);
    }
  }

  function fmtTimestamp(iso: string | null | undefined): string {
    if (!iso) return "—";
    const d = new Date(iso);
    return new Intl.DateTimeFormat("es-CO", {
      day: "2-digit", month: "short", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    }).format(d);
  }

  return (
    <main className="min-h-screen bg-background">
      {/* Top rule + header */}
      <div className="h-1 bg-secondary" />

      <div className="mx-auto max-w-7xl px-8 pt-12 pb-6">
        <div className="eyebrow mb-3">Auditoría · Gestión Contractual</div>
        <h1 className="serif text-5xl font-bold tracking-tight text-ink mb-2">
          Bienvenida, Dra. María Camila Mendoza Zubiría
        </h1>
        <div className="eyebrow text-ink-soft">
          Jefe de Gestión Contractual del FEAB · {TODAY}
        </div>
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
            <span className="font-mono">{feab.procesos}</span> procesos
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

      {/* Modificatorios summary panel — always at the top so the Dra
          sees the most recent modification across her portfolio at a glance. */}
      <div className="mx-auto max-w-7xl px-8 mb-6">
        <ModsPanel onPickContract={(id) => setSelected(id)} />
      </div>

      {/* Mis procesos seguidos — manual watch list (add/remove SECOP URLs) */}
      <div className="mx-auto max-w-7xl px-8 mb-6">
        <WatchListPanel onPickProcessId={(id) => setSelected(id)} />
      </div>

      {/* Filters card */}
      <div className="mx-auto max-w-7xl px-8 mb-6">
        <div className="border border-rule rounded-lg bg-surface p-5 space-y-5">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="md:col-span-2">
              <span className="eyebrow mb-2 block">Buscar</span>
              <Input
                placeholder="Proveedor, objeto, código de contrato…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <div>
              <span className="eyebrow mb-2 block">Marcas</span>
              <label className="flex items-center gap-2 text-sm text-ink cursor-pointer h-10 px-3 border border-input rounded-md hover:bg-background">
                <input
                  type="checkbox"
                  checked={onlyMod}
                  onChange={(e) => setOnlyMod(e.target.checked)}
                  className="rounded border-border"
                />
                Solo modificados
              </label>
            </div>
          </div>

          <SlicerPills
            label="Año de firma"
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
        </div>
      </div>

      {/* Table */}
      <div className="mx-auto max-w-7xl px-8 pb-12">
        <div className="flex items-baseline justify-between mb-4">
          <h2 className="serif text-2xl font-semibold text-ink">
            Inventario de contratos
          </h2>
          <span className="text-xs text-ink-soft">
            {filtered.length} de {contracts.length} mostrados
          </span>
        </div>

        {isLoading ? (
          <div className="flex items-center gap-2 py-16 text-ink-soft">
            <Loader2 className="h-5 w-5 animate-spin" /> Consultando SECOP II…
          </div>
        ) : (
          <ContractsTable
            data={filtered}
            onRowClick={(c) => setSelected(c.id_contrato ?? null)}
            pageFiltersActive={
              !!search ||
              years.length > 0 ||
              states.length > 0 ||
              modalities.length > 0 ||
              onlyMod
            }
            onResetAll={() => {
              setSearch("");
              setYears([]);
              setStates([]);
              setModalities([]);
              setOnlyMod(false);
            }}
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
        <span className="serif font-medium text-burgundy">Dra Cami Contractual</span>{" "}
        · Datos oficiales:{" "}
        <code className="font-mono">datos.gov.co / SECOP II</code>{" "}
        · {new Date().toISOString().slice(0, 10)}
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
