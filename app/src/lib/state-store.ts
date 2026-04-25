/**
 * IndexedDB-backed state store for the FEAB dashboard.
 *
 * ## Por qué IndexedDB y no localStorage
 *
 * localStorage tiene un cap de ~5MB por origen y serializa solo strings.
 * Nuestro audit log puede crecer a varios MB de JSONL y necesita queries
 * por timestamp/op. IndexedDB nos da:
 *  - Stores con índices (range queries por fecha)
 *  - Tamaño en GBs (limitado por cuota del browser, típica ~10% del disco)
 *  - Async API, no bloquea el thread principal
 *  - Persistencia entre sesiones igual que localStorage
 *
 * ## Schema (versión 1)
 *
 *   - `watch_list` (keyPath: `url`)
 *       Espejo del watched_urls.json: 491 URLs de procesos SECOP que la
 *       Dra. sigue. Inicialmente se siembra desde /data/watched_urls.json
 *       en el primer arranque; después esta store es fuente de verdad.
 *
 *   - `audit_log` (auto-key)
 *       Hash-chained log inmutable: cada operación (add/edit/remove)
 *       agrega una entry con prev_hash + hash. La Dra. (o un auditor)
 *       puede verificar el chain con `verifyAuditChain()`.
 *
 *   - `observaciones` (keyPath: `notice_uid`)
 *       Notas manuales de la Dra. por proceso. Independiente del watch
 *       list (puede tener obs sobre un proceso que no esté en watch list).
 *
 *   - `meta` (keyPath: `key`)
 *       Pares key/value para flags: `seed_version`, `last_seed_at`, etc.
 *
 * ## Filosofía cardinal preservada
 *
 *  - **El audit log nunca se sobreescribe**: append-only, hash-chain
 *    rompe si alguien edita una entry vieja.
 *  - **Excel sigue siendo solo vigencia + link**: la store no acepta
 *    campos como `numero_contrato` ni `valor` desde input usuario.
 *  - **Honestidad sobre completitud**: si no hay observación para un
 *    proceso, devolvemos `null`, nunca un placeholder inventado.
 */

const DB_NAME = "feab-dashboard";
const DB_VERSION = 1;

export interface WatchedItemRow {
  url: string;
  process_id: string | null;
  notice_uid: string | null;
  sheets: string[];
  vigencias: string[];
  appearances: Array<{
    sheet: string;
    vigencia: string | null;
    row: number | null;
    url: string;
  }>;
  added_at: string;
  edited_at?: string;
  note: string | null;
}

export interface AuditEntry {
  id?: number; // auto-increment
  ts: string;
  op: "fill" | "replace" | "watch_add" | "watch_edit" | "watch_remove" |
      "obs_set" | "obs_clear" | "verify" | "boot" | "seed";
  url?: string | null;
  process_id?: string | null;
  field?: string | null;
  old?: unknown;
  new?: unknown;
  source?: string | null;
  hash: string;
  prev_hash: string;
}

export interface Observacion {
  notice_uid: string;
  text: string;
  updated_at: string;
}

interface MetaRow {
  key: string;
  value: unknown;
  updated_at: string;
}

let _dbPromise: Promise<IDBDatabase> | null = null;

