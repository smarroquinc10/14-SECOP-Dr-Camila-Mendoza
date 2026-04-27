"use client";

import * as React from "react";
import useSWR from "swr";
import {
  CheckCircle2,
  Database,
  Globe,
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
import type { PortalBulk } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  api,
  withBasePath,
  type Contract,
  type WatchedItem,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { exportRowsToExcel } from "@/lib/export-excel";

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

  // Portal scrape progress: poll igual que verify-progress pero para el
  // scraper del portal SECOP (community.secop.gov.co). Cada item toma
  // ~30-55s (Chrome visible + captcha amortizado), por eso refresh 5s.
  const { data: portalProgress, mutate: reloadPortalProgress } = useSWR(
    "portal-progress",
    api.portalProgress,
    { refreshInterval: 5_000 }
  );

  // SECOP Integrado bulk: enriquece la tabla principal con los procesos
  // que el API estándar no expone, SIN captcha. Recargamos cada 5 min
  // (el dataset rpmr-utcd no cambia más rápido que eso).
  const { data: integradoBulk, mutate: reloadIntegradoBulk } = useSWR(
    "integrado-bulk",
    api.integradoBulk,
    { refreshInterval: 300_000 }
  );

  // Portal cache (community.secop.gov.co) — seed estático bakeado al
  // bundle. Cubre los procesos que ni el SECOP API ni el Integrado
  // exponen (típicamente ~66 procs scrapeados del portal con captcha
  // resuelto a mano cuando se generó el seed). Cero refresh — es read-
  // only. Cuando deployes una versión nueva con seed actualizado, Cami
  // ve la nueva data al refrescar.
  const { data: portalBulk } = useSWR<PortalBulk>(
    "portal-bulk",
    api.portalBulk,
    { refreshInterval: 0, revalidateOnFocus: false }
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
  const [onlyMod, setOnlyMod] = React.useState(false);
  // Feature D (2026-04-26): Toggle "Vencen en 30 días" — la Dra como
  // contractual del FEAB necesita estar pendiente de contratos que vencen
  // pronto para anticipar liquidaciones / renovaciones / prórrogas.
  const [onlyExpiringSoon, setOnlyExpiringSoon] = React.useState(false);
  // Feature A (2026-04-26): Toggle "Requieren tu atención" — filas con
  // modificatorios recientes (últimos 7 días) o que vencen en 30 días.
  // Ayuda a estar pendiente sin abrumar.
  const [onlyAttention, setOnlyAttention] = React.useState(false);

  // ---- Build unified rows + busy/feedback state for actions -----------
  // Cardinal rule: cada celda con su procedencia clara.
  //   - data_source = "api"        → SECOP API estándar
  //   - data_source = "integrado"  → SECOP Integrado (sin captcha)
  //   - data_source = null         → ninguno; UI muestra "—" honesto
  const allRows = React.useMemo(
    () => buildUnifiedRows(watched, contracts, integradoBulk ?? null, portalBulk ?? null),
    [watched, contracts, integradoBulk, portalBulk]
  );

  const totalAppearances = React.useMemo(
    () => watched.reduce((acc, w) => acc + (w.appearances?.length ?? 0), 0),
    [watched]
  );

  // Coverage stats — qué porcentaje del watch list tiene datos automáticos
  // vs muestra "—" honesto. La Dra ve transparencia total: cuánto el sistema
  // cubre solo y cuánto requiere acción humana (botón "Abrir" o scrape local).
  const coverageStats = React.useMemo(() => {
    const watched_rows = allRows.filter((r) => r.watched);
    const total = watched_rows.length;
    const api = watched_rows.filter((r) => r.data_source === "api").length;
    const integrado = watched_rows.filter((r) => r.data_source === "integrado").length;
    const portal = watched_rows.filter((r) => r.data_source === "portal").length;
    const none = watched_rows.filter((r) => r.data_source == null).length;
    const cubierto = api + integrado + portal;
    const pct = total > 0 ? Math.round((cubierto / total) * 100) : 0;
    return { total, api, integrado, portal, none, cubierto, pct };
  }, [allRows]);

  // Frescura del SECOP — fecha del contrato más reciente entre los watched.
  // Sirve como indicador de "qué tan al día está la API pública vs hoy".
  // Si la última firma es de hace 30+ días, la Dra sabe que algo nuevo
  // probablemente todavía no está sincronizado.
  const freshnessStats = React.useMemo(() => {
    const fechas = allRows
      .filter((r) => r.watched && r.fecha_firma)
      .map((r) => r.fecha_firma as string)
      .sort()
      .reverse();
    const ultimaFirma = fechas[0] ?? null;
    let diasDesde: number | null = null;
    if (ultimaFirma) {
      const d = new Date(ultimaFirma);
      const hoy = new Date();
      diasDesde = Math.floor((hoy.getTime() - d.getTime()) / (1000 * 60 * 60 * 24));
    }
    return { ultimaFirma, diasDesde };
  }, [allRows]);

  // Feature B (2026-04-26): "Cambios recientes" — los ultimos N modificatorios
  // detectados en el watch list. Ayuda a la Dra a estar pendiente de cambios
  // sin tener que filtrar manualmente. Criterio: dias_adicionados > 0 ordenados
  // por fecha_firma descendente (proxy de "ultima actividad del proceso").
  const recentMods = React.useMemo(() => {
    return allRows
      .filter(
        (r) =>
          r.watched &&
          r.dias_adicionados != null &&
          r.dias_adicionados > 0
      )
      .sort((a, b) => (b.fecha_firma ?? "").localeCompare(a.fecha_firma ?? ""))
      .slice(0, 8);
  }, [allRows]);

  // Feature A (2026-04-26): Stats de "requieren atencion" para el header.
  // Union de mods recientes + venciendo en 30 dias (sin duplicados).
  const attentionStats = React.useMemo(() => {
    const today = new Date();
    let mods = 0;
    let expiring = 0;
    const seenKeys = new Set<string>();
    for (const r of allRows) {
      if (!r.watched) continue;
      let needs = false;
      const isMod =
        (r.dias_adicionados != null && r.dias_adicionados > 0) ||
        /modific/i.test(r.estado ?? "");
      if (isMod) needs = true;
      const fechaFin =
        (r._raw_api?.fecha_de_fin_del_contrato as string | undefined) ??
        (r._raw_integrado?.fecha_fin_ejecuci_n as string | undefined) ??
        null;
      let venceProx = false;
      if (fechaFin) {
        const fin = new Date(fechaFin);
        if (!isNaN(fin.getTime())) {
          const dias = Math.floor(
            (fin.getTime() - today.getTime()) / (1000 * 60 * 60 * 24)
          );
          venceProx = dias >= 0 && dias <= 30;
        }
      }
      if (venceProx) needs = true;
      if (!needs) continue;
      const k = r.process_id ?? r.id_contrato ?? "";
      if (seenKeys.has(k)) continue;
      seenKeys.add(k);
      if (isMod) mods++;
      if (venceProx) expiring++;
    }
    return { total: seenKeys.size, mods, expiring };
  }, [allRows]);

  // Feature I (2026-04-26): "Último scrape del portal" — fecha más reciente
  // de scraped_at entre todos los procesos del watch list cubiertos por
  // portal_seed. Esto le dice a la Dra "los datos del portal community.secop
  // se actualizaron por última vez el día X". El cron mensual de GitHub
  // Action lo refresca automáticamente.
  const lastPortalScrape = React.useMemo(() => {
    if (!portalBulk) return { fecha: null as string | null, diasDesde: null as number | null };
    const fechas = Object.values(portalBulk)
      .map((p) => p?.scraped_at)
      .filter((s): s is string => !!s)
      .sort()
      .reverse();
    const fecha = fechas[0] ?? null;
    let diasDesde: number | null = null;
    if (fecha) {
      const d = new Date(fecha);
      diasDesde = Math.floor((Date.now() - d.getTime()) / (1000 * 60 * 60 * 24));
    }
    return { fecha, diasDesde };
  }, [portalBulk]);

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
        // Bug A fix (2026-04-26): incluir notice_uid en el blob de búsqueda.
        // 276/491 items del watch list tienen notice_uid != process_id (ej.
        // process_id=CO1.PPI.10057597, notice_uid=CO1.NTC.1416630). Sin esto,
        // buscar por el código NTC que aparece en community.secop devolvía
        // "no encontrado" cuando la fila SÍ existe en la tabla. FN del filtro.
        const blob = (
          (r.id_contrato ?? "") +
          " " +
          (r.process_id ?? "") +
          " " +
          (r.notice_uid ?? "") +
          " " +
          (r.objeto ?? "") +
          " " +
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
      // Feature D (2026-04-26): "Vencen en 30 dias". El campo viene de
      // _raw_api.fecha_de_fin_del_contrato (jbjy-vk9h) o
      // _raw_integrado.fecha_fin_ejecuci_n (rpmr-utcd).
      if (onlyExpiringSoon) {
        const fechaFin =
          (r._raw_api?.fecha_de_fin_del_contrato as string | undefined) ??
          (r._raw_integrado?.fecha_fin_ejecuci_n as string | undefined) ??
          null;
        if (!fechaFin) return false;
        const fin = new Date(fechaFin);
        if (isNaN(fin.getTime())) return false;
        const hoy = new Date();
        const diasRestantes = Math.floor(
          (fin.getTime() - hoy.getTime()) / (1000 * 60 * 60 * 24)
        );
        if (diasRestantes < 0 || diasRestantes > 30) return false;
      }
      // Feature A (2026-04-26): "Requieren tu atencion" - union de:
      //   (a) modificatorios recientes (dias_adicionados > 0 + fecha_firma
      //       en ultimos 30 dias)
      //   (b) vencen en proximos 30 dias
      //   (c) estado contiene "modific" (literal del SECOP)
      if (onlyAttention) {
        const tieneModReciente =
          r.dias_adicionados != null && r.dias_adicionados > 0;
        const estadoMod = /modific/i.test(r.estado ?? "");
        const fechaFin =
          (r._raw_api?.fecha_de_fin_del_contrato as string | undefined) ??
          (r._raw_integrado?.fecha_fin_ejecuci_n as string | undefined) ??
          null;
        let venceProx = false;
        if (fechaFin) {
          const fin = new Date(fechaFin);
          if (!isNaN(fin.getTime())) {
            const dias = Math.floor(
              (fin.getTime() - new Date().getTime()) / (1000 * 60 * 60 * 24)
            );
            venceProx = dias >= 0 && dias <= 30;
          }
        }
        if (!tieneModReciente && !estadoMod && !venceProx) return false;
      }
      return true;
    });
    // When the user picks one or more sheet pills, expand every row
    // by its appearances in those sheets so the count matches the
    // Excel exactly (e.g. FEAB 2024 → 85 rows, not 66 dedup-by-process).
    return expandRowsByAppearance(base, sheets);
  }, [allRows, search, years, states, modalities, sheets, onlyMod, onlyMine, onlyExpiringSoon, onlyAttention]);

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

  /** Lanza el scraper del portal para TODOS los procesos pendientes
   *  (los que el API público no expone o los que tienen cache parcial).
   *  Tarda ~30-55s por proceso por el captcha amortizado. */
  async function handleScrapePortalAll() {
    setRefreshing(true);
    try {
      await api.portalScrape({});
      await new Promise((r) => setTimeout(r, 2000));
      await reloadPortalProgress();
      setFeedback({
        kind: "info",
        text:
          "Lectura del portal SECOP iniciada en segundo plano. " +
          "Si pide captcha la primera vez, resolvelo en la ventana de Chrome.",
      });
    } catch (err) {
      setFeedback({
        kind: "error",
        text: err instanceof Error ? err.message : "No pude iniciar el scraper.",
      });
    } finally {
      setRefreshing(false);
    }
  }

  /** Sincroniza el dataset SECOP Integrado (rpmr-utcd) — fuente pública
   *  sin captcha. Toma ~1s. Resuelve un montón de procesos sin tener
   *  que abrir el scraper del portal. */
  const [syncingInteg, setSyncingInteg] = React.useState(false);
  async function handleIntegradoSync() {
    setSyncingInteg(true);
    try {
      await api.integradoSync();
      // Esperar que el subprocess escriba (~1-2s típico) + refrescar.
      await new Promise((r) => setTimeout(r, 2500));
      await reloadIntegradoBulk();
      setFeedback({
        kind: "ok",
        text: "SECOP Integrado actualizado desde datos.gov.co.",
      });
    } catch (err) {
      setFeedback({
        kind: "error",
        text:
          err instanceof Error
            ? err.message
            : "No pude sincronizar SECOP Integrado.",
      });
    } finally {
      setSyncingInteg(false);
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

  /** Format a number of seconds as "Xm Ys" / "Ys" — for refresh timer/ETA. */
  function fmtDuration(seconds: number): string {
    if (seconds < 60) return `${Math.round(seconds)}s`;
    const m = Math.floor(seconds / 60);
    const s = Math.round(seconds % 60);
    return `${m}m ${s}s`;
  }

  const pageFiltersActive =
    !!search ||
    years.length > 0 ||
    states.length > 0 ||
    modalities.length > 0 ||
    sheets.length > 0 ||
    onlyMod ||
    onlyExpiringSoon ||
    onlyAttention;

  return (
    <main className="min-h-screen bg-background">
      {/* Top institutional strip — Fiscalía / FEAB identity */}
      <div className="border-b border-rule bg-surface">
        <div className="mx-auto max-w-7xl px-8 py-3 flex items-center justify-between gap-4">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={withBasePath("/feab-logo-square.png")}
            alt="FEAB · Fondo Especial para la Administración de Bienes"
            className="h-12 md:h-14 object-contain"
          />
          <div className="text-right">
            <div className="text-[10px] md:text-[11px] font-semibold uppercase tracking-[0.18em] text-burgundy">
              FEAB · Fondo Especial para la Administración de Bienes
            </div>
            <div className="text-[9px] md:text-[10px] text-ink-soft mt-0.5">
              NIT 901148337
            </div>
          </div>
        </div>
      </div>

      {/* Burgundy accent line */}
      <div className="h-1 bg-burgundy" />

      {/* Header — program title + personal greeting */}
      <div className="mx-auto max-w-7xl px-8 pt-10 pb-6">
        <div className="eyebrow mb-3">
          Sistema de Seguimiento de Contratos · SECOP II
        </div>
        <h1 className="serif text-4xl md:text-5xl font-bold tracking-tight text-ink mb-2">
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

        <Button
          size="lg"
          variant="outline"
          onClick={handleIntegradoSync}
          disabled={syncingInteg}
          className="gap-2"
          title="Sincroniza el dataset SECOP Integrado (rpmr-utcd) — fuente pública sin captcha. Tarda ~1 segundo."
        >
          {syncingInteg ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Database className="h-4 w-4" />
          )}
          {syncingInteg
            ? "Sincronizando…"
            : `Integrado (${integradoBulk?.total_rows ?? "—"})`}
        </Button>

        <Button
          size="lg"
          variant="outline"
          onClick={handleScrapePortalAll}
          disabled={refreshing || (portalProgress?.running ?? false)}
          className="gap-2"
          title="Lee directo del portal community.secop.gov.co los procesos que el API público no expone"
        >
          {portalProgress?.running ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Globe className="h-4 w-4" />
          )}
          {portalProgress?.running
            ? `Leyendo portal… (${portalProgress.processed}/${portalProgress.total})`
            : "Leer del portal SECOP"}
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

        {/* Cobertura SECOP — Bug F UX (2026-04-26): indicador prominente
            de qué porcentaje del watch list tiene datos automáticos vs
            muestra "—" honesto. Cumple regla cardinal "honestidad cuando
            no sabe" + da claridad operativa a la Dra. */}
        {coverageStats.total > 0 && (
          <div
            className="flex flex-col text-[11px] text-ink-soft border-l border-rule pl-3"
            title={`API jbjy-vk9h: ${coverageStats.api} · SECOP Integrado: ${coverageStats.integrado} · Portal cache: ${coverageStats.portal} · Sin cobertura API (viven solo en community.secop): ${coverageStats.none}`}
          >
            <span className="eyebrow">Cobertura automática</span>
            <span className="font-mono text-ink">
              <span
                className={cn(
                  coverageStats.pct >= 80
                    ? "text-emerald-700"
                    : coverageStats.pct >= 50
                    ? "text-amber-700"
                    : "text-rose-700"
                )}
              >
                {coverageStats.cubierto}/{coverageStats.total}
              </span>
              {" · "}
              <span className="text-ink-soft">{coverageStats.pct}%</span>
            </span>
            <span className="text-[10px] mt-0.5">
              {coverageStats.none} sin API · click "Abrir" en la fila
            </span>
          </div>
        )}

        {/* Frescura datos.gov.co — última firma de contrato detectada. */}
        {freshnessStats.ultimaFirma && (
          <div
            className="flex flex-col text-[11px] text-ink-soft border-l border-rule pl-3"
            title={`Última firma de contrato del FEAB en datos.gov.co: ${freshnessStats.ultimaFirma}. Las APIs públicas tienen lag de ~1-2 semanas vs community.secop. Cron 'Refrescar seeds' corre cada día 06:00 UTC.`}
          >
            <span className="eyebrow">Última firma SECOP</span>
            <span className="font-mono text-ink">
              {freshnessStats.ultimaFirma.slice(0, 10)}
            </span>
            <span className="text-[10px] mt-0.5">
              {freshnessStats.diasDesde === 0
                ? "hoy"
                : freshnessStats.diasDesde === 1
                ? "hace 1 día"
                : `hace ${freshnessStats.diasDesde} días`}
            </span>
          </div>
        )}

        {/* Feature I (2026-04-26): "Último scrape portal" — cuándo se
            actualizó el cache de community.secop por última vez. Verde
            si reciente (<30d), ámbar (30-60d), rojo (>60d). Click navega
            a la GitHub Action mensual para que la Dra/IT puedan triggear
            un refresh manual sin esperar el cron. */}
        {lastPortalScrape.fecha && (
          <a
            href="https://github.com/smarroquinc10/14-SECOP-Dr-Camila-Mendoza/actions/workflows/scrape-portal-mensual.yml"
            target="_blank"
            rel="noopener noreferrer"
            className={cn(
              "flex flex-col text-[11px] border-l border-rule pl-3 hover:underline",
              lastPortalScrape.diasDesde != null && lastPortalScrape.diasDesde < 30
                ? "text-emerald-700"
                : lastPortalScrape.diasDesde != null && lastPortalScrape.diasDesde < 60
                ? "text-amber-700"
                : "text-rose-700"
            )}
            title={`Último scrape del portal community.secop: ${lastPortalScrape.fecha}. Cron mensual día 1 04:00 UTC. Click → ir a GitHub Actions para refrescar manual.`}
          >
            <span className="eyebrow">Último refresh portal</span>
            <span className="font-mono">
              {lastPortalScrape.fecha.slice(0, 10)}
            </span>
            <span className="text-[10px] mt-0.5">
              {lastPortalScrape.diasDesde === 0
                ? "hoy 🔄"
                : lastPortalScrape.diasDesde === 1
                ? "ayer"
                : `hace ${lastPortalScrape.diasDesde} días`}
            </span>
          </a>
        )}

        {/* Feature A (2026-04-26): "Requieren atención" — la Dra como
            contractual del FEAB ve de un vistazo cuántos procesos tienen
            modificatorios o están por vencer. Click navega al filtro. */}
        {attentionStats.total > 0 && (
          <button
            onClick={() => {
              setOnlyAttention(true);
              window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
            }}
            className="flex flex-col text-[11px] text-amber-700 border-l border-rule pl-3 cursor-pointer hover:text-amber-900 text-left"
            title={`${attentionStats.mods} con modificatorios + ${attentionStats.expiring} por vencer en 30 días. Click → activa el filtro.`}
          >
            <span className="eyebrow text-amber-700">🔔 Requieren atención</span>
            <span className="font-mono font-bold text-amber-900 text-base">
              {attentionStats.total}
            </span>
            <span className="text-[10px] mt-0.5">
              {attentionStats.mods} mods · {attentionStats.expiring} por vencer
            </span>
          </button>
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
          OR for ~30s after a completed run so the Dra sees the result.
          Layout: counts on top row, ETA + elapsed on bottom row so it
          never hides off-screen on narrow windows. */}
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
            <div className="flex items-center justify-between text-xs mb-2 gap-3">
              <span className="font-medium text-ink truncate">
                {verifyProgress.running
                  ? "Refrescando contra SECOP…"
                  : "Refresco completado"}
              </span>
              <span className="font-mono text-ink-soft whitespace-nowrap">
                {verifyProgress.processed} / {verifyProgress.total} ·{" "}
                {verifyProgress.percent}%
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
            {/* Tiempo transcurrido + ETA — siempre visibles abajo, nunca se cortan. */}
            <div className="flex flex-wrap items-center justify-between gap-3 mt-3 text-[11px]">
              <div className="text-ink-soft font-mono">
                {verifyProgress.elapsed_seconds != null && (
                  <span>
                    Transcurrido:{" "}
                    <span className="text-ink font-semibold">
                      {fmtDuration(verifyProgress.elapsed_seconds)}
                    </span>
                  </span>
                )}
              </div>
              <div className="font-mono">
                {verifyProgress.running &&
                  verifyProgress.eta_seconds != null && (
                    <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded bg-burgundy/10 text-burgundy">
                      <span className="text-[10px] uppercase tracking-wider opacity-70">
                        Tiempo restante
                      </span>
                      <span className="font-bold">
                        ≈ {fmtDuration(verifyProgress.eta_seconds)}
                      </span>
                    </span>
                  )}
                {verifyProgress.running &&
                  verifyProgress.eta_seconds == null && (
                    <span className="text-ink-soft italic">
                      Calculando tiempo restante…
                    </span>
                  )}
              </div>
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

      {/* Portal scrape progress — barra paralela a la del verify para
          el scraper de community.secop.gov.co. Se muestra mientras el
          scraper escribe en .cache/portal_progress.jsonl y ~30s después
          de terminar para que la Dra vea el resumen. */}
      {portalProgress &&
        portalProgress.total > 0 &&
        (portalProgress.running ||
          (portalProgress.processed > 0 &&
            (portalProgress.last_update_age_seconds ?? 999) < 30)) && (
          <div className="mx-auto max-w-7xl px-8 mb-6">
            <div
              className={cn(
                "border rounded-lg p-4",
                portalProgress.running
                  ? "border-burgundy/30 bg-burgundy/5"
                  : "border-emerald-300 bg-emerald-50",
              )}
            >
              <div className="flex items-center justify-between text-xs mb-2 gap-3">
                <span className="font-medium text-ink truncate inline-flex items-center gap-1.5">
                  <Globe className="h-3.5 w-3.5" />
                  {portalProgress.running
                    ? "Leyendo del portal SECOP…"
                    : "Lectura del portal completada"}
                </span>
                <span className="font-mono text-ink-soft whitespace-nowrap">
                  {portalProgress.processed} / {portalProgress.total} ·{" "}
                  {portalProgress.percent}%
                </span>
              </div>
              <div className="h-2 bg-stone-100 rounded-full overflow-hidden">
                <div
                  className={cn(
                    "h-full transition-all duration-300 rounded-full",
                    portalProgress.running ? "bg-burgundy" : "bg-emerald-500",
                  )}
                  style={{ width: `${portalProgress.percent}%` }}
                />
              </div>
              <div className="flex flex-wrap items-center justify-between gap-3 mt-3 text-[11px]">
                <div className="text-ink-soft font-mono">
                  {portalProgress.elapsed_seconds != null && (
                    <span>
                      Transcurrido:{" "}
                      <span className="text-ink font-semibold">
                        {fmtDuration(portalProgress.elapsed_seconds)}
                      </span>
                    </span>
                  )}
                </div>
                <div className="font-mono">
                  {portalProgress.running &&
                    portalProgress.eta_seconds != null && (
                      <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded bg-burgundy/10 text-burgundy">
                        <span className="text-[10px] uppercase tracking-wider opacity-70">
                          Tiempo restante
                        </span>
                        <span className="font-bold">
                          ≈ {fmtDuration(portalProgress.eta_seconds)}
                        </span>
                      </span>
                    )}
                </div>
              </div>
              {!portalProgress.running && portalProgress.processed > 0 && (
                <div className="text-[11px] text-ink-soft mt-2 italic">
                  {portalProgress.ok ?? 0} completos · {portalProgress.partial ?? 0}{" "}
                  parciales · {portalProgress.errored ?? 0} errores. Cada
                  proceso ya está en el snapshot del portal.
                </div>
              )}
              {portalProgress.running && (
                <div className="text-[11px] text-ink-soft mt-2 italic">
                  Si SECOP pide captcha, resolvelo en la ventana de Chrome
                  visible — queda guardado para los siguientes procesos.
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

          {/* Features A+D (2026-04-26): toggles para "estar pendiente"
              sin abrumar a la Dra. Combinan modificatorios + vencimientos. */}
          <div className="flex flex-wrap items-center gap-3 pt-2 border-t border-rule mt-2">
            <span className="eyebrow text-ink-soft">ATAJOS</span>
            <label className="flex items-center gap-2 cursor-pointer text-sm text-ink-soft hover:text-ink">
              <input
                type="checkbox"
                checked={onlyAttention}
                onChange={(e) => setOnlyAttention(e.target.checked)}
                className="rounded"
              />
              <span>
                🔔 Requieren tu atención{" "}
                {attentionStats.total > 0 && (
                  <span className="font-mono text-[11px] text-amber-700">
                    ({attentionStats.total})
                  </span>
                )}
              </span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer text-sm text-ink-soft hover:text-ink">
              <input
                type="checkbox"
                checked={onlyMod}
                onChange={(e) => setOnlyMod(e.target.checked)}
                className="rounded"
              />
              <span>Solo contratos modificados</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer text-sm text-ink-soft hover:text-ink">
              <input
                type="checkbox"
                checked={onlyExpiringSoon}
                onChange={(e) => setOnlyExpiringSoon(e.target.checked)}
                className="rounded"
              />
              <span>
                ⏰ Vencen en 30 días{" "}
                {attentionStats.expiring > 0 && (
                  <span className="font-mono text-[11px] text-rose-700">
                    ({attentionStats.expiring})
                  </span>
                )}
              </span>
            </label>
          </div>

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
                  setOnlyMod(false);
                  setOnlyExpiringSoon(false);
                  setOnlyAttention(false);
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

      {/* Feature B (2026-04-26): "Cambios recientes" — los ultimos N
          modificatorios del watch list. La Dra como contractual del FEAB
          los ve de un vistazo sin filtrar manualmente. Click → modal del
          proceso especifico. */}
      {recentMods.length > 0 && (
        <div className="mx-auto max-w-7xl px-8 pb-6">
          <div className="bg-amber-50 border border-amber-200 rounded-md p-4">
            <div className="flex items-center justify-between mb-2">
              <h3 className="serif text-base font-semibold text-amber-900">
                🔔 Cambios recientes en tus procesos
              </h3>
              <span className="text-[11px] text-amber-700">
                últimos {recentMods.length} modificatorios detectados
              </span>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {recentMods.map((r) => (
                <button
                  key={r.key}
                  onClick={() => setSelected(r.key)}
                  className="text-left bg-white border border-amber-200 rounded px-3 py-2 hover:border-amber-400 hover:bg-amber-50 text-xs"
                  title={`Click para ver detalle de ${r.process_id ?? r.id_contrato}`}
                >
                  <div className="font-mono text-amber-900 text-[11px] mb-0.5">
                    {r.numero_contrato ?? r.process_id ?? r.id_contrato}
                  </div>
                  <div className="text-ink line-clamp-1">
                    {r.objeto ?? "(sin objeto)"}
                  </div>
                  <div className="flex items-center gap-2 mt-1 text-[10px] text-ink-soft">
                    <span>+{r.dias_adicionados} días adic.</span>
                    {r.fecha_firma && (
                      <span>· firmado {r.fecha_firma.slice(0, 10)}</span>
                    )}
                    {r.estado && <span>· {r.estado}</span>}
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* TABLA UNIFICADA */}
      <div className="mx-auto max-w-7xl px-8 pb-12">
        <div className="flex items-center justify-between mb-4 gap-3">
          <h2 className="serif text-2xl font-semibold text-ink">
            {onlyMine ? "Mis procesos seguidos" : "Inventario completo"}
          </h2>
          <div className="flex items-center gap-3">
            <span className="text-xs text-ink-soft">
              {/* Bug C fix (2026-04-26): el divisor era allRows.length que
                  incluye 282 contratos huerfanos del SECOP no presentes en
                  el watch list. Con onlyMine=true esos quedan filtrados,
                  pero el counter mostraba "X de 773" engañoso. CLAUDE.md
                  regla 8: vista por defecto = SUS 491 procesos. Counter
                  ahora refleja solo lo realmente mostrable. */}
              {filtered.length} de {allRows.filter((r) => r.watched).length} mostrados
            </span>
            <Button
              size="sm"
              variant="outline"
              disabled={filtered.length === 0}
              onClick={async () => {
                try {
                  await exportRowsToExcel(filtered, "FEAB-procesos");
                  setFeedback({
                    kind: "ok",
                    text: `Excel descargado · ${filtered.length} filas`,
                  });
                } catch (err) {
                  setFeedback({
                    kind: "error",
                    text:
                      err instanceof Error
                        ? err.message
                        : "No pude generar el Excel.",
                  });
                }
              }}
              className="gap-2"
              title="Descarga lo que tenés filtrado en pantalla como un .xlsx"
            >
              <Database className="h-4 w-4" />
              Descargar Excel ({filtered.length})
            </Button>
          </div>
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

      {/* Institutional footer — sellos del Estado Colombiano + identidad FEAB */}
      <div className="border-t border-rule bg-surface mt-12">
        <div className="mx-auto max-w-7xl px-8 py-8">
          {/* Sellos gov.co — wrapped, monochromed at low opacity for sobriety */}
          <div className="flex flex-wrap items-center justify-center gap-x-8 gap-y-4 mb-6 opacity-80">
            {[
              { src: "/sellos/Todos_pais.png", alt: "Todos por un país" },
              { src: "/sellos/Col_compra.png", alt: "Colombia Compra Eficiente" },
              { src: "/sellos/gov.co-footer.png", alt: "gov.co" },
              { src: "/sellos/Gob_linea.png", alt: "Gobierno en línea" },
            ].map((s) => (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                key={s.src}
                src={withBasePath(s.src)}
                alt={s.alt}
                className="h-9 md:h-10 object-contain"
              />
            ))}
          </div>

          <div className="rule mb-5" />

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 items-start text-[11px]">
            <div>
              <div className="eyebrow mb-1">Entidad</div>
              <div className="text-ink font-semibold">
                FEAB — Fondo Especial para la Administración de Bienes
              </div>
              <div className="text-ink-soft mt-0.5">
                NIT 901148337
              </div>
            </div>
            <div>
              <div className="eyebrow mb-1">Sistema</div>
              <div className="text-ink font-semibold">
                Sistema de Seguimiento de Contratos · SECOP II
              </div>
              <div className="text-ink-soft mt-0.5">
                Espejo automático del SECOP — datos oficiales{" "}
                <code className="font-mono">datos.gov.co</code>
              </div>
            </div>
            <div>
              <div className="eyebrow mb-1">Estado</div>
              <div className="text-ink-soft font-mono">
                {new Date().toISOString().slice(0, 10)}
              </div>
              {lastRefresh && (
                <div className="text-emerald-700 mt-0.5 inline-flex items-center gap-1">
                  <CheckCircle2 className="h-3 w-3" />
                  Última actualización: {lastRefresh.slice(11, 16)} UTC
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
