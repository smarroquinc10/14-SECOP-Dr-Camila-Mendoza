/**
 * Cliente del dashboard FEAB para deploy estático en GitHub Pages.
 *
 * **Antes** este archivo proxyaba un FastAPI corriendo en localhost:8000.
 * **Ahora** todo el laburo se hace en el browser:
 *
 *   - Lectura de los 491 procesos del watch list  → IndexedDB (sembrado
 *     desde `/data/watched_urls.json` en el primer arranque). Ver
 *     `state-store.ts`.
 *   - Lectura en vivo de SECOP (contratos / Integrado)  → llamadas
 *     directas a `datos.gov.co/resource/...`. CORS abierto, no necesita
 *     proxy. Ver `socrata.ts`.
 *   - Audit log inmutable hash-chained               → IndexedDB
 *     (`audit_log` store).
 *   - Observaciones manuales de la Dra.              → IndexedDB.
 *
 * El interfaz pública (objeto `api` + types) se mantiene idéntica al
 * original FastAPI, así los componentes (`page.tsx`, `detail-dialog.tsx`,
 * `unified-table.tsx`, `mods-panel.tsx`, `watch-list.tsx`) NO necesitan
 * cambios. Lo que era un round-trip HTTP de 200ms ahora es una llamada
 * Socrata (~500ms el primero, después cacheado por SWR) o IndexedDB
 * (~5ms). Más rápido en general.
 *
 * Limitaciones conscientes vs el FastAPI original:
 *
 *   - `contractPortal(uid)` siempre devuelve `available: false` — el
 *     scraper del portal community.secop usa Playwright, que no corre en
 *     un browser. La UI ya tiene fallback: muestra el botón "Abrir en
 *     portal" para que la Dra resuelva el captcha en otra pestaña.
 *   - `portalProgress()` siempre devuelve `running: false`. Los progress
 *     bars relacionados con el scraper del portal nunca se muestran.
 *   - `portalScrape()` no scrapea — abre la URL del portal en otra
 *     pestaña como fallback amigable.
 *   - `refresh()` y `verify()` ya no recorren el Excel en disco. Lo que
 *     hacen ahora es disparar un re-fetch de Socrata.
 */

import {
  addWatched,
  appendAudit,
  editWatched,
  ensureSeed,
  getObservacion as getObsFromStore,
  getMeta,
  inferProcessId,
  listAudit,
  listWatched,
  removeWatched as removeWatchedFromStore,
  setObservacion,
  setMeta,
  totalAuditEntries,
  verifyAuditChain,
  withBasePath,
} from "./state-store";
import type { AuditEntry as StoreAuditEntry, WatchedItemRow } from "./state-store";
import {
  extractNoticeUid,
  fetchFeabContratos,
  fetchIntegrado,
  type SocrataContrato,
  type SocrataIntegrado,
} from "./socrata";

// El seed_version se usa por la lógica de `ensureSeed` para decidir si
// repoblar la store. Bumpealo cuando cambies el `/data/watched_urls.json`
// y querés que Cami reciba los nuevos URLs en su próximo refresh.
const SEED_VERSION = "2026-04-25";

// Bandera para no llamar `ensureSeed` 491 veces por segundo: lo intentamos
// una sola vez y guardamos la promise. Si falla, los próximos calls fallan
// rápido también — pero el siguiente módulo de página puede reintentar.
let _seedPromise: Promise<{ seeded: boolean; itemCount: number }> | null = null;
function seed() {
  if (!_seedPromise) {
    _seedPromise = ensureSeed(SEED_VERSION).catch((err) => {
      _seedPromise = null; // permite reintentar
      throw err;
    });
  }
  return _seedPromise;
}

// Asegurar que cualquier acceso a la API espere el seed. Si el browser no
// soporta IndexedDB (raro hoy día), seguimos como degraded mode.
async function ensureSeeded(): Promise<void> {
  if (typeof indexedDB === "undefined") return;
  try {
    await seed();
  } catch (err) {
    console.warn("[api] seed falló, sigo en degraded mode:", err);
  }
}

// ---- Type definitions (idénticas al original FastAPI) ---------------------

