"use client";

/**
 * Configuración del sync con Gist (opción C-light · Sergio 2026-04-28).
 *
 * - GIST_ID: ID del gist privado donde vive el state cifrado.
 * - ENCRYPTED_PAT: el PAT de GitHub (scope `gist`) cifrado con AES-GCM
 *   usando la passphrase del dashboard (`cami2026`). Cualquiera con el
 *   bundle puede ver el ciphertext, pero sin la passphrase no lo descifra.
 *
 * Si alguno de los dos está vacío → sync OFF · la app sigue funcionando
 * solo con IndexedDB local (cardinal-honesto · 0 break).
 *
 * Para configurar:
 *   1. Crear PAT en https://github.com/settings/tokens (scope: gist).
 *   2. Crear gist secret en https://gist.github.com/ con archivo
 *      feab-state.json y contenido `{}`.
 *   3. Cifrar el PAT corriendo en la consola del browser:
 *        await encryptString("ghp_xxx...", "cami2026")
 *      O usando el endpoint local /api/encrypt-pat (script Python aparte).
 *   4. Pegar el ciphertext acá como ENCRYPTED_PAT y el ID del gist
 *      como GIST_ID.
 */

export const GIST_ID = "c72a296f570313dbe4a983f6d41211ba";
export const ENCRYPTED_PAT =
  "hbvX+d+d4A39WfM+.nRiYsO7pQBT61nxRtS/UDrjChOpIjkHKG1ZMWCxHeOfxtzyw/he3Yjgbo6p1eYYlM95dO6rxDNo=";

export const GIST_FILENAME = "feab-state.json";

export function isSyncConfigured(): boolean {
  return GIST_ID.length > 0 && ENCRYPTED_PAT.length > 0;
}