function openDb(): Promise<IDBDatabase> {
  if (_dbPromise) return _dbPromise;
  _dbPromise = new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      // Crear stores en la migración de versión 0 → 1.
      // Cada upgrade futuro agrega su bloque if (oldVersion < N).
      if (!db.objectStoreNames.contains("watch_list")) {
        const watchStore = db.createObjectStore("watch_list", { keyPath: "url" });
        watchStore.createIndex("by_process", "process_id", { unique: false });
        watchStore.createIndex("by_notice", "notice_uid", { unique: false });
      }
      if (!db.objectStoreNames.contains("audit_log")) {
        const auditStore = db.createObjectStore("audit_log", {
          keyPath: "id",
          autoIncrement: true,
        });
        auditStore.createIndex("by_ts", "ts", { unique: false });
        auditStore.createIndex("by_op", "op", { unique: false });
      }
      if (!db.objectStoreNames.contains("observaciones")) {
        db.createObjectStore("observaciones", { keyPath: "notice_uid" });
      }
      if (!db.objectStoreNames.contains("meta")) {
        db.createObjectStore("meta", { keyPath: "key" });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
  return _dbPromise;
}

// ---- Helpers genéricos -----------------------------------------------------

async function getAll<T>(store: string): Promise<T[]> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(store, "readonly");
    const req = tx.objectStore(store).getAll();
    req.onsuccess = () => resolve(req.result as T[]);
    req.onerror = () => reject(req.error);
  });
}

async function get<T>(store: string, key: IDBValidKey): Promise<T | undefined> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(store, "readonly");
    const req = tx.objectStore(store).get(key);
    req.onsuccess = () => resolve(req.result as T | undefined);
    req.onerror = () => reject(req.error);
  });
}

async function put<T>(store: string, value: T): Promise<void> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(store, "readwrite");
    tx.objectStore(store).put(value);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

async function del(store: string, key: IDBValidKey): Promise<void> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(store, "readwrite");
    tx.objectStore(store).delete(key);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

async function clear(store: string): Promise<void> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(store, "readwrite");
    tx.objectStore(store).clear();
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

// ---- Hash chain utilities (Web Crypto, no deps) ---------------------------

const ZERO_HASH = "0".repeat(64);