export interface Contract {
  id_contrato?: string;
  referencia_del_contrato?: string;
  proceso_de_compra?: string;
  proveedor_adjudicado?: string;
  documento_proveedor?: string;
  tipodocproveedor?: string;
  objeto_del_contrato?: string;
  valor_del_contrato?: string;
  valor_pagado?: string;
  valor_facturado?: string;
  fecha_de_firma?: string;
  fecha_de_inicio_del_contrato?: string;
  fecha_de_fin_del_contrato?: string;
  fecha_fin_liquidacion?: string;
  estado_contrato?: string;
  liquidaci_n?: string;
  modalidad_de_contratacion?: string;
  tipo_de_contrato?: string;
  dias_adicionados?: string | number;
  origen_de_los_recursos?: string;
  urlproceso?: string;
  _notas?: string;
  [key: string]: unknown;
}

export interface ObservacionDra {
  sheet: string;
  row: number;
  text: string;
}

export interface ContractDetail {
  notice_uid: string | null;
  process_id: string;
  proceso: Record<string, unknown> | null;
  contratos: Contract[];
  adiciones_by_contrato: Record<string, Record<string, unknown>[]>;
  garantias_by_contrato: Record<string, Record<string, unknown>[]>;
  pagos_by_contrato: Record<string, Record<string, unknown>[]>;
  ejecucion_by_contrato: Record<string, Record<string, unknown>[]>;
  suspensiones_by_contrato: Record<string, Record<string, unknown>[]>;
  mods_proceso: Record<string, unknown>[];
  feab_fills: Record<string, unknown>;
  feab_confidence: Record<string, string>;
  feab_sources: Record<string, string>;
  needs_review: string[];
  issues: string[];
  observaciones_dra: ObservacionDra[];
  secop_hash: string;
  code_version: string;
  fetched_at: string;
}

export interface AuditEntry {
  ts: string;
  op: string;
  row?: number;
  process_id?: string;
  column?: string;
  old?: unknown;
  new?: unknown;
  source?: string;
  confidence?: string;
  secop_hash?: string;
  code_version?: string;
  hash: string;
  prev_hash: string;
}

export interface AuditLogResponse {
  entries: AuditEntry[];
  intact: boolean;
  problems: string[];
  total: number;
}

export interface FeabEntity {
  nit: string;
  nombre: string;
  alias: string;
  padre: string;
  contratos: number;
  procesos: number;
}

export interface ModItem {
  id_contrato: string;
  referencia: string;
  proveedor: string;
  objeto: string;
  valor: string;
  estado: string;
  dias_adicionados: number;
  fecha_firma: string;
  fecha_fin: string;
  fecha_notificacion_prorroga: string;
  fecha_actualizacion: string;
  url: string;
}

export interface ModSummary {
  total_modificados: number;
  total_dias_adicionados: number;
  ultimo: ModItem | null;
  items: ModItem[];
}

export interface WatchedAppearance {
  sheet: string;
  vigencia: string | null;
  row: number | null;
  url: string;
}

export interface ExcelData {
  sheet?: string;
  row?: number;
  vigencia?: string | null;
  estado?: string;
  fecha_firma?: string;
  fecha_inicio?: string;
  fecha_terminacion?: string;
  valor_total?: number | string;
  valor_inicial?: number | string;
  proveedor?: string;
  objeto?: string;
  modalidad?: string;
  dias_prorrogas?: number | string;
  adiciones_count?: number | string;
  liquidacion?: string;
  fecha_liquidacion?: string;
  numero_contrato?: string;
  supervisor?: string;
  obs_brief?: string | null;
  is_modificado?: boolean;
}

export interface WatchedItem {
  url: string;
  process_id: string | null;
  notice_uid: string | null;
  sheets: string[];
  vigencias: string[];
  appearances: WatchedAppearance[];
  excel_data?: ExcelData | null;
  obs_brief?: string | null;
  is_modificado_excel?: boolean;
  added_at: string;
  note: string | null;
}

/** Espejo de un proceso del dataset rpmr-utcd (SECOP Integrado). */
export interface IntegradoSnapshot {
  available: boolean;
  key: string;
  fields?: Record<string, string | null>;
  synced_at?: string | null;
  source?: string | null;
}

/** Subset summary del Integrado para la tabla principal. */
export interface IntegradoSummary {
  estado_del_proceso?: string | null;
  valor_contrato?: string | null;
  nom_raz_social_contratista?: string | null;
  fecha_de_firma_del_contrato?: string | null;
  fecha_inicio_ejecuci_n?: string | null;
  fecha_fin_ejecuci_n?: string | null;
  modalidad_de_contrataci_n?: string | null;
  tipo_de_contrato?: string | null;
  numero_del_contrato?: string | null;
  numero_de_proceso?: string | null;
  objeto_a_contratar?: string | null;
  url_contrato?: string | null;
}

