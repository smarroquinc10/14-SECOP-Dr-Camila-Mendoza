"use client";

import * as React from "react";
import {
  type Column,
  type ColumnDef,
  type ColumnFiltersState,
  type SortingState,
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  Check,
  ExternalLink,
  Filter,
  Pencil,
  Plus,
  RotateCcw,
  Trash2,
  X as XIcon,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  type Contract,
  type IntegradoSummary,
  type WatchedAppearance,
  type WatchedItem,
} from "@/lib/api";

/** Mapa del bulk SECOP Integrado pasado por la página. */
export interface IntegradoBulk {
  by_notice_uid: Record<string, IntegradoSummary>;
  by_pccntr: Record<string, IntegradoSummary>;
  synced_at?: string | null;
}
import { cn, moneyCO } from "@/lib/utils";

/* ──────────────── Excel-style filter types ─────────────────────────── */

type FilterVal =
  | { kind: "text"; q: string }
  | { kind: "set"; values: string[] };

function matchFilter(fv: FilterVal | undefined, value: string): boolean {
  if (!fv) return true;
  if (fv.kind === "set") {
    if (fv.values.length === 0) return true;
    return fv.values.includes(value);
  }
  const q = (fv.q ?? "").toLowerCase();
  if (!q) return true;
  return value.toLowerCase().includes(q);
}

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
  numero_contrato: string | null;  // CONTRATO-FEAB-NNNN-AAAA from Excel
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

  // De qué fuente vienen los campos visibles (estado/valor/proveedor/...).
  // - "api"        → SECOP API estandar (p6dx-8zbt / jbjy-vk9h vía /contracts)
  // - "integrado"  → SECOP Integrado (rpmr-utcd) — fallback sin captcha
  // - "portal"     → Snapshot cacheado del scraper de community.secop.gov.co
  //                  bakeado al bundle (cuando ningún API público lo expone).
  // - null         → ninguna fuente tuvo match; las celdas muestran "—" honesto
  // La UI muestra un badge claro cuando data_source !== "api" para que la
  // procedencia NUNCA quede ambigua.
  data_source: "api" | "integrado" | "portal" | null;

  // Cuándo se obtuvo la data del portal (cuando data_source === "portal").
  // Permite al badge mostrar antigüedad real ("hace 3 días" / "hace 2 meses")
  // en lugar del genérico "vía portal cache". null cuando no aplica.
  data_source_scraped_at: string | null;

  // Payloads CRUDOS de cada fuente — guardados acá para que `export-excel.ts`
  // pueda volcar TODOS los campos del SECOP al XLSX. La regla cardinal "ver
  // todo" exige que la descarga incluya 100% de los campos que devuelve
  // cada API, no solo los curados de la vista. Si una fuente no tiene
  // match, el raw queda en null y no contribuye columnas a esa fila.
  _raw_api: Record<string, unknown> | null;
  _raw_integrado: Record<string, unknown> | null;
  _raw_portal: Record<string, unknown> | null;
}

/** Mapa del bulk Portal cache pasado por la página — cada entry es el
 *  snapshot ya scrapeado del portal community.secop, indexado por
 *  notice_uid. */
export interface PortalBulk {
  [notice_uid: string]: {
    fields?: Record<string, string | null>;
    documents?: { name: string; url: string }[];
    notificaciones?: { proceso: string; evento: string; fecha: string }[];
    status?: string | null;
    scraped_at?: string | null;
  };
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
  integ: IntegradoSummary | null = null,
  hasPortalSnapshot: boolean = false,
): UnifiedRow["verifyStatus"] {
  // 1. If we have an API contract, it IS in the public API.
  if (contract?.id_contrato) return "contrato_firmado";
  // 2. If watch has notice_uid resolved, it's verified against datos.gov.co.
  if (watch?.notice_uid) return "verificado";
  // 3. Integrado matchea => el proceso ESTÁ publicado en datos.gov.co
  //    (rpmr-utcd combina SECOP I + II).
  if (integ) return "verificado";
  // 4. Portal cache hit => sí está en community.secop.gov.co aunque no
  //    en datos.gov.co. La data viene del scrape previo bakeado.
  if (hasPortalSnapshot) return "verificado";
  // 5. If process_id is a workspace ID (REQ/BDOS), it's a draft.
  const pid = watch?.process_id ?? "";
  if (pid.startsWith("CO1.REQ.") || pid.startsWith("CO1.BDOS.")) {
    return "borrador";
  }
  // 6. Otherwise: not in any public source.
  return "no_en_api";
}

