/**
 * Llamadas directas al portal abierto de datos del Estado Colombiano
 * (datos.gov.co, Socrata SODA API). El browser puede consumir estos
 * endpoints sin proxy porque CORS está abierto para todos los datasets
 * públicos.
 *
 * Datasets que usamos:
 *
 *   - `jbjy-vk9h` — Contratos electrónicos (SECOP II) por NIT
 *   - `p6dx-8zbt` — Procesos de contratación (SECOP II) por NIT
 *   - `rpmr-utcd` — SECOP Integrado (SECOP I + II + procesos finalizados)
 *
 * Filosofía cardinal: SECOP es la única fuente de verdad. Lo que devuelve
 * el API es lo que mostramos. Si un campo viene null, lo dejamos null —
 * la UI muestra "—" honesto.
 */

const BASE = "https://www.datos.gov.co/resource";
const FEAB_NIT = "901148337";
const PAGE_SIZE = 1000; // cap de Socrata por request

/**
 * Aplica todos los filtros sobre un endpoint Socrata y devuelve la unión
 * paginada (sin cap superior — los datasets del FEAB tienen ~1000 filas
 * cada uno, así que rara vez paginamos más de una vez).
 */
async function fetchAll<T>(
  resource: string,
  params: Record<string, string> = {}
): Promise<T[]> {
  const all: T[] = [];
  let offset = 0;
  // Hard cap de seguridad: 50 páginas (50000 filas).
  for (let page = 0; page < 50; page++) {
    const qp = new URLSearchParams({
      ...params,
      $limit: String(PAGE_SIZE),
      $offset: String(offset),
    });
    const url = `${BASE}/${resource}.json?${qp.toString()}`;
    const res = await fetch(url, {
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    if (!res.ok) {
      throw new Error(
        `Socrata ${resource} → ${res.status} ${res.statusText}`
      );
    }
    const rows = (await res.json()) as T[];
    all.push(...rows);
    if (rows.length < PAGE_SIZE) break;
    offset += PAGE_SIZE;
  }
  return all;
}

/**
 * Dataset Contratos electrónicos. Una fila por contrato. Incluye id,
 * proveedor, valor, fechas, estado, modalidad, etc.
 */
export interface SocrataContrato {
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
  urlproceso?: string | { url: string } | null;
  [key: string]: unknown;
}

export async function fetchFeabContratos(): Promise<SocrataContrato[]> {
  const rows = await fetchAll<SocrataContrato>("jbjy-vk9h", {
    nit_entidad: FEAB_NIT,
  });
  // Normalizo `urlproceso`: a veces viene como objeto `{ url: "..." }` y
  // a veces como string crudo. La UI quiere string.
  return rows.map((r) => ({
    ...r,
    urlproceso: typeof r.urlproceso === "object" && r.urlproceso !== null
      ? (r.urlproceso as { url?: string }).url ?? ""
      : (r.urlproceso as string | undefined) ?? "",
  }));
}

/**
 * Dataset Procesos. Una fila por proceso (notice_uid).
 */
export interface SocrataProceso {
  id_del_proceso?: string;
  notice_uid?: string;
  nombre_del_procedimiento?: string;
  estado_del_procedimiento?: string;
  fase?: string;
  modalidad_de_contratacion?: string;
  url_proceso?: string;
  fecha_publicacion?: string;
  fecha_apertura_de_proceso?: string;
  valor_total_adjudicacion?: string;
  [key: string]: unknown;
}

export async function fetchFeabProcesos(): Promise<SocrataProceso[]> {
  return fetchAll<SocrataProceso>("p6dx-8zbt", {
    nit_entidad: FEAB_NIT,
  });
}

/**
 * Dataset SECOP Integrado. Combina SECOP I + II + procesos finalizados.
 * Es la fuente más completa para procesos viejos.
 */
export interface SocrataIntegrado {
  estado_del_proceso?: string;
  valor_contrato?: string;
  nom_raz_social_contratista?: string;
  fecha_de_firma_del_contrato?: string;
  fecha_inicio_ejecuci_n?: string;
  fecha_fin_ejecuci_n?: string;
  modalidad_de_contrataci_n?: string;
  tipo_de_contrato?: string;
  numero_del_contrato?: string;
  numero_de_proceso?: string;
  objeto_a_contratar?: string;
  url_contrato?: string | { url: string };
  [key: string]: unknown;
}

export async function fetchIntegrado(): Promise<SocrataIntegrado[]> {
  const rows = await fetchAll<SocrataIntegrado>("rpmr-utcd", {
    nit_de_la_entidad: FEAB_NIT,
  });
  return rows.map((r) => ({
    ...r,
    url_contrato: typeof r.url_contrato === "object" && r.url_contrato !== null
      ? (r.url_contrato as { url?: string }).url ?? ""
      : (r.url_contrato as string | undefined) ?? "",
  }));
}

/**
 * Helper: extrae el `notice_uid` de una `url_contrato` del Integrado.
 * El URL contiene `noticeUID=CO1.NTC.X` o `PPI=CO1.PPI.X`.
 */
export function extractNoticeUid(url: string | undefined): string | null {
  if (!url) return null;
  const decoded = decodeURIComponent(url);
  const m = decoded.match(/CO1\.(NTC|PPI|PCCNTR|REQ)\.\d+/i);
  return m ? m[0].toUpperCase() : null;
}
