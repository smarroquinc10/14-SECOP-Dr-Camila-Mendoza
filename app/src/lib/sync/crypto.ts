"use client";

/**
 * Cifrado simétrico AES-GCM 256 con key derivada de la passphrase.
 *
 * Cardinal (2026-04-28 · opción C-light de Sergio):
 *   - Usado para cifrar el PAT de GitHub que vive en el bundle público.
 *   - También cifra el JSON del state antes de subirlo al gist privado
 *     (defensa en profundidad · si por error el gist se vuelve público
 *     algún día, el contenido sigue siendo inútil sin la passphrase).
 *
 * Importante:
 *   - Se usa un SALT distinto al de `access-gate.tsx` para que el hash
 *     de autenticación (público) NO sea la misma cosa que la key de
 *     cifrado. Aunque alguien obtenga `EXPECTED_HASH` del bundle, no
 *     tiene la key AES de los datos cifrados.
 *   - PBKDF2-SHA256 200_000 iteraciones · acorde con el resto del
 *     proyecto · ralentiza brute force offline.
 *   - IV random de 12 bytes por cada encrypt · recomendación NIST GCM.
 *   - Output base64 en formato `iv.ciphertext` (con el `.` como
 *     separador) para serialización trivial.
 */

const SYNC_KEY_SALT = "FEAB-Sync-Gist-Encryption-Cami-2026";
const ITERATIONS = 200_000;

async function deriveAesKey(passphrase: string): Promise<CryptoKey> {
  const enc = new TextEncoder();
  const keyMaterial = await crypto.subtle.importKey(
    "raw",
    enc.encode(passphrase),
    "PBKDF2",
    false,
    ["deriveKey"],
  );
  return crypto.subtle.deriveKey(
    {
      name: "PBKDF2",
      salt: enc.encode(SYNC_KEY_SALT),
      iterations: ITERATIONS,
      hash: "SHA-256",
    },
    keyMaterial,
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt", "decrypt"],
  );
}

function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  for (let i = 0; i < bytes.byteLength; i += 1) {
    binary += String.fromCharCode(bytes[i]);
  }
  // btoa es ASCII-only, ya estamos pasando bytes como chars
  return btoa(binary);
}

function base64ToBytes(b64: string): Uint8Array {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

/**
 * Cifra una string con AES-GCM 256. Devuelve `iv_base64.ct_base64`.
 * IV se genera fresco en cada llamada · es OBLIGATORIO no reusarlos.
 */
export async function encryptString(
  plaintext: string,
  passphrase: string,
): Promise<string> {
  const key = await deriveAesKey(passphrase);
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ct = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv },
    key,
    new TextEncoder().encode(plaintext),
  );
  return `${bytesToBase64(iv)}.${bytesToBase64(new Uint8Array(ct))}`;
}

/**
 * Descifra un payload `iv.ct` producido por encryptString. Throws si
 * la passphrase es incorrecta (AES-GCM auth tag falla) o si el formato
 * del payload está corrupto.
 */
export async function decryptString(
  payload: string,
  passphrase: string,
): Promise<string> {
  const parts = payload.split(".");
  if (parts.length !== 2) {
    throw new Error("Formato de ciphertext inválido (esperaba iv.ct)");
  }
  const iv = base64ToBytes(parts[0]);
  const ct = base64ToBytes(parts[1]);
  const key = await deriveAesKey(passphrase);
  const pt = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: iv as BufferSource },
    key,
    ct as BufferSource,
  );
  return new TextDecoder().decode(pt);
}