/**
 * El portal SECOP devuelve `valor_total` como string formateado al estilo
 * colombiano: "12.000.000" o "$ 12.000.000,00". Lo normalizo a number
 * para que la columna de Valor muestre el monto bien formateado por
 * `moneyCO`. Si no parsea, devuelvo null (la celda muestra "—" honesto).
 */
function parsePortalValor(raw: string | null | undefined): number | null {
  if (!raw) return null;
  // Limpia "$", espacios, "COP", " ".
  let s = String(raw).replace(/[^\d.,-]/g, "").trim();
  if (!s) return null;
  // En CO: separador de miles "." y decimal ",". Si hay coma, lo trato
  // como decimal — antes de la coma son miles.
  if (s.includes(",")) {
    s = s.replace(/\./g, "").replace(",", ".");
  } else {
    // Solo dots: pueden ser miles. "12.000.000" → "12000000"
    s = s.replace(/\./g, "");
  }
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}

/**
 * El portal usa formatos de fecha tipo "27/05/2024 10:30 AM (UTC -5)" o
 * "2024-05-27T10:30:00". Extraigo la fecha YYYY-MM-DD si puedo. Si no,
 * devuelvo null.
 */
function parsePortalFecha(raw: string | null | undefined): string | null {
  if (!raw) return null;
  const s = String(raw).trim();
  // ISO: 2024-05-27 / 2024-05-27T...
  const iso = s.match(/^(\d{4}-\d{2}-\d{2})/);
  if (iso) return iso[1];
  // CO: 27/05/2024 → 2024-05-27
  const co = s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})/);
  if (co) {
    return `${co[3]}-${co[2].padStart(2, "0")}-${co[1].padStart(2, "0")}`;
  }
  return null;
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
  integradoBulk?: IntegradoBulk | null,
  portalBulk?: PortalBulk | null,
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

  // Lookup helper: SECOP Integrado por notice_uid o PCCNTR. Devuelve
  // un summary inmutable (no se modifica) o null si no hay match.
  //
  // CASCADA DE LOOKUP (importa el orden):
  //   1. notice_uid del watch list → by_notice_uid (NTC format)
  //   2. process_id del watch list → by_pccntr (PCCNTR format)
  //   3. process_id del watch list → by_notice_uid (cuando el seed guardó
  //      el NTC como process_id pero el verify_watch script no había
  //      corrido para resolver notice_uid). Esto era un agujero del que
  //      caían 491 procs y por eso el badge mostraba "No en API público".
  const lookupIntegrado = (
    notice_uid: string | null,
    process_id: string | null,
  ): IntegradoSummary | null => {
    if (!integradoBulk) return null;
    if (notice_uid && integradoBulk.by_notice_uid[notice_uid]) {
      return integradoBulk.by_notice_uid[notice_uid];
    }
    if (process_id && integradoBulk.by_pccntr[process_id]) {
      return integradoBulk.by_pccntr[process_id];
    }
    // Fallback: process_id en formato NTC matchea by_notice_uid
    if (process_id && integradoBulk.by_notice_uid[process_id]) {
      return integradoBulk.by_notice_uid[process_id];
    }
    return null;
  };

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

    // Cascada de fuentes (regla cardinal: cada celda con su procedencia clara):
    //   1. SECOP API contracts dataset       →  data_source = "api"
    //   2. SECOP Integrado (rpmr-utcd)       →  data_source = "integrado"
    //   3. Portal cache (community.secop)    →  data_source = "portal"
    //   4. ninguna  →  data_source = null, campos null, UI muestra "—"
    //
    // NO se mergean: el primer match gana entero. La Dra siempre sabe
    // de qué fuente viene cada fila gracias al badge en la columna Origen.
    const integ =
      contract == null
        ? lookupIntegrado(w.notice_uid, w.process_id)
        : null;
    // Portal cache: clave es notice_uid (formato CO1.NTC.X). Si el watch
    // ya tiene notice_uid lo usamos; si no, el process_id puede ser un
    // NTC también (mismo agujero que ya tapamos en lookupIntegrado).
    let portalSnap: PortalBulk[string] | null = null;
    if (contract == null && integ == null && portalBulk) {
      const key1 = w.notice_uid ?? "";
      const key2 = w.process_id ?? "";
      portalSnap = portalBulk[key1] ?? portalBulk[key2] ?? null;
    }
    const dataSource: UnifiedRow["data_source"] = contract
      ? "api"
      : integ
      ? "integrado"
      : portalSnap
      ? "portal"
      : null;
    const dataSourceScrapedAt =
      dataSource === "portal" ? portalSnap?.scraped_at ?? null : null;

    const apiDias = parseInt(String(contract?.dias_adicionados ?? "0"), 10);
    const dias =
      Number.isFinite(apiDias) && apiDias > 0 ? apiDias : null;
    const liq =
      String(contract?.liquidaci_n ?? "")
        .trim()
        .toLowerCase() === "si";

    // Valor: del API si hay contrato, sino del Integrado, sino del Portal.
    let valor: number | null = null;
    if (contract) {
      const valorRaw = contract.valor_del_contrato;
      if (valorRaw != null && valorRaw !== "") {
        const n = Number(valorRaw);
        if (Number.isFinite(n)) valor = n;
      }
    } else if (integ?.valor_contrato) {
      const n = Number(integ.valor_contrato);
      if (Number.isFinite(n)) valor = n;
    } else if (portalSnap?.fields?.valor_total) {
      valor = parsePortalValor(portalSnap.fields.valor_total);
    }

    // Notas: la regla cardinal del CLAUDE.md dice que las observaciones
    // manuales de la Dra (`obs_brief`) se muestran SÓLO en el modal de
    // detalle, NUNCA en la tabla principal. Antes este bloque mezclaba
    // obs_brief con prefijo "(Excel)" en la columna Modificatorios — lo
    // cual era doble violación: (1) leakeaba observación manual al main
    // table, (2) etiquetaba como "(Excel)" data que en HTML-pure viene
    // de IndexedDB (no del Excel original).
    //
    // En HTML-pure el SECOP API tampoco devuelve `_notas` (es un campo
    // computado por el FastAPI legacy). Por eso siempre queda null acá
    // y la celda Modificatorios muestra "Sin modificatorios" o
    // "Modificado +N días" según `dias_adicionados` del API.
    const notas: string | null = null;

    rows.push({
      key: contract?.id_contrato ?? w.url ?? `${w.process_id ?? "noid"}-${rows.length}`,
      process_id: w.process_id,
      id_contrato: contract?.id_contrato ?? integ?.numero_del_contrato ?? null,
      notice_uid: w.notice_uid ?? contract?.proceso_de_compra ?? null,
      // numero_contrato: del API si hay (referencia_del_contrato); del
      // Integrado si no hay (numero_de_proceso = CONTRATO-FEAB-XXXX o
      // numero_del_contrato = CO1.PCCNTR.X). NUNCA del Excel.
      numero_contrato:
        (contract?.referencia_del_contrato as string) ??
        integ?.numero_de_proceso ??
        integ?.numero_del_contrato ??
        portalSnap?.fields?.numero_contrato ??
        portalSnap?.fields?.numero_proceso ??
        null,
      url: w.url,
      objeto:
        (contract?.objeto_del_contrato as string) ??
        integ?.objeto_a_contratar ??
        portalSnap?.fields?.descripcion ??
        portalSnap?.fields?.objeto ??
        null,
      proveedor:
        (contract?.proveedor_adjudicado as string) ??
        integ?.nom_raz_social_contratista ??
        portalSnap?.fields?.proveedor ??
        null,
      valor,
      fecha_firma:
        ((contract?.fecha_de_firma as string) ??
          integ?.fecha_de_firma_del_contrato ??
          parsePortalFecha(portalSnap?.fields?.fecha_firma_contrato ?? portalSnap?.fields?.fecha_firma) ??
          "")
          .slice(0, 10) || null,
      estado:
        (contract?.estado_contrato as string) ??
        integ?.estado_del_proceso ??
        portalSnap?.fields?.estado ??
        null,
      modalidad:
        (contract?.modalidad_de_contratacion as string) ??
        integ?.modalidad_de_contrataci_n ??
        portalSnap?.fields?.modalidad ??
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
      verifyStatus: classifyStatus(w, contract, integ, portalSnap != null),
      data_source: dataSource,
      data_source_scraped_at: dataSourceScrapedAt,
      _raw_api: contract ? (contract as Record<string, unknown>) : null,
      _raw_integrado: integ ? (integ as Record<string, unknown>) : null,
      _raw_portal: portalSnap ? (portalSnap as Record<string, unknown>) : null,
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
      numero_contrato: (c.referencia_del_contrato as string) ?? null,
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
      data_source: "api",
      data_source_scraped_at: null,
      _raw_api: c as Record<string, unknown>,
      _raw_integrado: null,
      _raw_portal: null,
    });
  }

  return rows;
}