export interface PortalSnapshot {
  available: boolean;
  notice_uid: string;
  fields?: Record<string, string>;
  all_labels?: Record<string, string>;
  documents?: { name: string; url: string }[];
  notificaciones?: { proceso: string; evento: string; fecha: string }[];
  status?: string | null;
  missing_fields?: string[];
  scraped_at?: string | null;
  raw_length?: number | null;
}

// ---- Implementation -------------------------------------------------------

const FEAB_NIT = "901148337";

const FEAB_ENTITY: FeabEntity = {
  nit: FEAB_NIT,
  nombre:
    "Fondo Especial para la Administración de Bienes de la Fiscalía General de la Nación",
  alias: "FEAB",
  padre: "Fiscalía General de la Nación",
  contratos: 0,
  procesos: 0,
};

// Cache en memoria de los datos crudos de Socrata. Se invalida con
// `integradoSync()` o `verifyWatch()`.
//
// IMPORTANTE: usamos una promise singleton (no el resultado) para que dos
// componentes que llamen `getContracts()` / `getIntegrado()` en paralelo
// antes de que el primer fetch termine compartan la MISMA request. Antes
// el cache era `T[] | null` y se rellenaba post-await: si el segundo
// caller llegaba durante el await, hacía fetch de nuevo. Ese race causaba
// 2-3 hits a datos.gov.co por carga inicial (~6 MB de overhead).
let _contractsPromise: Promise<SocrataContrato[]> | null = null;
let _integradoPromise: Promise<SocrataIntegrado[]> | null = null;
let _portalBulkPromise: Promise<PortalBulk> | null = null;
let _lastSyncedAt: string | null = null;

/**
 * Tipo del bulk del portal cache. La key es el `notice_uid` y el value
 * es el snapshot scrapeado del portal community.secop.gov.co.
 *
 * Este cache vive como archivo estático en `/data/portal_opportunity_seed.json`,
 * bakeado al bundle al momento del último scrape (~66 procesos típicamente).
 * No se actualiza desde el browser — es read-only fallback para los
 * procesos que el API público de datos.gov.co no expone.
 */
export type PortalBulk = Record<
  string,
  {
    fields?: Record<string, string | null>;
    documents?: { name: string; url: string }[];
    notificaciones?: { proceso: string; evento: string; fecha: string }[];
    status?: string | null;
    scraped_at?: string | null;
    all_labels?: Record<string, string>;
  }
>;

async function getContracts(forceRefresh = false): Promise<SocrataContrato[]> {
  if (forceRefresh) _contractsPromise = null;
  if (!_contractsPromise) {
    _contractsPromise = (async () => {
      const rows = await fetchFeabContratos();
      _lastSyncedAt = new Date().toISOString();
      await setMeta("last_synced_at", _lastSyncedAt);
      return rows;
    })().catch((err) => {
      _contractsPromise = null; // permite reintentar
      throw err;
    });
  }
  return _contractsPromise;
}

async function getIntegrado(forceRefresh = false): Promise<SocrataIntegrado[]> {
  if (forceRefresh) _integradoPromise = null;
  if (!_integradoPromise) {
    _integradoPromise = (async () => {
      const rows = await fetchIntegrado();
      _lastSyncedAt = new Date().toISOString();
      await setMeta("last_synced_at", _lastSyncedAt);
      return rows;
    })().catch((err) => {
      _integradoPromise = null;
      throw err;
    });
  }
  return _integradoPromise;
}

/**
 * Bulk del portal cache: lo bajamos UNA sola vez como archivo estático
 * y lo dejamos en memoria. Si el bundle no incluye el seed (deploy
 * fresco sin scraper history), devolvemos `{}` para que la cascada de
 * fallbacks de `unified-table.tsx` siga siendo honesta.
 */
async function getPortalBulk(): Promise<PortalBulk> {
  if (!_portalBulkPromise) {
    _portalBulkPromise = (async () => {
      try {
        const url = withBasePath("/data/portal_opportunity_seed.json");
        const res = await fetch(url, { cache: "no-store" });
        if (!res.ok) return {} as PortalBulk;
        return (await res.json()) as PortalBulk;
      } catch {
        return {} as PortalBulk;
      }
    })();
  }
  return _portalBulkPromise;
}

