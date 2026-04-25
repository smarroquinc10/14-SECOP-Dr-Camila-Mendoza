/**
 * Thin client for the FastAPI bridge running on http://localhost:8000.
 * Goes through Next.js rewrite at /api/secop/*.
 */

const BASE = "/api/secop";

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

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API ${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`API ${path} → ${res.status}`);
  return res.json() as Promise<T>;
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
  numero_contrato_excel?: string | null;
  obs_brief?: string | null;
  is_modificado_excel?: boolean;
  added_at: string;
  note: string | null;
}

export const api = {
  health: () => get<{ status: string; code_version: string; timestamp: string }>("/health"),
  feab: () => get<FeabEntity>("/entity/feab"),
  contracts: (limit = 500, offset = 0) =>
    get<Contract[]>(`/contracts?limit=${limit}&offset=${offset}`),
  contract: (id: string) =>
    get<ContractDetail>(`/contracts/${encodeURIComponent(id)}`),
  processes: (limit = 500) => get<Contract[]>(`/processes?limit=${limit}`),
  auditLog: (limit = 100) => get<AuditLogResponse>(`/audit-log?limit=${limit}`),
  modificatoriosRecientes: (limit = 20) =>
    get<ModSummary>(`/modificatorios-recientes?limit=${limit}`),
  ultimaActualizacion: () =>
    get<{
      ultimo_fill: string | null;
      ultimo_replace: string | null;
      ultima_verificacion: string | null;
      ultima_consulta: string | null;
      total_operaciones: number;
    }>("/ultima-actualizacion"),
  watchList: () => get<{ items: WatchedItem[] }>("/watch"),
  watchAdd: (url: string, note?: string) =>
    post<{ added: boolean; item: WatchedItem; total: number; reason?: string }>(
      "/watch",
      { url, note: note ?? "" }
    ),
  watchRemove: async (url: string) => {
    const res = await fetch(
      `/api/secop/watch?url=${encodeURIComponent(url)}`,
      { method: "DELETE", cache: "no-store" }
    );
    if (!res.ok) throw new Error(`watch-remove ${res.status}`);
    return res.json() as Promise<{ removed: number; total: number }>;
  },
  watchUpdate: async (oldUrl: string, newUrl: string, note?: string) => {
    const res = await fetch(`/api/secop/watch`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ old_url: oldUrl, new_url: newUrl, note }),
      cache: "no-store",
    });
    if (!res.ok) {
      const err = await res
        .json()
        .catch(() => ({ detail: `${res.status}` }));
      throw new Error(err.detail ?? `watch-update ${res.status}`);
    }
    return res.json() as Promise<{
      updated: boolean;
      item: WatchedItem;
      total: number;
    }>;
  },
  watchImportFromExcel: (workbook?: string) =>
    post<{
      added_new: number;
      merged: number;
      already_recorded: number;
      skipped_invalid: number;
      errors: string[];
      total_unique: number;
      total_appearances: number;
      per_sheet: Record<
        string,
        {
          found: number;
          added_new: number;
          merged: number;
          already_recorded: number;
          no_link_col: number;
        }
      >;
      workbook: string;
    }>("/watch/import-from-excel", workbook ? { workbook } : {}),
  refresh: () => post<{ status: string; workbook: string; started_at: string }>("/refresh"),
  verify: () => post<{ total: number; fresh: number; stale: number; errors: number; drift_rows: { row: number; process_id: string }[] }>("/verify"),
  verifyWatch: () =>
    post<{ started: boolean; pid: number; message: string }>("/verify-watch"),
  verifyProgress: () =>
    get<{
      running: boolean;
      processed: number;
      total: number;
      percent: number;
      started_at: string | null;
      last_update_age_seconds: number | null;
      eta_seconds: number | null;
      report_path: string | null;
    }>("/verify-progress"),
};