/**
 * Convierte un timestamp ISO a un label legible "hace X días/meses".
 * Si no parsea, devuelve null (la UI cae al label genérico).
 */
function formatAge(iso: string | null): string | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return null;
  const days = Math.floor((Date.now() - t) / 86400000);
  if (days < 0) return "hoy";
  if (days === 0) return "hoy";
  if (days === 1) return "ayer";
  if (days < 30) return `hace ${days} días`;
  const months = Math.floor(days / 30);
  if (months === 1) return "hace 1 mes";
  if (months < 12) return `hace ${months} meses`;
  const years = Math.floor(days / 365);
  return years === 1 ? "hace 1 año" : `hace ${years} años`;
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


/* ─────────────────────────────────────────────────────────────────────
 * Unified table with Excel-style per-column sort + filter.
 *
 * The Dra works in Excel daily — she expects each column header to have
 * a sort arrow and a filter dropdown with checkbox-list of values, just
 * like Excel's auto-filter. We use TanStack Table for the data engine
 * and a custom `ColumnHeader` for the popover UX.
 *
 * The cell renderers below are the SAME visual layout as before — only
 * the engine wiring (sort/filter) changed.
 * ──────────────────────────────────────────────────────────────────── */
export function UnifiedTable({
  rows,
  onPick,
  onAdd,
  onUpdate,
  onRemove,
  busy,
  totalAppearances,
  selectedIds,
  onToggleSelect,
}: {
  rows: UnifiedRow[];
  onPick: (id: string) => void;
  onAdd: (url: string) => Promise<void>;
  onUpdate: (oldUrl: string, newUrl: string) => Promise<void>;
  onRemove: (url: string) => Promise<void>;
  busy: boolean;
  totalAppearances: number;
  // Feature G (2026-04-26): seleccion granular para "refrescar los que la
  // Dra elija" en lugar de masivo. Selectable solo si el row tiene
  // notice_uid o process_id formato CO1.NTC.* (scrapeables).
  selectedIds: Set<string>;
  onToggleSelect: (uid: string) => void;
}) {
  const [addUrl, setAddUrl] = React.useState("");
  const [editingKey, setEditingKey] = React.useState<string | null>(null);
  const [editDraft, setEditDraft] = React.useState("");
  const [sorting, setSorting] = React.useState<SortingState>([]);
  const [columnFilters, setColumnFilters] = React.useState<ColumnFiltersState>(
    [],
  );

  // Each column has TWO accessors:
  //   - `accessorFn`  → what TanStack uses for sort + the default filter
  //   - `meta.filterAccessor` (optional) → what the popover lists as
  //     unique values / what the custom filterFn matches on. We use this
  //     when the SORT key differs from the FILTER key (e.g. Valor/Firma
  //     sorts numerically by valor but filters by the year of firma).
  const columns = React.useMemo<ColumnDef<UnifiedRow>[]>(
    () => [
      {
        // Feature G (2026-04-26): columna de seleccion para refrescar
        // procesos especificos sin gastar CapSolver en todos. Solo
        // habilitable para rows scrapeables (con notice_uid o process_id
        // formato NTC). REQ y PCCNTR no se pueden re-scrapear.
        id: "select",
        header: () => (
          <span className="text-[10px] text-ink-soft" title="Seleccioná procesos para refrescar">
            ✓
          </span>
        ),
        enableSorting: false,
        enableColumnFilter: false,
        cell: ({ row }) => {
          const r = row.original;
          const uid =
            r.notice_uid ??
            (r.process_id?.startsWith("CO1.NTC.") ? r.process_id : null);
          if (!uid || !r.watched) {
            return null;
          }
          const checked = selectedIds.has(uid);
          return (
            <input
              type="checkbox"
              checked={checked}
              onClick={(e) => e.stopPropagation()}
              onChange={() => onToggleSelect(uid)}
              className="rounded cursor-pointer"
              title={`Marcar ${uid} para refrescar desde el portal SECOP`}
            />
          );
        },
        size: 36,
      },
      {
        id: "contrato",
        header: "Contrato",
        accessorFn: (r) =>
          r.numero_contrato ?? r.id_contrato ?? r.process_id ?? "",
        cell: ({ row }) => {
          const r = row.original;
          const vigencia =
            r.vigencias.join(", ") ||
            (r.fecha_firma ? r.fecha_firma.slice(0, 4) : null);
          return (
            <div className="font-mono text-[11px]">
              {vigencia && (
                <span className="inline-flex items-center px-1.5 py-0.5 rounded bg-burgundy/10 text-burgundy mb-1 text-[10px]">
                  {vigencia}
                </span>
              )}
              <button
                onClick={() =>
                  onPick(r.id_contrato ?? r.process_id ?? r.key)
                }
                className="block text-burgundy hover:underline text-left break-all"
              >
                {r.numero_contrato ?? r.id_contrato ?? r.process_id ?? "—"}
              </button>
              {r.numero_contrato && (r.id_contrato ?? r.process_id) && (
                <span className="block text-[10px] text-ink-soft mt-0.5 break-all">
                  {r.id_contrato ?? r.process_id}
                </span>
              )}
              {r.notice_uid && (
                <span className="block text-[10px] text-ink-soft/70 mt-0.5 break-all">
                  {r.notice_uid}
                </span>
              )}
              {r.appearances_count > 1 && (
                <span className="block text-[10px] text-ink-soft italic mt-0.5">
                  {r.appearances_count} apariciones
                </span>
              )}
            </div>
          );
        },
        size: 200,
      },
      {
        id: "objeto",
        header: "Objeto / Proveedor",
        accessorFn: (r) => r.proveedor ?? r.objeto ?? "",
        meta: {
          filterAccessor: (r: UnifiedRow) => r.proveedor ?? "",
        },
        cell: ({ row }) => {
          const r = row.original;
          return (
            <div className="text-xs">
              <div className="text-ink line-clamp-3">
                {r.objeto ?? (
                  <span className="text-ink-soft italic">
                    (sin contrato firmado)
                  </span>
                )}
              </div>
              {r.proveedor && (
                <div className="text-[11px] text-ink-soft mt-1 truncate">
                  {r.proveedor}
                </div>
              )}
            </div>
          );
        },
      },
      {
        id: "valor",
        header: "Valor / Firma",
        accessorFn: (r) => r.valor ?? 0,
        sortingFn: (a, b) => (a.original.valor ?? 0) - (b.original.valor ?? 0),
        meta: {
          // Filter "Valor/Firma" by the YEAR of fecha_firma — much more
          // useful than filtering by exact value.
          filterAccessor: (r: UnifiedRow) =>
            r.fecha_firma ? r.fecha_firma.slice(0, 4) : "",
        },
        filterFn: (row, _id, fv) => {
          const year = row.original.fecha_firma?.slice(0, 4) ?? "";
          return matchFilter(fv as FilterVal, year);
        },
        cell: ({ row }) => {
          const r = row.original;
          return (
            <div className="text-right">
              <div className="font-mono text-xs text-ink">
                {r.valor != null ? moneyCO.format(r.valor) : "—"}
              </div>
              <div className="font-mono text-[10px] text-ink-soft mt-0.5">
                {r.fecha_firma ?? "—"}
              </div>
            </div>
          );
        },
        size: 140,
      },
      {
        id: "estado",
        header: "Estado",
        accessorFn: (r) => r.estado ?? "",
        cell: ({ row }) => {
          const r = row.original;
          return (
            <div className="text-xs">
              {r.estado ? (
                <span className="inline-flex items-center px-1.5 py-0.5 rounded bg-stone-100 text-ink whitespace-nowrap text-[10px]">
                  {r.estado}
                </span>
              ) : (
                <span className="text-ink-soft/50 text-[10px]">—</span>
              )}
              {r.liquidado && (
                <div className="text-[10px] text-ink-soft italic mt-1">
                  Liquidado
                </div>
              )}
            </div>
          );
        },
        size: 130,
      },
      {
        id: "modificatorios",
        header: "Modificatorios",
        accessorFn: (r) => {
          const isMod =
            /modific/i.test(r.estado ?? "") ||
            (r.dias_adicionados != null && r.dias_adicionados > 0);
          return isMod ? "Modificado" : "Sin modificatorios";
        },
        cell: ({ row }) => {
          const r = row.original;
          const isMod =
            /modific/i.test(r.estado ?? "") ||
            (r.dias_adicionados != null && r.dias_adicionados > 0);
          return (
            <div className="text-[11px]">
              {isMod ? (
                <div>
                  <span className="inline-flex items-center px-1.5 py-0.5 rounded bg-amber-50 text-amber-800 border border-amber-200 text-[10px] whitespace-nowrap">
                    Modificado
                  </span>
                  {r.dias_adicionados && r.dias_adicionados > 0 && (
                    <span className="block font-mono text-[10px] text-ink-soft mt-1">
                      +{r.dias_adicionados} días
                    </span>
                  )}
                </div>
              ) : (
                <span className="text-ink-soft/50 text-[10px]">
                  Sin modificatorios
                </span>
              )}
              {r.notas && (
                <div className="text-[10px] text-ink-soft italic mt-1 line-clamp-2">
                  {r.notas}
                </div>
              )}
            </div>
          );
        },
        size: 170,
      },
      {
        id: "origen",
        header: "Origen",
        accessorFn: (r) => r.verifyStatus,
        meta: {
          // Show human-friendly labels in the filter list.
          filterAccessor: (r: UnifiedRow) => statusLabel(r.verifyStatus),
        },
        filterFn: (row, _id, fv) =>
          matchFilter(fv as FilterVal, statusLabel(row.original.verifyStatus)),
        cell: ({ row }) => {
          const r = row.original;
          return (
            <div className="text-[10px]">
              <StatusBadge status={r.verifyStatus} />
              {r.data_source === "integrado" && (
                <div
                  className="mt-1 inline-flex items-center px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200 text-[9px] font-medium"
                  title="Datos del dataset SECOP Integrado (rpmr-utcd) — fuente pública sin captcha. La API estándar (p6dx-8zbt/jbjy-vk9h) no expone este proceso."
                >
                  vía Integrado
                </div>
              )}
              {r.data_source === "portal" && (() => {
                const age = formatAge(r.data_source_scraped_at);
                const fechaCorta =
                  r.data_source_scraped_at?.slice(0, 10) ?? null;
                const tooltip = r.data_source_scraped_at
                  ? `Cache del portal community.secop.gov.co — leído ${fechaCorta} (${age ?? "fecha desconocida"}). Se refresca con el cron mensual o con "Refrescar seleccionados" cuando lo necesités.`
                  : "Datos del cache estático del portal community.secop.gov.co. Se actualiza con un scrape periódico (no en vivo).";
                return (
                  <>
                    <div
                      className="mt-1 inline-flex items-center px-1.5 py-0.5 rounded bg-amber-50 text-amber-800 border border-amber-200 text-[9px] font-medium"
                      title={tooltip}
                    >
                      vía portal cache{age ? ` · ${age}` : ""}
                    </div>
                    {/* Feature G (2026-04-26): fecha exacta del ultimo
                        scrape VISIBLE (no en tooltip). La Dra ve cuando
                        cada celda fue actualizada por ultima vez sin
                        tener que pasar el mouse encima. */}
                    {fechaCorta && (
                      <div className="text-[9px] text-ink-soft mt-0.5 font-mono">
                        Actualizado: {fechaCorta}
                      </div>
                    )}
                  </>
                );
              })()}
              <div className="text-ink-soft mt-1 truncate">
                {r.sheets.length > 0 ? (
                  r.sheets.join(", ")
                ) : (
                  <span className="italic">solo SECOP</span>
                )}
              </div>
            </div>
          );
        },
        size: 150,
      },
      {
        id: "acciones",
        header: "Acciones",
        enableSorting: false,
        enableColumnFilter: false,
        cell: ({ row }) => {
          const r = row.original;
          const isEditing = editingKey === r.key;
          if (isEditing) {
            return (
              <div className="flex items-center justify-end gap-1">
                <Input
                  autoFocus
                  value={editDraft}
                  onChange={(e) => setEditDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Escape") setEditingKey(null);
                    if (
                      e.key === "Enter" &&
                      editDraft.trim() &&
                      r.watch_url
                    ) {
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
            );
          }
          return (
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
                    onClick={() => r.watch_url && onRemove(r.watch_url)}
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
          );
        },
        size: 220,
      },
    ],
    [editingKey, editDraft, busy, onPick, onUpdate, onRemove],
  );

  const table = useReactTable({
    data: rows,
    columns,
    state: { sorting, columnFilters },
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    enableColumnFilters: true,
    defaultColumn: {
      filterFn: (row, colId, filterValue) =>
        matchFilter(
          filterValue as FilterVal,
          String(row.getValue(colId) ?? ""),
        ),
    },
  });

  // Build the unique-values list per column from each column's
  // filterAccessor (or accessorFn fallback). Capped at 200 distinct
  // values per column so the popover stays performant.
  const uniqueValuesByCol = React.useMemo(() => {
    const m: Record<string, string[]> = {};
    for (const c of columns) {
      const id = c.id;
      if (!id) continue;
      const colMeta = c.meta as
        | { filterAccessor?: (r: UnifiedRow) => string }
        | undefined;
      const accessor =
        colMeta?.filterAccessor ??
        (("accessorFn" in c &&
          typeof (c as { accessorFn?: unknown }).accessorFn === "function"
          ? (r: UnifiedRow) =>
              String(
                (
                  c as {
                    accessorFn: (r: UnifiedRow, i: number) => unknown;
                  }
                ).accessorFn(r, 0) ?? "",
              )
          : () => ""));
      const set = new Set<string>();
      for (const r of rows) {
        const v = String(accessor(r) ?? "").trim();
        if (v && v !== "—" && v !== "0") set.add(v);
        if (set.size > 200) break;
      }
      m[id] = Array.from(set).sort();
    }
    return m;
  }, [rows, columns]);

  const hasActiveTableFilters =
    columnFilters.length > 0 || sorting.length > 0;

  function resetFormat() {
    setSorting([]);
    setColumnFilters([]);
  }

  const visibleCount = table.getRowModel().rows.length;

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
            onClick={() =>
              addUrl.trim() && onAdd(addUrl.trim()).then(() => setAddUrl(""))
            }
            disabled={busy || !addUrl.trim()}
            className="gap-2"
          >
            <Plus className="h-4 w-4" />
            Agregar
          </Button>
        </div>
      </div>

      {hasActiveTableFilters && (
        <div className="flex items-center justify-between px-4 py-2 bg-amber-50 border-b border-amber-200 text-xs">
          <span className="text-amber-800">
            <Filter className="h-3 w-3 inline mr-1" />
            Tabla con filtros u ordenamiento personalizado en columnas
          </span>
          <button
            onClick={resetFormat}
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-amber-600 text-white hover:bg-amber-700 text-xs font-medium"
          >
            <RotateCcw className="h-3 w-3" />
            Restablecer formato
          </button>
        </div>
      )}

      {rows.length === 0 ? (
        <div className="px-5 py-12 text-center text-xs text-ink-soft italic">
          No hay procesos que coincidan con los filtros.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-background text-[11px] uppercase tracking-wider text-ink-soft">
              {table.getHeaderGroups().map((hg) => (
                <tr key={hg.id}>
                  {hg.headers.map((h) => (
                    <th
                      key={h.id}
                      style={{ width: h.column.columnDef.size }}
                      className="text-left px-3 py-2 align-top"
                    >
                      {h.isPlaceholder ? null : (
                        <ColumnHeader
                          title={String(h.column.columnDef.header)}
                          column={h.column}
                          uniqueValues={
                            uniqueValuesByCol[h.column.id] ?? []
                          }
                        />
                      )}
                    </th>
                  ))}
                </tr>
              ))}
            </thead>
            <tbody>
              {visibleCount === 0 ? (
                <tr>
                  <td
                    colSpan={columns.length}
                    className="text-center p-12 text-ink-soft italic"
                  >
                    Sin resultados con los filtros actuales.
                  </td>
                </tr>
              ) : (
                table.getRowModel().rows.map((row) => (
                  <tr
                    key={row.id}
                    className="border-t border-rule/60 hover:bg-background align-top"
                  >
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id} className="px-3 py-2 align-top">
                        {flexRender(
                          cell.column.columnDef.cell,
                          cell.getContext(),
                        )}
                      </td>
                    ))}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      <div className="px-4 py-2.5 text-xs text-ink-soft border-t border-rule bg-background">
        {visibleCount} de {rows.length} procesos · click cualquier fila para
        ver detalle completo
      </div>
    </div>
  );
}


/** Human-friendly label for a verifyStatus — used by the Origen column
 *  filter so the popover lists "Contrato firmado" instead of the raw
 *  enum value "contrato_firmado". */
function statusLabel(s: UnifiedRow["verifyStatus"]): string {
  switch (s) {
    case "contrato_firmado": return "Contrato firmado";
    case "verificado":       return "Proceso verificado";
    case "borrador":         return "Borrador SECOP";
    case "no_en_api":        return "No en API público";
  }
}


/** Excel-style filter header for one column.
 *
 * - Click on the title → toggle sort asc/desc/none
 * - Click on the funnel icon → opens a popover with:
 *   - Search box
 *   - Checkbox list of unique values (multi-select)
 *   - Limpiar button
 *
 * The popover closes on outside-click thanks to Radix Popover, so the
 * Dra doesn't have to chase a stuck dropdown. */
function ColumnHeader({
  title,
  column,
  uniqueValues,
}: {
  title: string;
  column: Column<UnifiedRow, unknown>;
  uniqueValues: string[];
}) {
  const filterValue = column.getFilterValue() as FilterVal | undefined;
  const isActive =
    !!filterValue &&
    ((filterValue.kind === "set" && filterValue.values.length > 0) ||
      (filterValue.kind === "text" && filterValue.q.length > 0));
  const sort = column.getIsSorted();
  const canFilter = column.getCanFilter();
  const canSort = column.getCanSort();

  const [search, setSearch] = React.useState("");
  const selected = filterValue?.kind === "set" ? filterValue.values : [];

  const filteredValues = uniqueValues.filter((v) =>
    v.toLowerCase().includes(search.toLowerCase()),
  );

  function toggleValue(v: string) {
    const cur = filterValue?.kind === "set" ? filterValue.values : [];
    const next = cur.includes(v) ? cur.filter((x) => x !== v) : [...cur, v];
    column.setFilterValue({ kind: "set", values: next });
  }

  function selectAll() {
    column.setFilterValue({ kind: "set", values: filteredValues });
  }

  function clearAll() {
    column.setFilterValue(undefined);
    setSearch("");
  }

  return (
    <div className="flex items-center gap-1 group">
      {canSort ? (
        <button
          onClick={() => column.toggleSorting(sort === "asc")}
          className="inline-flex items-center gap-1 hover:text-ink"
          title="Ordenar"
        >
          {title}
          {sort === "asc" ? (
            <ArrowUp className="h-3 w-3 opacity-90" />
          ) : sort === "desc" ? (
            <ArrowDown className="h-3 w-3 opacity-90" />
          ) : (
            <ArrowUpDown className="h-3 w-3 opacity-60" />
          )}
        </button>
      ) : (
        <span>{title}</span>
      )}
      {canFilter && (
        <Popover>
          <PopoverTrigger asChild>
            <button
              className={cn(
                "inline-flex items-center justify-center h-5 w-5 rounded transition-colors",
                isActive
                  ? "bg-burgundy/15 text-burgundy ring-1 ring-burgundy/30"
                  : "text-ink-soft hover:bg-stone-200 hover:text-ink",
              )}
              title="Filtrar columna (estilo Excel)"
            >
              <Filter className="h-3.5 w-3.5" />
            </button>
          </PopoverTrigger>
          <PopoverContent className="w-72 p-3">
            <Input
              placeholder="Buscar valor…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="h-8 text-xs"
            />
            <div className="flex items-center justify-between mt-2 mb-1 px-1">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-ink-soft">
                {filteredValues.length} valores
              </span>
              <button
                onClick={selectAll}
                className="text-[11px] uppercase tracking-wider text-burgundy hover:underline"
              >
                Seleccionar todos
              </button>
            </div>
            <div className="max-h-64 overflow-y-auto border border-rule rounded">
              {filteredValues.length === 0 ? (
                <div className="px-3 py-6 text-xs italic text-ink-soft text-center">
                  Sin valores
                </div>
              ) : (
                filteredValues.map((v) => (
                  <label
                    key={v}
                    className="flex items-center gap-2 px-2 py-1.5 hover:bg-surface cursor-pointer text-xs"
                  >
                    <Checkbox
                      checked={selected.includes(v)}
                      onCheckedChange={() => toggleValue(v)}
                    />
                    <span className="truncate text-ink">{v}</span>
                  </label>
                ))
              )}
            </div>
            <div className="flex justify-between mt-3 pt-2 border-t border-rule">
              <Button variant="ghost" size="sm" onClick={clearAll}>
                Limpiar
              </Button>
              <span className="text-[10px] text-ink-soft self-center">
                {selected.length} seleccionados
              </span>
            </div>
          </PopoverContent>
        </Popover>
      )}
    </div>
  );
}