async function sha256Hex(input: string): Promise<string> {
  const buf = new TextEncoder().encode(input);
  const digest = await crypto.subtle.digest("SHA-256", buf);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function canonicalize(entry: AuditEntry): string {
  const { hash: _hash, id: _id, ...rest } = entry;
  void _hash; void _id;
  // Ordeno keys para que el hash sea determinista.
  const ordered: Record<string, unknown> = {};
  for (const k of Object.keys(rest).sort()) {
    ordered[k] = (rest as Record<string, unknown>)[k];
  }
  return JSON.stringify(ordered);
}

async function lastHash(): Promise<string> {
  const all = await getAll<AuditEntry>("audit_log");
  if (all.length === 0) return ZERO_HASH;
  const sorted = all.slice().sort((a, b) => (a.id ?? 0) - (b.id ?? 0));
  return sorted[sorted.length - 1].hash;
}

// ---- Public API: watch list -----------------------------------------------

/**
 * Bootstrap inicial: si la DB nunca fue sembrada, copiar /data/watched_urls.json
 * a la store. Posteriores boots ven `seed_version` y bypasean.
 */
export async function ensureSeed(seedVersion: string): Promise<{
  seeded: boolean;
  itemCount: number;
}> {
  const meta = await get<MetaRow>("meta", "seed_version");
  if (meta?.value === seedVersion) {
    const all = await getAll<WatchedItemRow>("watch_list");
    return { seeded: false, itemCount: all.length };
  }

  // Primer load (o version mismatch). Bajo el seed.
  const seedUrl = withBasePath("/data/watched_urls.json");
  const res = await fetch(seedUrl);
  if (!res.ok) {
    throw new Error(`No pude leer el seed (${res.status} ${res.statusText})`);
  }
  const items: WatchedItemRow[] = await res.json();

  // Vacío la store y la repueblo. Esto NO toca audit_log ni observaciones —
  // esas son de la usuaria, no del seed.
  await clear("watch_list");
  const db = await openDb();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction("watch_list", "readwrite");
    const store = tx.objectStore("watch_list");
    for (const it of items) store.put(it);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
  await put<MetaRow>("meta", {
    key: "seed_version",
    value: seedVersion,
    updated_at: new Date().toISOString(),
  });

  // Audit entry: marcar el evento de seeding.
  const prev = await lastHash();
  const entry: AuditEntry = {
    ts: new Date().toISOString(),
    op: "seed",
    new: { items_seeded: items.length, seed_version: seedVersion },
    hash: "",
    prev_hash: prev,
  };
  entry.hash = await sha256Hex(canonicalize(entry) + prev);
  await put<AuditEntry>("audit_log", entry);

  return { seeded: true, itemCount: items.length };
}

export async function listWatched(): Promise<WatchedItemRow[]> {
  return getAll<WatchedItemRow>("watch_list");
}

export async function getWatched(url: string): Promise<WatchedItemRow | undefined> {
  return get<WatchedItemRow>("watch_list", url);
}

export async function addWatched(input: {
  url: string;
  vigencia: string;
  sheet?: string;
  note?: string | null;
}): Promise<WatchedItemRow> {
  const existing = await get<WatchedItemRow>("watch_list", input.url);
  if (existing) {
    throw new Error("Esa URL ya está en tu lista.");
  }
  // process_id se infiere del URL (CO1.NTC.X / CO1.PCCNTR.X / etc.)
  const process_id = inferProcessId(input.url);
  const sheet = input.sheet ?? `FEAB ${input.vigencia}`;
  const item: WatchedItemRow = {
    url: input.url,
    process_id,
    notice_uid: process_id?.startsWith("CO1.NTC.") ? process_id : null,
    sheets: [sheet],
    vigencias: [input.vigencia],
    appearances: [
      { sheet, vigencia: input.vigencia, row: null, url: input.url },
    ],
    added_at: new Date().toISOString(),
    note: input.note ?? null,
  };
  await put<WatchedItemRow>("watch_list", item);
  await appendAudit({
    op: "watch_add",
    url: input.url,
    process_id,
    new: { vigencia: input.vigencia, sheet, note: input.note ?? null },
  });
  return item;
}

export async function editWatched(
  oldUrl: string,
  newUrl: string,
  note?: string | null
): Promise<WatchedItemRow> {
  const existing = await get<WatchedItemRow>("watch_list", oldUrl);
  if (!existing) throw new Error("No encontré ese URL en tu lista.");
  if (oldUrl === newUrl && (note ?? null) === existing.note) {
    return existing;
  }
  // Si la URL cambió, removemos la fila vieja antes de poner la nueva
  // (porque keyPath = url).
  if (oldUrl !== newUrl) {
    await del("watch_list", oldUrl);
  }
  const updated: WatchedItemRow = {
    ...existing,
    url: newUrl,
    process_id: inferProcessId(newUrl),
    note: note ?? existing.note ?? null,
    edited_at: new Date().toISOString(),
    appearances: existing.appearances.map((a) =>
      a.url === oldUrl ? { ...a, url: newUrl } : a
    ),
  };
  await put<WatchedItemRow>("watch_list", updated);
  await appendAudit({
    op: "watch_edit",
    url: newUrl,
    process_id: updated.process_id,
    old: { url: oldUrl, note: existing.note },
    new: { url: newUrl, note: updated.note },
  });
  return updated;
}

export async function removeWatched(url: string): Promise<void> {
  const existing = await get<WatchedItemRow>("watch_list", url);
  if (!existing) return;
  await del("watch_list", url);
  await appendAudit({
    op: "watch_remove",
    url,
    process_id: existing.process_id,
    old: existing,
  });
}

// ---- Public API: audit log -------------------------------------------------

export async function appendAudit(input: Omit<AuditEntry, "ts" | "hash" | "prev_hash">): Promise<AuditEntry> {
  const prev = await lastHash();
  const entry: AuditEntry = {
    ...input,
    ts: new Date().toISOString(),
    hash: "",
    prev_hash: prev,
  };
  entry.hash = await sha256Hex(canonicalize(entry) + prev);
  await put<AuditEntry>("audit_log", entry);
  return entry;
}

export async function listAudit(limit = 500): Promise<AuditEntry[]> {
  const all = await getAll<AuditEntry>("audit_log");
  // Ordeno por id descendente y limito.
  return all
    .slice()
    .sort((a, b) => (b.id ?? 0) - (a.id ?? 0))
    .slice(0, limit);
}

export async function totalAuditEntries(): Promise<number> {
  const all = await getAll<AuditEntry>("audit_log");
  return all.length;
}

export async function verifyAuditChain(): Promise<{
  intact: boolean;
  problems: string[];
  total: number;
}> {
  const all = await getAll<AuditEntry>("audit_log");
  const sorted = all.slice().sort((a, b) => (a.id ?? 0) - (b.id ?? 0));
  const problems: string[] = [];
  let prev = ZERO_HASH;
  for (let i = 0; i < sorted.length; i++) {
    const e = sorted[i];
    const expected = await sha256Hex(canonicalize(e) + prev);
    if (e.hash !== expected) {
      problems.push(`Entry ${i + 1} (${e.ts}): hash inválido`);
    }
    if (e.prev_hash !== prev) {
      problems.push(`Entry ${i + 1} (${e.ts}): prev_hash no coincide con la entry anterior`);
    }
    prev = e.hash;
  }
  return { intact: problems.length === 0, problems, total: sorted.length };
}

// ---- Public API: observaciones --------------------------------------------

export async function getObservacion(notice_uid: string): Promise<string | null> {
  const o = await get<Observacion>("observaciones", notice_uid);
  return o?.text ?? null;
}

export async function setObservacion(notice_uid: string, text: string): Promise<void> {
  const old = await get<Observacion>("observaciones", notice_uid);
  if (text.trim() === "") {
    if (old) {
      await del("observaciones", notice_uid);
      await appendAudit({
        op: "obs_clear",
        process_id: notice_uid,
        old: old.text,
      });
    }
    return;
  }
  await put<Observacion>("observaciones", {
    notice_uid,
    text,
    updated_at: new Date().toISOString(),
  });
  await appendAudit({
    op: "obs_set",
    process_id: notice_uid,
    old: old?.text ?? null,
    new: text,
  });
}

// ---- Public API: meta -----------------------------------------------------

export async function getMeta<T>(key: string): Promise<T | undefined> {
  const row = await get<MetaRow>("meta", key);
  return row?.value as T | undefined;
}

export async function setMeta<T>(key: string, value: T): Promise<void> {
  await put<MetaRow>("meta", {
    key,
    value,
    updated_at: new Date().toISOString(),
  });
}

// ---- URL parsing helper ---------------------------------------------------

const NTC_RE = /CO1\.NTC\.[\d]+/i;
const PCCNTR_RE = /CO1\.PCCNTR\.[\d]+/i;
const PPI_RE = /CO1\.PPI\.[\d]+/i;
const REQ_RE = /CO1\.REQ\.[\d]+/i;

export function inferProcessId(url: string): string | null {
  if (!url) return null;
  const decoded = decodeURIComponent(url);
  for (const re of [NTC_RE, PCCNTR_RE, PPI_RE, REQ_RE]) {
    const m = decoded.match(re);
    if (m) return m[0].toUpperCase();
  }
  return null;
}

// ---- Path helpers (GitHub Pages basePath compatibility) -------------------

/**
 * Si la app vive en https://user.github.io/repo-name/, los fetch a
 * /data/X.json se rompen porque resuelven al root del dominio.
 * Esta función prefija con `process.env.NEXT_PUBLIC_BASE_PATH` cuando está
 * definida (típicamente en el build de Vercel/GitHub Pages).
 */
export function withBasePath(path: string): string {
  const base = process.env.NEXT_PUBLIC_BASE_PATH ?? "";
  if (!base) return path;
  if (path.startsWith("/")) return `${base}${path}`;
  return `${base}/${path}`;
}
