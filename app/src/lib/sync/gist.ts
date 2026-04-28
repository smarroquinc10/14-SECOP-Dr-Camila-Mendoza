"use client";

/**
 * Cliente del Gist privado para sincronización entre máquinas.
 *
 * Cardinal (2026-04-28 · opción C-light de Sergio):
 *   - PUSH: serializa watch_list + audit_log (firmados SHA-256), cifra
 *     el JSON entero con la passphrase, hace PATCH al gist.
 *   - PULL: GET del gist, descifra, devuelve el state. Si el gist está
 *     vacío (`{}`), devuelve null sin error.
 *
 * Diseño:
 *   - El JSON cifrado en el gist es opaco para GitHub · solo se descifra
 *     en el browser de Cami con la passphrase. Defensa en profundidad.
 *   - Cada PUSH actualiza un timestamp `last_pushed_at` que sirve para
 *     conflict detection en otra máquina (si traés un state con
 *     last_pushed_at más nuevo que el local edited_at, aviso a la Dra).
 *   - Si la red falla, push y pull retornan errores · IndexedDB sigue
 *     siendo la verdad local · cuando vuelva la red, el próximo edit
 *     dispara nuevo push.
 */

import { decryptString, encryptString } from "./crypto";
import {
  ENCRYPTED_PAT,
  GIST_FILENAME,
  GIST_ID,
  isSyncConfigured,
} from "./config";

export interface SyncedState {
  watch_list: unknown[];
  audit_log: unknown[];
  observaciones?: unknown[];
  last_pushed_at: string;
  last_pushed_by?: string;
  schema_version: 1;
}

/**
 * Descifra el PAT con la passphrase. Cachea el resultado en memoria
 * por la vida de la pestaña · evita re-derivar PBKDF2 200K iter en
 * cada push.
 */
let _patCache: { passphrase: string; pat: string } | null = null;
async function getPAT(passphrase: string): Promise<string> {
  if (_patCache && _patCache.passphrase === passphrase) return _patCache.pat;
  if (!ENCRYPTED_PAT) throw new Error("Sync no configurado (ENCRYPTED_PAT vacío)");
  const pat = await decryptString(ENCRYPTED_PAT, passphrase);
  _patCache = { passphrase, pat };
  return pat;
}

/**
 * Sube el state al gist privado. Cifra el JSON entero con la passphrase
 * antes de enviarlo a GitHub. Devuelve el revision_id del gist (útil
 * para tracking).
 */
export async function pushToGist(
  state: Omit<SyncedState, "last_pushed_at" | "schema_version">,
  passphrase: string,
): Promise<{ ok: true; revision: string } | { ok: false; error: string }> {
  if (!isSyncConfigured()) {
    return { ok: false, error: "sync no configurado" };
  }
  try {
    const pat = await getPAT(passphrase);
    const fullState: SyncedState = {
      ...state,
      last_pushed_at: new Date().toISOString(),
      schema_version: 1,
    };
    const ciphertext = await encryptString(JSON.stringify(fullState), passphrase);

    const res = await fetch(`https://api.github.com/gists/${GIST_ID}`, {
      method: "PATCH",
      headers: {
        Authorization: `Bearer ${pat}`,
        Accept: "application/vnd.github+json",
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
      },
      body: JSON.stringify({
        files: { [GIST_FILENAME]: { content: ciphertext } },
      }),
    });
    if (!res.ok) {
      const txt = await res.text().catch(() => "");
      return {
        ok: false,
        error: `GitHub PATCH ${res.status}: ${txt.slice(0, 200)}`,
      };
    }
    const body = (await res.json()) as { history?: { version: string }[] };
    const revision = body.history?.[0]?.version ?? "unknown";
    return { ok: true, revision };
  } catch (e) {
    return {
      ok: false,
      error: e instanceof Error ? e.message : String(e),
    };
  }
}

/**
 * Trae el state del gist privado · descifra · devuelve el JSON parseado.
 * Si el gist está vacío o tiene `{}`, devuelve `null` sin error.
 */
export async function pullFromGist(
  passphrase: string,
): Promise<
  | { ok: true; state: SyncedState | null }
  | { ok: false; error: string }
> {
  if (!isSyncConfigured()) {
    return { ok: true, state: null };
  }
  try {
    const pat = await getPAT(passphrase);
    const res = await fetch(`https://api.github.com/gists/${GIST_ID}`, {
      method: "GET",
      headers: {
        Authorization: `Bearer ${pat}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
      },
    });
    if (!res.ok) {
      const txt = await res.text().catch(() => "");
      return {
        ok: false,
        error: `GitHub GET ${res.status}: ${txt.slice(0, 200)}`,
      };
    }
    const body = (await res.json()) as {
      files?: Record<string, { content?: string } | undefined>;
    };
    const file = body.files?.[GIST_FILENAME];
    const content = (file?.content ?? "").trim();
    if (!content || content === "{}") {
      return { ok: true, state: null };
    }
    const decrypted = await decryptString(content, passphrase);
    const parsed = JSON.parse(decrypted) as SyncedState;
    return { ok: true, state: parsed };
  } catch (e) {
    return {
      ok: false,
      error: e instanceof Error ? e.message : String(e),
    };
  }
}
