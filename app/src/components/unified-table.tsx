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
import {
  classifyDocs,
  summarizeModificatorios,
  type ClassifiedModificatorio,
} from "@/lib/classify-modificatorios";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
  /** Consecutivo primario para mostrar en la celda principal de la
   *  tabla. Cardinal: prioridad Excel > portal SECOP. Cuando Excel
   *  trae N contratos, se muestra el primero acá y la lista completa
   *  vive en `numero_contratos_excel` para el modal. */
  numero_contrato: string | null;  // CONTRATO-FEAB-NNNN-AAAA
  /** Lista completa de consecutivos FEAB del Excel asociados a este
   *  proceso (modelo 1↔N · una URL puede tener hasta 13 contratos
   *  cuando una subasta tuvo múltiples adjudicaciones). Se renderiza
   *  en el modal en sección "Contratos FEAB asociados". Vacío para
   *  procesos sin contrato firmado todavía. */
  numero_contratos_excel: string[];
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
  // CARDINAL PURO (Sergio 2026-04-27): modificatorios detectados como
  // documentos PDF en el portal scrape (patrón "Modificatorio|Otrosí|Adendo").
  // Es cardinal puro real: viene del scrape del link community.secop.
  modificatorios_count: number;
  modificatorios_docs: { name: string; url: string }[];
  /** Modificatorios clasificados por tipo y número (Sergio 2026-04-28).
   *  Cada entrada tiene `tipo` (Adición · Prórroga · Cesión · etc.),
   *  `numero` (extraído del nombre del PDF si aparece) y el link.
   *  TODO sesión OCR: agregar `valor_adicionado`, `dias_prorrogados`,
   *  `fecha_documento` extraídos del contenido del PDF. */
  modificatorios_classified: ClassifiedModificatorio[];
  modificatorios_summary: string;

  // From watch list (if present)
  sheets: string[];
  vigencias: string[];
  appearances: WatchedAppearance[];
  appearances_count: number;
  watched: boolean;
  watch_url: string | null;

  // Verify status taxonomy (derived)
  verifyStatus:
    | "verificado"
    | "contrato_firmado"
    | "contrato_interno"
    | "borrador"
    | "no_en_api";

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

  // Discrepancias detectadas entre fuentes del SECOP — cardinal:
  // cuando rpmr-utcd dice "valor=481" pero el portal dice "valor=890.400"
  // para el mismo contrato, hay un drift INTERNO del SECOP. La UI alerta
  // a la Dra para que NO confíe ciegamente en el dato de la cascada y
  // verifique vs el portal. Generado por scripts/cross_check_fuentes.py.
  discrepancias: Array<{
    campo: string;
    fuente_a: string;
    valor_a: string | number | null;
    fuente_b: string;
    valor_b: string | number | null;
    diff_pct?: number;
  }>;
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
 * CARDINAL PURO (Sergio 2026-04-27): un link = una fila visible.
 *
 * Antes esta función expandía cada proceso a N filas si aparecía N veces
 * en el Excel (ej. CO1.NTC.6343203 aparecía 13 veces idéntica porque la
 * Dra registró 13 sub-rodantes de la misma subasta). Era ruido visual
 * puro: 13 filas con datos del SECOP IDÉNTICOS · cardinal violation
 * porque el LINK es uno solo.
 *
 * Ahora: filtramos por hoja PERO NUNCA duplicamos filas. El conteo de
 * apariciones en el Excel se preserva como `appearances_count` (visible
 * en el modal · "Apariciones en tu Excel: 13"). Cardinal honesto.
 */
export function expandRowsByAppearance(
  rows: UnifiedRow[],
  selectedSheets: string[],
): UnifiedRow[] {
  if (selectedSheets.length === 0) return rows;
  return rows.filter((r) => {
    if (!r.watched || r.appearances.length === 0) {
      // Orphan o sin appearances: incluir si alguna de sus hojas matchea
      // o si no tiene hoja (manual add)
      return r.sheets.some((s) => selectedSheets.includes(s)) || r.sheets.length === 0;
    }
    // Watched row: incluir si tiene al menos una appearance en las hojas
    // seleccionadas. UNA fila por proceso · NO N filas por aparición.
    return r.appearances.some((a) => selectedSheets.includes(a.sheet));
  });
}


