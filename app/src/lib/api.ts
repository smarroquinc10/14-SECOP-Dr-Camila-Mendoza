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

export interface WatchedItem {
  url: string;
  process_id: string | null;
  notice_uid: string | null;
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
  watchImportFromExcel: (workbook?: string) =>
    post<{
      added: number;
      skipped_dupe: number;
      skipped_invalid: number;
      errors: string[];
      total: number;
      per_sheet: Record<
        string,
        {
          found: number;
          added: number;
          skipped_dupe: number;
          skipped_invalid: number;
          no_link_col: number;
        }
      >;
      workbook: string;
    }>("/watch/import-from-excel", workbook ? { workbook } : {}),
  refresh: () => post<{ status: string; workbook: string; started_at: string }>("/refresh"),
  verify: () => post<{ total: number; fresh: number; stale: number; errors: number; drift_rows: { row: number; process_id: string }[] }>("/verify"),
};