function toContract(row: SocrataContrato): Contract {
  return row as Contract; // mismo shape exacto en runtime
}

function rowToWatchedItem(row: WatchedItemRow, obs?: string | null): WatchedItem {
  return {
    url: row.url,
    process_id: row.process_id,
    notice_uid: row.notice_uid,
    sheets: row.sheets,
    vigencias: row.vigencias,
    appearances: row.appearances,
    added_at: row.added_at,
    note: row.note,
    obs_brief: obs ?? null,
    excel_data: null,
    is_modificado_excel: false,
  };
}

function storeEntryToApi(e: StoreAuditEntry): AuditEntry {
  return {
    ts: e.ts,
    op: e.op,
    process_id: e.process_id ?? undefined,
    column: e.field ?? undefined,
    old: e.old,
    new: e.new,
    source: e.source ?? undefined,
    hash: e.hash,
    prev_hash: e.prev_hash,
    code_version: "html-pure", // marca que viene del browser, no del MSI
  };
}

// ---- The api object -------------------------------------------------------

export const api = {
  // ---- Health + identity ----
  health: async () => ({
    status: "ok",
    code_version: "html-pure",
    timestamp: new Date().toISOString(),
  }),

  feab: async (): Promise<FeabEntity> => {
    await ensureSeeded();
    const [contratos, integrado] = await Promise.all([
      getContracts().catch(() => []),
      getIntegrado().catch(() => []),
    ]);
    // procesos = unique notice_uids mencionados en contratos + integrado
    const noticeIds = new Set<string>();
    for (const c of contratos) {
      const uid = extractNoticeUid(typeof c.urlproceso === "string" ? c.urlproceso : undefined);
      if (uid) noticeIds.add(uid);
    }
    for (const i of integrado) {
      const uid = extractNoticeUid(typeof i.url_contrato === "string" ? i.url_contrato : undefined);
      if (uid) noticeIds.add(uid);
    }
    return {
      ...FEAB_ENTITY,
      contratos: contratos.length,
      procesos: noticeIds.size,
    };
  },

  // ---- Contracts ----
  contracts: async (limit = 500, offset = 0): Promise<Contract[]> => {
    const all = await getContracts();
    return all.slice(offset, offset + limit).map(toContract);
  },

  contract: async (id: string): Promise<ContractDetail> => {
    const all = await getContracts();
    const me = all.find((c) => c.id_contrato === id);
    const noticeUid = me ? extractNoticeUid(typeof me.urlproceso === "string" ? me.urlproceso : undefined) : null;
    // En la versión HTML solo agrupamos los contratos del MISMO proceso
    // (mismo notice_uid). No hay tablas separadas para adiciones/garantías
    // /pagos/ejecución/suspensiones — Socrata no las expone públicamente
    // para la mayoría de procesos del FEAB. La UI ya soporta arrays vacíos
    // y muestra "—".
    const sameProcess = noticeUid
      ? all.filter((c) => extractNoticeUid(typeof c.urlproceso === "string" ? c.urlproceso : undefined) === noticeUid)
      : me ? [me] : [];

    const observaciones: ObservacionDra[] = [];
    if (noticeUid) {
      const obs = await getObsFromStore(noticeUid);
      if (obs) {
        observaciones.push({ sheet: "manual", row: 0, text: obs });
      }
    }

    return {
      notice_uid: noticeUid,
      process_id: id,
      proceso: null,
      contratos: sameProcess.map(toContract),
      adiciones_by_contrato: {},
      garantias_by_contrato: {},
      pagos_by_contrato: {},
      ejecucion_by_contrato: {},
      suspensiones_by_contrato: {},
      mods_proceso: [],
      feab_fills: {},
      feab_confidence: {},
      feab_sources: {},
      needs_review: [],
      issues: [],
      observaciones_dra: observaciones,
      secop_hash: "",
      code_version: "html-pure",
      fetched_at: new Date().toISOString(),
    };
  },

  processes: async (limit = 500): Promise<Contract[]> => {
    // En la HTML version, "procesos" y "contratos" se sirven del mismo
    // dataset (jbjy-vk9h trae contratos electronicos que incluyen el
    // notice_uid del proceso padre). El componente que llamaba a
    // `api.processes` (mods-panel) en realidad usaba contratos.
    return api.contracts(limit, 0);
  },

  // ---- Audit log ----
  auditLog: async (limit = 100): Promise<AuditLogResponse> => {
    await ensureSeeded();
    const [entries, integrity, total] = await Promise.all([
      listAudit(limit),
      verifyAuditChain(),
      totalAuditEntries(),
    ]);
    return {
      entries: entries.map(storeEntryToApi),
      intact: integrity.intact,
      problems: integrity.problems,
      total,
    };
  },

  modificatoriosRecientes: async (limit = 20): Promise<ModSummary> => {
    const all = await getContracts();
    const mods = all
      .filter((c) => {
        const dias = typeof c.dias_adicionados === "number"
          ? c.dias_adicionados
          : Number(c.dias_adicionados ?? 0);
        return dias > 0 || /modific/i.test(c.estado_contrato ?? "");
      })
      .sort((a, b) => {
        const da = a.fecha_de_firma ?? "";
        const db = b.fecha_de_firma ?? "";
        return db.localeCompare(da);
      });
    const items: ModItem[] = mods.slice(0, limit).map((c) => ({
      id_contrato: c.id_contrato ?? "",
      referencia: c.referencia_del_contrato ?? "",
      proveedor: c.proveedor_adjudicado ?? "",
      objeto: c.objeto_del_contrato ?? "",
      valor: c.valor_del_contrato ?? "",
      estado: c.estado_contrato ?? "",
      dias_adicionados: typeof c.dias_adicionados === "number"
        ? c.dias_adicionados
        : Number(c.dias_adicionados ?? 0),
      fecha_firma: c.fecha_de_firma ?? "",
      fecha_fin: c.fecha_de_fin_del_contrato ?? "",
      fecha_notificacion_prorroga: "",
      fecha_actualizacion: "",
      url: typeof c.urlproceso === "string" ? c.urlproceso : "",
    }));
    const total_dias = mods.reduce((acc, c) => {
      const d = typeof c.dias_adicionados === "number"
        ? c.dias_adicionados
        : Number(c.dias_adicionados ?? 0);
      return acc + (Number.isFinite(d) ? d : 0);
    }, 0);
    return {
      total_modificados: mods.length,
      total_dias_adicionados: total_dias,
      ultimo: items[0] ?? null,
      items,
    };
  },

  ultimaActualizacion: async (): Promise<{
    ultimo_fill: string | null;
    ultimo_replace: string | null;
    ultima_verificacion: string | null;
    ultima_consulta: string | null;
    total_operaciones: number;
  }> => {
    await ensureSeeded();
    const [entries, total] = await Promise.all([
      listAudit(1000),
      totalAuditEntries(),
    ]);
    const findOp = (op: string) =>
      entries.find((e) => e.op === op)?.ts ?? null;
    return {
      ultimo_fill: findOp("fill"),
      ultimo_replace: findOp("replace"),
      ultima_verificacion: findOp("verify"),
      ultima_consulta: _lastSyncedAt ?? (await getMeta<string>("last_synced_at")) ?? null,
      total_operaciones: total,
    };
  },

  // ---- Watch list CRUD ----
  watchList: async (): Promise<{ items: WatchedItem[] }> => {
    await ensureSeeded();
    const rows = await listWatched();
    // Cada item enriquecido con su `obs_brief` si tiene observación manual.
    const items = await Promise.all(
      rows.map(async (r) => {
        const obs = r.notice_uid ? await getObsFromStore(r.notice_uid) : null;
        return rowToWatchedItem(r, obs);
      })
    );
    return { items };
  },

  watchAdd: async (
    url: string,
    note?: string
  ): Promise<{ added: boolean; item: WatchedItem; total: number; reason?: string }> => {
    await ensureSeeded();
    try {
      // Vigencia se infiere del año actual; la UI puede llamar
      // `api.watchAdd` con `note` que en la HTML version interpretamos
      // como si fuera un hint de vigencia (formato "2026" o "FEAB 2026").
      const m = (note ?? "").match(/(20\d{2})/);
      const vigencia = m ? m[1] : String(new Date().getFullYear());
      const item = await addWatched({ url, vigencia, note: note ?? null });
      const all = await listWatched();
      return {
        added: true,
        item: rowToWatchedItem(item),
        total: all.length,
      };
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      const all = await listWatched();
      const existing = all.find((r) => r.url === url);
      return {
        added: false,
        item: existing ? rowToWatchedItem(existing) : ({
          url, process_id: null, notice_uid: null,
          sheets: [], vigencias: [], appearances: [], added_at: new Date().toISOString(),
          note: note ?? null,
        }),
        total: all.length,
        reason: msg,
      };
    }
  },

  watchRemove: async (url: string): Promise<{ removed: number; total: number }> => {
    await ensureSeeded();
    await removeWatchedFromStore(url);
    const all = await listWatched();
    return { removed: 1, total: all.length };
  },

  watchUpdate: async (
    oldUrl: string,
    newUrl: string,
    note?: string
  ): Promise<{ updated: boolean; item: WatchedItem; total: number }> => {
    await ensureSeeded();
    const item = await editWatched(oldUrl, newUrl, note ?? null);
    const all = await listWatched();
    return { updated: true, item: rowToWatchedItem(item), total: all.length };
  },

  // En la HTML version, "import-from-excel" no aplica (no tenemos disco).
  // Devolvemos un response coherente con shape pero indicando 0 cambios.
  watchImportFromExcel: async (workbook?: string) => ({
    added_new: 0,
    merged: 0,
    already_recorded: 0,
    skipped_invalid: 0,
    errors: ["Importar desde Excel no está disponible en la versión web"],
    total_unique: (await listWatched()).length,
    total_appearances: 0,
    per_sheet: {},
    workbook: workbook ?? "",
  }),

  // ---- Refresh / verify ----
  refresh: async (): Promise<{ status: string; workbook: string; started_at: string }> => {
    // Re-fetch Socrata, sin tocar IndexedDB.
    await Promise.all([getContracts(true), getIntegrado(true)]);
    return {
      status: "ok",
      workbook: "",
      started_at: new Date().toISOString(),
    };
  },

  verify: async (): Promise<{ total: number; fresh: number; stale: number; errors: number; drift_rows: { row: number; process_id: string }[] }> => {
    await Promise.all([getContracts(true), getIntegrado(true)]);
    const all = await listWatched();
    return {
      total: all.length,
      fresh: all.length,
      stale: 0,
      errors: 0,
      drift_rows: [],
    };
  },

  verifyWatch: async (): Promise<{ started: boolean; pid: number; message: string }> => {
    // Trigger un re-fetch de Socrata. La UI no espera la promesa porque
    // pollea verify-progress, así que lo hacemos fire-and-forget.
    void Promise.all([getContracts(true), getIntegrado(true)]).then(() =>
      appendAudit({ op: "verify" })
    );
    return {
      started: true,
      pid: 0,
      message: "Refrescando contra SECOP…",
    };
  },

  verifyProgress: async () => ({
    running: false,
    processed: 0,
    total: 0,
    percent: 0,
    started_at: null as string | null,
    elapsed_seconds: null as number | null,
    last_update_age_seconds: null as number | null,
    eta_seconds: null as number | null,
    report_path: null as string | null,
  }),

  // ---- Portal scraper (no aplica en HTML pura) ----
  contractPortal: async (notice_uid: string): Promise<PortalSnapshot> => ({
    available: false,
    notice_uid,
  }),

  portalProgress: async () => ({
    running: false,
    processed: 0,
    total: 0,
    percent: 0,
    started_at: null as string | null,
    elapsed_seconds: null as number | null,
    last_update_age_seconds: null as number | null,
    eta_seconds: null as number | null,
    ok: 0,
    partial: 0,
    errored: 0,
    last_event: null as Record<string, unknown> | null,
  }),

  portalScrape: async (opts?: { uid?: string; limit?: number; force?: boolean }) => {
    // Mejor que un no-op: si la UI llama portalScrape con un uid,
    // abrimos el portal SECOP en otra pestaña para que la Dra resuelva
    // el captcha a mano.
    if (opts?.uid && typeof window !== "undefined") {
      const portalUrl = `https://community.secop.gov.co/Public/Tendering/OpportunityDetail/Index?noticeUID=${encodeURIComponent(opts.uid)}`;
      window.open(portalUrl, "_blank", "noopener,noreferrer");
    }
    return { started: false, pid: 0, cmd: "html-pure: opens portal in new tab" };
  },

  // ---- SECOP Integrado (rpmr-utcd) ----
  contractIntegrado: async (key: string): Promise<IntegradoSnapshot> => {
    const all = await getIntegrado();
    const matched = all.find((r) => {
      const url = typeof r.url_contrato === "string" ? r.url_contrato : "";
      const uid = extractNoticeUid(url);
      return uid === key.toUpperCase() || r.numero_de_proceso === key;
    });
    if (!matched) {
      return {
        available: false,
        key,
        synced_at: _lastSyncedAt,
        source: "https://www.datos.gov.co/resource/rpmr-utcd.json",
      };
    }
    const fields: Record<string, string | null> = {};
    for (const [k, v] of Object.entries(matched)) {
      fields[k] = typeof v === "string" ? v : v == null ? null : String(v);
    }
    return {
      available: true,
      key,
      fields,
      synced_at: _lastSyncedAt,
      source: "https://www.datos.gov.co/resource/rpmr-utcd.json",
    };
  },

  integradoBulk: async () => {
    const all = await getIntegrado();
    const by_notice_uid: Record<string, IntegradoSummary> = {};
    const by_pccntr: Record<string, IntegradoSummary> = {};
    for (const r of all) {
      const url = typeof r.url_contrato === "string" ? r.url_contrato : "";
      const summary: IntegradoSummary = {
        estado_del_proceso: r.estado_del_proceso ?? null,
        valor_contrato: r.valor_contrato ?? null,
        nom_raz_social_contratista: r.nom_raz_social_contratista ?? null,
        fecha_de_firma_del_contrato: r.fecha_de_firma_del_contrato ?? null,
        fecha_inicio_ejecuci_n: r.fecha_inicio_ejecuci_n ?? null,
        fecha_fin_ejecuci_n: r.fecha_fin_ejecuci_n ?? null,
        modalidad_de_contrataci_n: r.modalidad_de_contrataci_n ?? null,
        tipo_de_contrato: r.tipo_de_contrato ?? null,
        numero_del_contrato: r.numero_del_contrato ?? null,
        numero_de_proceso: r.numero_de_proceso ?? null,
        objeto_a_contratar: r.objeto_a_contratar ?? null,
        url_contrato: url,
      };
      const uid = extractNoticeUid(url);
      if (uid) by_notice_uid[uid] = summary;
      const pccntr = url.match(/CO1\.PCCNTR\.\d+/i)?.[0];
      if (pccntr) by_pccntr[pccntr.toUpperCase()] = summary;
    }
    return {
      synced_at: _lastSyncedAt,
      total_rows: all.length,
      source: "https://www.datos.gov.co/resource/rpmr-utcd.json",
      nit: FEAB_NIT,
      by_notice_uid,
      by_pccntr,
    };
  },

  integradoSummary: async () => {
    const all = await getIntegrado();
    const noticeCount = new Set(
      all.map((r) => {
        const url = typeof r.url_contrato === "string" ? r.url_contrato : "";
        return extractNoticeUid(url);
      }).filter(Boolean)
    ).size;
    const pccntrCount = new Set(
      all.map((r) => {
        const url = typeof r.url_contrato === "string" ? r.url_contrato : "";
        return url.match(/CO1\.PCCNTR\.\d+/i)?.[0];
      }).filter(Boolean)
    ).size;
    return {
      synced_at: _lastSyncedAt,
      total_rows: all.length,
      by_notice_uid_count: noticeCount,
      by_pccntr_count: pccntrCount,
      source: "https://www.datos.gov.co/resource/rpmr-utcd.json",
      nit: FEAB_NIT,
    };
  },

  integradoSync: async (nit?: string): Promise<{ started: boolean; pid: number; cmd: string }> => {
    void getIntegrado(true).then(() =>
      appendAudit({ op: "verify", source: "rpmr-utcd" })
    );
    return {
      started: true,
      pid: 0,
      cmd: `html-pure: refetch rpmr-utcd?nit_de_la_entidad=${nit ?? FEAB_NIT}`,
    };
  },

  /**
   * Bulk del portal cache (seed estático) — usado por `unified-table.tsx`
   * como tercer nivel de fallback cuando ni el SECOP API ni Integrado
   * tienen datos del proceso. La key es el `notice_uid`.
   */
  portalBulk: async (): Promise<PortalBulk> => {
    return getPortalBulk();
  },
};

// ---- Re-export observation helpers para componentes que las quieran -----

export const observaciones = {
  get: getObsFromStore,
  set: setObservacion,
};

// ---- Re-export utility helpers --------------------------------------------

export { inferProcessId, withBasePath };