function classifyStatus(
  watch: WatchedItem | null,
  _contract: Contract | null,
  _integ: IntegradoSummary | null = null,
  hasPortalSnapshot: boolean = false,
): UnifiedRow["verifyStatus"] {
  // CARDINAL PURA (Sergio 2026-04-27): "verdad absoluta = links y punto"
  // La clasificación NO depende de jbjy/rpmr (mienten · 33 procs >50% drift).
  // Solo del URL del link y del scrape del portal community.secop.
  //
  // 1. URL apunta a portal interno SECOP II (Contracts Management) →
  //    requiere login institucional, no scrapeable públicamente.
  if (watch?.url?.includes("CO1ContractsManagement")) {
    return "contrato_interno";
  }
  // 2. Scrape del portal community.secop tiene snapshot → verificable
  //    cardinal contra el link mismo de la Dra.
  if (hasPortalSnapshot) return "verificado";
  // 3. process_id es workspace ID (REQ/BDOS) → borrador en preparación.
  const pid = watch?.process_id ?? "";
  if (pid.startsWith("CO1.REQ.") || pid.startsWith("CO1.BDOS.")) {
    return "borrador";
  }
  // 4. Sin nada público que el sistema pueda leer → "—" honesto.
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
  discrepanciasBulk?: import("@/lib/api").DiscrepanciasBulk | null,
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

    // CASCADA CARDINAL PURA (Sergio 2026-04-27 · 4 confirmaciones):
    //   "es que la verdad absoluta son los links y punto"
    //   "lo principal es que la Dra Camila confíe en la app porque
    //    ella usa esos links y lo hace a mano"
    //   "haz lo que sea mejor ya conoces reglas y todo"
    //
    // Solo el scrape del link community.secop cuenta como verdad.
    // jbjy-vk9h y rpmr-utcd son fuentes derivadas que MIENTEN:
    //   - rpmr roto: 33 procs >50% drift de valor (caso máx: rpmr=$361
    //     cuando real es $345.242.994). 119 fechas posteriores +11.8 días.
    //   - jbjy va a portal interno SECOP II que requiere login (no es
    //     espejo del link de la Dra · solo verificable manualmente).
    //
    // Por eso `contract` e `integ` se siguen calculando para las
    // discrepancias internas y _raw_*, PERO los CAMPOS VISIBLES de
    // la fila (objeto, valor, proveedor, etc.) vienen ÚNICAMENTE del
    // portalSnap. Si no hay portalSnap → "—" honesto.
    //
    // Memoria: feedback_dashboard_es_scraper_de_links.md
    const integ = lookupIntegrado(w.notice_uid, w.process_id);
    let portalSnap: PortalBulk[string] | null = null;
    if (portalBulk) {
      const key1 = w.notice_uid ?? "";
      const key2 = w.process_id ?? "";
      portalSnap = portalBulk[key1] ?? portalBulk[key2] ?? null;
    }
    // Cascada cardinal pura: solo portal o nada.
    const dataSource: UnifiedRow["data_source"] = portalSnap ? "portal" : null;
    const dataSourceScrapedAt =
      dataSource === "portal" ? portalSnap?.scraped_at ?? null : null;

    // Discrepancias detectadas para este proceso · vienen del cross_check_fuentes.py
    const discrepKey = w.notice_uid ?? w.process_id ?? "";
    const discrepancias = discrepanciasBulk?.by_process_id?.[discrepKey] ?? [];

    // CARDINAL PURO REAL (Sergio 2026-04-27): los modificatorios viven en
    // el portal community.secop como PDFs adjuntos en la sección
    // "Documentos del proceso" con nombres tipo "Modificatorio N° X
    // Contrato N° Y de YYYY.pdf". El scraper YA los extrae como documents.
    // Detectarlos cardinal puro = filtrar documents por patrón.
    // Memoria: project_porque_fundador.md, feedback_dashboard_es_scraper_de_links.md
    const portalDocs = portalSnap?.documents ?? [];
    // CARDINAL (2026-04-28 · Sergio): clasificación con 11 tipos +
    // anti-FP (cobertura del 70 % vs 15 % del regex anterior). El campo
    // `modificatoriosDocs` se mantiene legacy para `modificatorios_docs`
    // que algunos componentes consumen (modal, export Excel).
    const modificatoriosClassified = classifyDocs(portalDocs);
    const modificatoriosSummary = summarizeModificatorios(modificatoriosClassified);
    const modificatoriosDocs = modificatoriosClassified.map((c) => ({
      name: c.nombre,
      url: c.url,
    }));
    // dias_adicionados ya no se calcula (jbjy es ruido) · sí contamos
    // modificatorios reales del link. Mantengo dias=null por compat con
    // export-excel que tiene una columna para eso.
    const dias = null;
    // Liquidado: solo si el portal scrape lo dice explícitamente
    const liq =
      String(portalSnap?.fields?.liquidacion ?? "").trim().toLowerCase() === "si";

    // Valor: SOLO del portal scrape. Si el portal no tiene valor → null
    // → la celda muestra "—" honesto. NO fallback a jbjy ni rpmr.
    let valor: number | null = null;
    if (portalSnap?.fields?.valor_total) {
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
      // CARDINAL PURO: TODOS los campos visibles vienen ÚNICAMENTE del
      // portalSnap (scrape del link community.secop). Si el portal no
      // tiene el campo → null → la celda muestra "—" honesto.
      // jbjy/rpmr NO se usan para campos visibles.
      key: w.url ?? `${w.process_id ?? "noid"}-${rows.length}`,
      process_id: w.process_id,
      id_contrato: null,
      notice_uid: w.notice_uid ?? null,
      // CARDINAL (2026-04-28 · Sergio corrige): preservar los dos
      // consecutivos como campos separados. NO unificar.
      //   - `numero_contrato`        → identificador que la entidad
      //     subió al portal SECOP (texto libre del scrape · ej.
      //     "FEAB 0001 DE 2024" / "CPM-0001-2025"). Sale del scrape.
      //   - `numero_contratos_excel` → consecutivo FEAB formal del
      //     Excel de la Dra (`CONTRATO-FEAB-NNNN-AAAA`). Lista por
      //     modelo 1↔N. Sale del Excel.
      // Ambos son legítimos · el modal y la tabla muestran cada uno
      // con su etiqueta para que la Dra vea las dos vistas del mismo
      // contrato sin que una oculte a la otra.
      numero_contrato:
        portalSnap?.fields?.numero_contrato ??
        portalSnap?.fields?.numero_proceso ??
        null,
      numero_contratos_excel: w.numero_contrato_excel ?? [],
      url: w.url,
      objeto:
        portalSnap?.fields?.descripcion ??
        portalSnap?.fields?.objeto ??
        null,
      proveedor: portalSnap?.fields?.proveedor ?? null,
      valor,
      fecha_firma:
        (parsePortalFecha(
          portalSnap?.fields?.fecha_firma_contrato ??
            portalSnap?.fields?.fecha_firma,
        ) ?? "").slice(0, 10) || null,
      estado: portalSnap?.fields?.estado ?? null,
      // CARDINAL PURO: el portal scrape NO devuelve "modalidad" (campo de
      // jbjy/rpmr). Sí devuelve tipo_contrato (Compraventa, Prestación de
      // servicios, Otro, Lease Furniture, Obra, Suministros) que es el
      // valor útil para Cami filtrar como "Tipo de contratación".
      modalidad: portalSnap?.fields?.tipo_contrato ?? null,
      notas,
      dias_adicionados: dias,
      liquidado: liq,
      modificatorios_count: modificatoriosClassified.length,
      modificatorios_docs: modificatoriosDocs.map((d) => ({
        name: d.name ?? "",
        url: d.url ?? "",
      })),
      modificatorios_classified: modificatoriosClassified,
      modificatorios_summary: modificatoriosSummary,
      sheets: w.sheets ?? [],
      vigencias: w.vigencias ?? [],
      appearances: w.appearances ?? [],
      appearances_count: w.appearances?.length ?? 0,
      watched: true,
      watch_url: w.url,
      verifyStatus: classifyStatus(w, null, null, portalSnap != null),
      data_source: dataSource,
      data_source_scraped_at: dataSourceScrapedAt,
      // CARDINAL PURO: jbjy/rpmr no se exponen en el modelo. Solo el portal
      // scrape. Si después necesitamos auditoría forense de qué dice cada
      // fuente, esos reportes se generan con scripts/cross_check_fuentes.py
      // (CI/local) — NO desde la UI de la Dra.
      _raw_api: null,
      _raw_integrado: null,
      _raw_portal: portalSnap ? (portalSnap as Record<string, unknown>) : null,
      discrepancias: [],
    });
    // contract / integ se mantienen como variables locales arriba para no
    // romper la firma de la función ni los lookups (futura limpieza en
    // sesión dedicada eliminará también estos cómputos · ahora preferimos
    // patch quirúrgico de bajo riesgo).
    void contract;
    void integ;
  }

  // Cardinal puro: NO agregamos huérfanos del SECOP API (contratos del FEAB
  // que no están en el watch list de la Dra). El watch list ES la verdad
  // operacional · todo lo demás es ruido. Ver memoria
  // `feedback_dashboard_es_scraper_de_links.md`.
  void usedContracts;

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
      title:
        "Este proceso ya tiene contrato firmado y publicado en SECOP. Tenés todos los datos: " +
        "valor, proveedor, fechas, etc.",
    },
    verificado: {
      label: "Publicado en SECOP",
      cls: "bg-sky-50 text-sky-700 border-sky-200",
      title:
        "Este proceso está publicado en SECOP (con su código oficial NTC). Tiene los datos del " +
        "proceso aunque puede que aún no tenga contrato firmado.",
    },
    contrato_interno: {
      label: "Verificable solo con tu login",
      cls: "bg-violet-50 text-violet-700 border-violet-200",
      title:
        "El link de este proceso va al portal interno SECOP II que requiere tu login " +
        "institucional. El sistema no puede leerlo automáticamente. Click en \"Abrir\" " +
        "y verificá los datos con tu sesión.",
    },
    borrador: {
      label: "Borrador (no publicado)",
      cls: "bg-amber-50 text-amber-700 border-amber-200",
      title:
        "Este proceso está en preparación dentro de SECOP — todavía no se publicó. " +
        "Cuando se publique, el sistema lo detecta solo y trae sus datos.",
    },
    no_en_api: {
      label: "Aún sin publicar",
      cls: "bg-rose-50 text-rose-700 border-rose-200",
      title:
        "Este proceso todavía no aparece publicado en SECOP. Puede ser un borrador en preparación, " +
        "un proceso cancelado, o uno en limbo. Click en \"Abrir\" para verlo manualmente en SECOP.",
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
  onUpdate: (
    oldUrl: string,
    patch: {
      newUrl?: string;
      note?: string | null;
      numero_contrato_excel?: string[];
      vigencias?: string[];
      sheets?: string[];
    },
  ) => Promise<void>;
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
  // Editor expandido (2026-04-28 · Sergio): la Dra abre un dialog para
  // corregir URL, consecutivos FEAB, vigencias y períodos. Todo desde
  // una sola pantalla · sus cambios se persisten en IndexedDB y sobreviven
  // al re-seed (merge inteligente en `ensureSeed`).
  const [editingRow, setEditingRow] = React.useState<UnifiedRow | null>(null);
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
        // Feature G (2026-04-26 r2): columna Contrato ahora incluye el
        // checkbox de seleccion a la izquierda — eliminamos columna "Sel."
        // separada para evitar scroll lateral (regla cardinal "max 6-8
        // columnas" del CLAUDE.md). El checkbox solo se renderiza para
        // procesos scrapeables (con notice_uid o process_id formato NTC).
        id: "contrato",
        header: "Contrato",
        // CARDINAL (2026-04-28) · sortable por consecutivo FEAB del Excel
        // primero (lo que la Dra usa para hablar de sus contratos), con
        // fallback al numero_contrato del portal y luego process_id.
        accessorFn: (r) =>
          r.numero_contratos_excel?.[0] ??
          r.numero_contrato ??
          r.id_contrato ??
          r.process_id ??
          "",
        cell: ({ row }) => {
          const r = row.original;
          const vigencia =
            r.vigencias.join(", ") ||
            (r.fecha_firma ? r.fecha_firma.slice(0, 4) : null);
          const uid =
            r.notice_uid ??
            (r.process_id?.startsWith("CO1.NTC.") ? r.process_id : null);
          const isScrapeable = !!uid && r.watched;
          // CARDINAL (2026-04-28 · Sergio "preserva los dos") · dos
          // consecutivos distintos coexisten:
          //   1. consecFeabExcel · `CONTRATO-FEAB-NNNN-AAAA` del Excel
          //      (ID interno formal del FEAB · lo que dice la Dra).
          //   2. numero_contrato  · texto libre del portal SECOP (lo
          //      que la entidad escribió al subir, ej. "FEAB 0001 DE
          //      2024", "CPM-0001-2025", etc.).
          // Verificación 2026-04-28: el portal trae el consecutivo
          // FEAB en `numero_proceso` solo en 33 % match exacto + 25 %
          // loose · 42 % no lo trae. Por eso preservamos ambos.
          const consecsExcel = r.numero_contratos_excel ?? [];
          const consecPrimaryExcel = consecsExcel[0] ?? null;
          const moreExcel = consecsExcel.length - 1;
          // Solo mostrar la línea del portal si difiere del Excel para
          // no duplicar (cuando coinciden, mostrar uno solo basta).
          const showPortalLine =
            r.numero_contrato &&
            consecPrimaryExcel &&
            r.numero_contrato.replace(/[\s-]/g, "").toLowerCase() !==
              consecPrimaryExcel.replace(/[\s-]/g, "").toLowerCase();
          // Fallback cuando no hay consecutivo Excel: usa portal o IDs.
          const primaryLine =
            consecPrimaryExcel ?? r.numero_contrato ?? r.id_contrato ??
            r.process_id ?? "—";
          return (
            <div className="flex items-start gap-2 font-mono text-[11px]">
              {/* Checkbox a la izquierda · solo para procesos scrapeables.
                  Spacer del mismo ancho cuando no aplica para alinear filas. */}
              {isScrapeable ? (
                <input
                  type="checkbox"
                  checked={selectedIds.has(uid!)}
                  onClick={(e) => e.stopPropagation()}
                  onChange={() => onToggleSelect(uid!)}
                  className="rounded cursor-pointer mt-1 shrink-0"
                  title={`Marcar ${uid} para refrescar desde el portal SECOP`}
                />
              ) : (
                <span className="w-4 mt-1 shrink-0" aria-hidden="true" />
              )}
              <div className="flex-1 min-w-0">
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
                  title={
                    consecPrimaryExcel
                      ? "Consecutivo FEAB del Excel de la Dra"
                      : "Identificador del proceso"
                  }
                >
                  {primaryLine}
                  {moreExcel > 0 && (
                    <span
                      className="ml-1 inline-flex items-center px-1 py-0.5 rounded bg-burgundy/10 text-burgundy text-[10px] font-sans"
                      title={`Este proceso tiene ${consecsExcel.length} contratos FEAB asociados: ${consecsExcel.join(", ")}`}
                    >
                      +{moreExcel}
                    </span>
                  )}
                </button>
                {/* Línea 2: numero_contrato del portal SECOP (si difiere
                    del consecutivo del Excel) — distinto al Excel y útil
                    para detectar discrepancias. */}
                {showPortalLine && (
                  <span
                    className="block text-[10px] text-ink-soft mt-0.5 break-all"
                    title="Número del contrato según el portal SECOP (texto que escribió la entidad)"
                  >
                    En portal: {r.numero_contrato}
                  </span>
                )}
                {/* Línea 3: process_id / id_contrato técnicos. */}
                {(r.id_contrato ?? r.process_id) && (
                  <span className="block text-[10px] text-ink-soft/70 mt-0.5 break-all">
                    {r.id_contrato ?? r.process_id}
                  </span>
                )}
                {r.notice_uid && r.notice_uid !== r.process_id && (
                  <span className="block text-[10px] text-ink-soft/70 mt-0.5 break-all">
                    {r.notice_uid}
                  </span>
                )}
                {r.appearances_count > 1 && (
                  <span
                    className="inline-flex items-center px-1.5 py-0.5 rounded bg-stone-100 text-ink-soft border border-rule text-[10px] mt-0.5"
                    title={`Este proceso aparece ${r.appearances_count} veces en tu Excel (sub-items de la misma subasta o contrato). El link del SECOP es uno solo · click para ver detalle de las apariciones.`}
                  >
                    {r.appearances_count} apariciones en tu Excel
                  </span>
                )}
              </div>
            </div>
          );
        },
        size: 220,
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
                    (contrato aún no firmado)
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
          // Cardinal r5 (2026-04-27): si hay drift detectado entre fuentes
          // del SECOP en este campo, mostrar el valor TACHADO visualmente.
          // La Dra lo ve pero sabe que NO confiar y verificar en el link.
          const driftValor = r.discrepancias?.some(d => d.campo === "valor_del_contrato");
          const driftFecha = r.discrepancias?.some(d => d.campo === "fecha_de_firma");
          return (
            <div className="text-right">
              <div
                className={cn(
                  "font-mono text-xs text-ink",
                  driftValor && "line-through decoration-rose-600 decoration-2 text-rose-700",
                )}
                title={driftValor
                  ? "🚨 Drift detectado: el SECOP Integrado y el portal reportan valores distintos para este contrato. Click la fila → modal → ver tabla de discrepancias. Verificá en el link antes de confiar."
                  : undefined
                }
              >
                {r.valor != null ? moneyCO.format(r.valor) : "—"}
              </div>
              <div
                className={cn(
                  "font-mono text-[10px] text-ink-soft mt-0.5",
                  driftFecha && "line-through decoration-rose-500 text-rose-600",
                )}
                title={driftFecha
                  ? "🚨 Drift detectado en fecha de firma · verificá en el link"
                  : undefined
                }
              >
                {r.fecha_firma ?? "—"}
              </div>
            </div>
          );
        },
        size: 115,
      },
      {
        id: "estado",
        header: "Estado del proceso",
        // CARDINAL PURO (Sergio 2026-04-27): el campo `estado` viene del
        // portal scrape · es el estado del PROCESO (no del contrato firmado).
        // Mostrar "Publicado" sin contexto era confuso · ahora se titula
        // "Estado del proceso" para que la Dra entienda que es el estado
        // del proceso publicado, no del contrato en ejecución.
        accessorFn: (r) => r.estado ?? "",
        cell: ({ row }) => {
          const r = row.original;
          return (
            <div className="text-xs">
              {r.estado ? (
                <span
                  className="inline-flex items-center px-1.5 py-0.5 rounded bg-stone-100 text-ink text-[10px] break-words"
                  title={`Estado del proceso en SECOP: "${r.estado}". Para el estado del contrato firmado, abrí el link manualmente.`}
                >
                  {r.estado}
                </span>
              ) : (
                <span
                  className="text-ink-soft/50 text-[10px] italic"
                  title="El portal community.secop no expone estado para este proceso · revisar en el link"
                >
                  — Revisar en el link
                </span>
              )}
            </div>
          );
        },
        size: 105,
      },
      {
        id: "modificatorios",
        header: "Modificatorios",
        // CARDINAL (Sergio 2026-04-28): los modificatorios vienen del scrape
        // del link community.secop como PDFs adjuntos. El clasificador
        // identifica TIPO (Adición · Prórroga · Cesión · Otrosí · Adenda ·
        // Suspensión · Liquidación · etc.) y NÚMERO. Display en columnas:
        // chip principal con summary cardinal + detalle por tipo en líneas
        // de 1 sub-línea. Sin valor monetario / días todavía · esa capa
        // viene del pipeline OCR (sesiones siguientes).
        accessorFn: (r) => r.modificatorios_summary,
        cell: ({ row }) => {
          const r = row.original;
          const n = r.modificatorios_count;
          if (n === 0) {
            return (
              <span
                className="text-ink-soft/60 text-[10px]"
                title="El portal community.secop no tiene PDFs de modificatorios para este proceso."
              >
                Sin modificatorios
              </span>
            );
          }
          // Detalle por tipo · agrupar para conteo por tipo
          const byTipo = new Map<string, ClassifiedModificatorio[]>();
          for (const m of r.modificatorios_classified) {
            const arr = byTipo.get(m.tipo) ?? [];
            arr.push(m);
            byTipo.set(m.tipo, arr);
          }
          // Chip de color por tipo · cardinal-claro
          const tipoColor: Record<string, string> = {
            "Adicion": "bg-emerald-50 text-emerald-800 border-emerald-200",
            "Prorroga": "bg-sky-50 text-sky-800 border-sky-200",
            "Modificatorio": "bg-amber-50 text-amber-800 border-amber-200",
            "Otrosi": "bg-violet-50 text-violet-800 border-violet-200",
            "Adenda": "bg-violet-50 text-violet-800 border-violet-200",
            "Cesion": "bg-rose-50 text-rose-800 border-rose-200",
            "Suspension": "bg-stone-100 text-stone-800 border-stone-300",
            "Reanudacion": "bg-stone-100 text-stone-800 border-stone-300",
            "Terminacion anticipada": "bg-rose-50 text-rose-800 border-rose-200",
            "Novacion": "bg-violet-50 text-violet-800 border-violet-200",
            "Liquidacion": "bg-stone-100 text-stone-800 border-stone-300",
          };
          return (
            <div className="text-[11px] flex flex-col gap-0.5">
              {/* Línea 1: total */}
              <span className="text-ink font-medium text-[10px]">
                {n} {n === 1 ? "acto" : "actos"}
              </span>
              {/* Líneas siguientes: chip por tipo con # */}
              {Array.from(byTipo.entries()).map(([tipo, arr]) => {
                const cls = tipoColor[tipo] ?? "bg-stone-100 text-stone-800 border-stone-300";
                const numbers = arr
                  .map((m) => m.numero ? `N°${m.numero}` : "")
                  .filter(Boolean);
                return (
                  <span
                    key={tipo}
                    className={`inline-flex items-center px-1.5 py-0.5 rounded border text-[9px] whitespace-nowrap w-fit ${cls}`}
                    title={arr.map((m) => `• ${m.tipo} ${m.numero ? `N° ${m.numero}` : ""} · ${m.nombre}`).join("\n")}
                  >
                    {arr.length > 1 ? `${arr.length} ` : ""}
                    {tipo}
                    {numbers.length > 0 && ` ${numbers.join(", ")}`}
                  </span>
                );
              })}
              <span
                className="text-ink-soft/60 text-[8px] italic mt-0.5"
                title="Tipo se infiere del nombre del PDF · valor monetario y plazo se agregarán cuando termine el procesamiento OCR del contenido"
              >
                valor pendiente OCR
              </span>
            </div>
          );
        },
        size: 175,
      },
      {
        id: "origen",
        header: "Estado en SECOP",
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
              {/* Alerta cardinal: discrepancia entre fuentes del SECOP.
                  Cuando rpmr-utcd y portal community.secop reportan datos
                  distintos para el mismo contrato, marca con icono visible
                  para que la Dra abra el modal y vea ambos valores. */}
              {r.discrepancias && r.discrepancias.length > 0 && (
                <div
                  className="mt-1 inline-flex items-center px-1.5 py-0.5 rounded bg-rose-50 text-rose-800 border border-rose-300 text-[9px] font-semibold"
                  title={`⚠️ Las fuentes del SECOP (rpmr-utcd y portal community.secop) reportan datos distintos para este contrato en ${r.discrepancias.length} ${r.discrepancias.length === 1 ? "campo" : "campos"}. Click la fila para ver los valores de cada fuente y verificar contra el portal.`}
                >
                  ⚠️ {r.discrepancias.length} discrepancia{r.discrepancias.length !== 1 ? "s" : ""}
                </div>
              )}
              {r.data_source === "integrado" && (() => {
                // CARDINAL (2026-04-27): cuando solo está en rpmr-utcd y NO
                // en portal, los valores pueden tener drift (95% de los rpmr-
                // only tienen discrepancia detectada). Badge cardinal rojo
                // alerta que la Dra debe verificar en el link directamente.
                const tieneDrift = r.discrepancias && r.discrepancias.length > 0;
                if (tieneDrift) {
                  return (
                    <div
                      className="mt-1 inline-flex items-center px-1.5 py-0.5 rounded bg-rose-100 text-rose-900 border border-rose-400 text-[9px] font-bold"
                      title="🚨 ALERTA CARDINAL: este proceso solo está en SECOP Integrado (rpmr-utcd) y se detectó drift de valores con el portal. Los valores mostrados PUEDEN SER INCORRECTOS. Verificá DIRECTAMENTE en el link al portal community.secop antes de confiar."
                    >
                      🚨 Drift detectado · NO confiar
                    </div>
                  );
                }
                return (
                  <div
                    className="mt-1 inline-flex items-center px-1.5 py-0.5 rounded bg-amber-50 text-amber-800 border border-amber-300 text-[9px] font-medium"
                    title="⚠️ Solo está en el SECOP Integrado (rpmr-utcd), no en el portal community.secop. El SECOP Integrado a veces tiene valores con drift. Para 100% confianza: click 'Abrir' y verificá en el portal."
                  >
                    ⚠️ Solo SECOP Integrado · usá el link
                  </div>
                );
              })()}
              {r.data_source === "portal" && (() => {
                const age = formatAge(r.data_source_scraped_at);
                const fechaCorta =
                  r.data_source_scraped_at?.slice(0, 10) ?? null;
                const tooltip = r.data_source_scraped_at
                  ? `Foto del SECOP tomada el ${fechaCorta} (${age ?? "fecha desconocida"}). Cuando Sergio corra "Búsqueda profunda" o el cron mensual, esta foto se actualiza con datos frescos.`
                  : "Foto del SECOP guardada de una búsqueda anterior. Se actualiza periódicamente.";
                return (
                  <>
                    <div
                      className="mt-1 inline-flex items-center px-1.5 py-0.5 rounded bg-amber-50 text-amber-800 border border-amber-200 text-[9px] font-medium"
                      title={tooltip}
                    >
                      Foto SECOP{age ? ` · ${age}` : ""}
                    </div>
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
        size: 130,
      },
      {
        id: "acciones",
        header: "Acciones",
        enableSorting: false,
        enableColumnFilter: false,
        cell: ({ row }) => {
          const r = row.original;
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
                    onClick={() => setEditingRow(r)}
                    disabled={busy}
                    className="inline-flex items-center gap-1 px-2 h-7 rounded text-[11px] text-burgundy hover:bg-burgundy/10 border border-transparent hover:border-burgundy/30 disabled:opacity-50"
                    title="Corregir consecutivo FEAB, vigencia, período o link"
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
        size: 170,
      },
    ],
    [busy, onPick, onUpdate, onRemove, selectedIds, onToggleSelect],
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
            <div className="eyebrow">Tus procesos del SECOP</div>
            <p className="text-xs text-ink-soft mt-1">
              {rows.length} procesos que vos seguís · cada fila es uno de tus
              links del SECOP, con todos sus datos extraídos automáticamente
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
            placeholder="¿Sumar otro proceso? Pegá acá la dirección (URL) del SECOP II…"
            className="flex-1"
            disabled={busy}
          />
          <Button
            onClick={() =>
              addUrl.trim() && onAdd(addUrl.trim()).then(() => setAddUrl(""))
            }
            disabled={busy || !addUrl.trim()}
            className="gap-2"
            title="Suma este proceso a tus 491 que ya seguís"
          >
            <Plus className="h-4 w-4" />
            Sumar a mi lista
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
          {/* Feature G r2 (2026-04-27): table-fixed evita que las celdas
              empujen el ancho de columnas. Junto con sizes reducidos, la
              tabla cabe sin scroll lateral en pantallas >=1280px. Cardinal:
              max 6-8 columnas + sin scroll horizontal (regla del CLAUDE.md). */}
          <table className="w-full text-sm table-fixed">
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

      {/* Editor expandido (2026-04-28 · Sergio "esto editar"). Permite
          corregir consecutivo FEAB, vigencia, período y link sin
          tocar el Excel. Cambios se guardan en IndexedDB y sobreviven
          al re-seed (merge inteligente · ensureSeed). */}
      {editingRow && (
        <WatchEditDialog
          row={editingRow}
          allSheets={allKnownSheets(rows)}
          onClose={() => setEditingRow(null)}
          onSave={async (patch) => {
            if (!editingRow.watch_url) return;
            await onUpdate(editingRow.watch_url, patch);
            setEditingRow(null);
          }}
          busy={busy}
        />
      )}
    </div>
  );
}

/** Returns the union of all sheets/períodos seen across the watch list,
 *  sorted alphabetically. Used as the suggested options in the editor
 *  so the Dra puede elegir uno conocido en lugar de tipearlo. Cardinal:
 *  permite tambien tipear uno nuevo (Excel evolves). */
function allKnownSheets(rows: UnifiedRow[]): string[] {
  const set = new Set<string>();
  for (const r of rows) {
    for (const s of r.sheets) set.add(s);
  }
  return Array.from(set).sort();
}

/**
 * WatchEditDialog · editor cardinal del watch list.
 *
 * La Dra abre este modal cuando hace click en "Editar" en una fila. Le
 * permite corregir TODOS los campos del Excel que el dashboard mantiene
 * por proceso:
 *   - Consecutivos FEAB asociados (modelo 1↔N · chips agregar/quitar)
 *   - Vigencias (chips · ej. ["2024", "2025"] cuando hay vigencias futuras)
 *   - Períodos / sheets ("FEAB 2024", "FEAB 2025", ...)
 *   - URL del SECOP (si la copió mal)
 *   - Nota libre
 *
 * Diseño:
 *   - Cada campo lista es de chips (badges) con X para quitar + input
 *     pequeño para agregar.
 *   - Períodos sugiere los que ya existen en el watch list (con dropdown).
 *   - Validación cardinal: la Dra puede vaciar campos · vacío = "—"
 *     honesto en la tabla, no inventa.
 */
function WatchEditDialog({
  row,
  allSheets,
  onClose,
  onSave,
  busy,
}: {
  row: UnifiedRow;
  allSheets: string[];
  onClose: () => void;
  onSave: (patch: {
    newUrl?: string;
    numero_contrato_excel?: string[];
    vigencias?: string[];
    sheets?: string[];
  }) => Promise<void>;
  busy: boolean;
}) {
  const [url, setUrl] = React.useState(row.watch_url ?? "");
  const [consecs, setConsecs] = React.useState<string[]>(
    row.numero_contratos_excel ?? [],
  );
  const [sheets, setSheets] = React.useState<string[]>(row.sheets);
  const [draftConsec, setDraftConsec] = React.useState("");
  const [draftSheet, setDraftSheet] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);

  const addToList = (
    list: string[],
    setList: (xs: string[]) => void,
    draft: string,
    setDraft: (s: string) => void,
  ) => {
    const v = draft.trim();
    if (!v) return;
    if (list.includes(v)) {
      setDraft("");
      return;
    }
    setList([...list, v]);
    setDraft("");
  };

  const removeFromList = (
    list: string[],
    setList: (xs: string[]) => void,
    idx: number,
  ) => {
    setList(list.filter((_, i) => i !== idx));
  };

  const handleSave = async () => {
    setError(null);
    const trimmedUrl = url.trim();
    if (!trimmedUrl) {
      setError("El link no puede quedar vacío.");
      return;
    }
    try {
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      const _ = new URL(trimmedUrl);
    } catch {
      setError("Pegá un link válido que empiece con https://");
      return;
    }
    await onSave({
      newUrl: trimmedUrl !== row.watch_url ? trimmedUrl : undefined,
      numero_contrato_excel: consecs,
      // Vigencias NO se editan desde el modal (Sergio 2026-04-28: solo
      // 3 campos visibles · consecutivo, período, link). El backend sigue
      // manejando vigencias desde el seed inicial · no las pisamos acá.
      sheets,
    });
  };

  return (
    <Dialog open={true} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <p className="text-[10px] uppercase tracking-wider text-ink-soft">
            Editar proceso
          </p>
          <DialogTitle className="serif text-xl text-ink">
            Corregir datos de este proceso
          </DialogTitle>
          <DialogDescription className="text-ink-soft text-xs">
            Tus cambios se guardan en este navegador y se preservan aunque el
            sistema vuelva a importar tu Excel maestro.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 mt-3">
          {/* Consecutivos FEAB */}
          <div>
            <label className="block text-xs font-semibold text-ink mb-1">
              Consecutivos del contrato (Excel FEAB)
            </label>
            <p className="text-[11px] text-ink-soft mb-2">
              Formato <code className="font-mono">CONTRATO-FEAB-NNNN-AAAA</code>{" "}
              · agregá uno o varios cuando una subasta tuvo varias adjudicaciones.
            </p>
            <div className="flex flex-wrap gap-1.5 mb-2">
              {consecs.map((c, i) => (
                <span
                  key={`${c}-${i}`}
                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-burgundy/10 text-burgundy text-[11px] font-mono"
                >
                  {c}
                  <button
                    onClick={() => removeFromList(consecs, setConsecs, i)}
                    className="hover:bg-burgundy/20 rounded-full px-1"
                    title={`Quitar ${c}`}
                  >
                    ×
                  </button>
                </span>
              ))}
              {consecs.length === 0 && (
                <span className="text-[11px] text-ink-soft italic">
                  (sin consecutivo asociado · proceso sin contrato firmado)
                </span>
              )}
            </div>
            <div className="flex gap-1">
              <Input
                value={draftConsec}
                onChange={(e) => setDraftConsec(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    addToList(consecs, setConsecs, draftConsec, setDraftConsec);
                  }
                }}
                placeholder="CONTRATO-FEAB-0001-2024"
                className="text-xs h-7 font-mono"
              />
              <button
                type="button"
                onClick={() =>
                  addToList(consecs, setConsecs, draftConsec, setDraftConsec)
                }
                disabled={!draftConsec.trim()}
                className="px-3 h-7 rounded text-[11px] bg-burgundy text-white hover:bg-burgundy/90 disabled:opacity-50"
              >
                Agregar
              </button>
            </div>
          </div>

          {/* Períodos / sheets */}
          <div>
            <label className="block text-xs font-semibold text-ink mb-1">
              Período / hoja del Excel
            </label>
            <p className="text-[11px] text-ink-soft mb-2">
              Cómo organizaste este proceso originalmente (ej.{" "}
              <code className="font-mono">FEAB 2024</code>). Podés ponerlo en
              varios períodos cuando aparece en más de una hoja.
            </p>
            <div className="flex flex-wrap gap-1.5 mb-2">
              {sheets.map((s, i) => (
                <span
                  key={`${s}-${i}`}
                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-burgundy/10 text-burgundy text-[11px]"
                >
                  {s}
                  <button
                    onClick={() => removeFromList(sheets, setSheets, i)}
                    className="hover:bg-burgundy/20 rounded-full px-1"
                  >
                    ×
                  </button>
                </span>
              ))}
              {sheets.length === 0 && (
                <span className="text-[11px] text-ink-soft italic">
                  (sin período · ingresá al menos uno)
                </span>
              )}
            </div>
            <div className="flex gap-1 items-center">
              <Input
                value={draftSheet}
                onChange={(e) => setDraftSheet(e.target.value)}
                list="known-sheets"
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    addToList(sheets, setSheets, draftSheet, setDraftSheet);
                  }
                }}
                placeholder="FEAB 2024"
                className="text-xs h-7 w-44"
              />
              <datalist id="known-sheets">
                {allSheets.map((s) => (
                  <option key={s} value={s} />
                ))}
              </datalist>
              <button
                type="button"
                onClick={() =>
                  addToList(sheets, setSheets, draftSheet, setDraftSheet)
                }
                disabled={!draftSheet.trim()}
                className="px-3 h-7 rounded text-[11px] bg-burgundy text-white hover:bg-burgundy/90 disabled:opacity-50"
              >
                Agregar
              </button>
            </div>
          </div>

          {/* URL */}
          <div>
            <label className="block text-xs font-semibold text-ink mb-1">
              Link del SECOP
            </label>
            <Input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://community.secop.gov.co/..."
              className="text-xs h-8"
            />
            <p className="text-[10px] text-ink-soft mt-1">
              Si corregís el link, el sistema asocia este proceso a la nueva
              dirección y vuelve a leer los datos del SECOP en el próximo
              refresh.
            </p>
          </div>

          {error && (
            <div className="text-xs text-rose-700 bg-rose-50 border border-rose-200 rounded px-3 py-2">
              {error}
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 mt-5 pt-3 border-t border-rule">
          <button
            onClick={onClose}
            disabled={busy}
            className="px-4 h-9 rounded text-sm text-ink-soft hover:bg-stone-100 disabled:opacity-50"
          >
            Cancelar
          </button>
          <button
            onClick={handleSave}
            disabled={busy}
            className="px-4 h-9 rounded text-sm bg-burgundy text-white hover:bg-burgundy/90 disabled:opacity-50"
          >
            {busy ? "Guardando…" : "Guardar cambios"}
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}


/** Human-friendly label for a verifyStatus — used by the Origen column
 *  filter so the popover lists "Contrato firmado" instead of the raw
 *  enum value "contrato_firmado". Lenguaje cero tech para Cami abogada. */
function statusLabel(s: UnifiedRow["verifyStatus"]): string {
  switch (s) {
    case "contrato_firmado":  return "Contrato firmado";
    case "verificado":        return "Publicado en SECOP";
    case "contrato_interno":  return "Verificable solo con tu login";
    case "borrador":          return "Borrador (no publicado)";
    case "no_en_api":         return "Aún sin publicar";
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
