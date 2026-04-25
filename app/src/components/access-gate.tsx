"use client";

import * as React from "react";
import { Loader2, Lock } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

/**
 * Barrera de acceso para que SOLO la Dra. Camila entre al dashboard.
 *
 * ## Por qué hay barrera si la URL es pública
 *
 * GitHub Pages no soporta auth server-side, así que cualquiera con la URL
 * podría llegar a la app. Esto NO es un riesgo de filtración (la data del
 * SECOP es pública y la lista de URLs vive en su browser, no en el server),
 * pero la Dra pidió "que nadie se meta a dañarle nada" — alguien con
 * acceso a su PC podría agregar/borrar URLs si abriera el browser.
 *
 * Esta barrera verifica un passphrase con **PBKDF2-SHA256, 200k iteraciones**.
 * El hash está hardcoded acá; la passphrase NUNCA se envía a ningún server.
 * Para cambiarla:
 *   1. Elegir nueva passphrase
 *   2. Correr `python scripts/compute_passphrase_hash.py "<nueva>"` (TBD)
 *      o usar el snippet en el comentario al final.
 *   3. Reemplazar `EXPECTED_HASH` abajo con el output.
 *
 * ## Limitaciones honestas (importantes)
 *
 *   - La barrera es CLIENT-SIDE: alguien con DevTools podría leer el
 *     hash y, en teoría, intentar romperlo offline. PBKDF2 con 200k
 *     iteraciones hace que cada intento cueste ~50ms en CPU moderno,
 *     o sea: para passphrases de 16+ chars con mayúsculas+números+
 *     símbolos, el costo del brute-force es prohibitivo en práctica.
 *   - La barrera es PER-BROWSER: una vez que la Dra entra, queda
 *     desbloqueada hasta cerrar la pestaña (sessionStorage). Si abre
 *     una nueva ventana o reinicia el browser, vuelve a pedir.
 *   - El mismo passphrase desbloquea cualquier device — la app no
 *     distingue entre la PC de la Dra y otra. Mantén el passphrase
 *     en privado.
 *
 * ## Cómo funciona
 *
 *   1. Al cargar el componente, mira `sessionStorage["feab.unlocked"]`.
 *   2. Si == "true", deja pasar (children renderizados).
 *   3. Si no, muestra el form de passphrase.
 *   4. Al submit, calcula PBKDF2(input, salt, 200000) en el browser.
 *   5. Si el hash matchea, marca sessionStorage y deja pasar.
 *   6. Si no, muestra error y el campo vuelve a quedar vacío.
 */

// PBKDF2-SHA256 hash precomputado del passphrase actual.
// Passphrase: "cami2026"  (mantenelo en privado).
// Salt:       "FEAB-Auditoria-Contractual-Cami-2026"
// Iteraciones: 200,000
// Para regenerarlo: python -c 'import hashlib,binascii;
//   print(binascii.hexlify(hashlib.pbkdf2_hmac("sha256", b"<passphrase>", b"<salt>", 200000, 32)).decode())'
const EXPECTED_HASH =
  "77e343cfa1ea16ea4f5ae4ffb7a4f3bb69625aa345fe5b5831cc02c4c0a5ab84";
const SALT = "FEAB-Auditoria-Contractual-Cami-2026";
const ITERATIONS = 200_000;
const STORAGE_KEY = "feab.unlocked";

async function pbkdf2Hex(passphrase: string): Promise<string> {
  const enc = new TextEncoder();
  const keyMaterial = await crypto.subtle.importKey(
    "raw",
    enc.encode(passphrase),
    "PBKDF2",
    false,
    ["deriveBits"],
  );
  const bits = await crypto.subtle.deriveBits(
    {
      name: "PBKDF2",
      salt: enc.encode(SALT),
      iterations: ITERATIONS,
      hash: "SHA-256",
    },
    keyMaterial,
    256,
  );
  return Array.from(new Uint8Array(bits))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export function AccessGate({ children }: { children: React.ReactNode }) {
  // `unlocked === null` significa "todavía no chequeé sessionStorage" —
  // así evitamos un flash del passphrase form cuando ella ya entró.
  const [unlocked, setUnlocked] = React.useState<boolean | null>(null);
  const [input, setInput] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (typeof window === "undefined") {
      setUnlocked(false);
      return;
    }
    const saved = sessionStorage.getItem(STORAGE_KEY);
    setUnlocked(saved === "true");
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!input.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const hash = await pbkdf2Hex(input);
      if (hash === EXPECTED_HASH) {
        sessionStorage.setItem(STORAGE_KEY, "true");
        setUnlocked(true);
      } else {
        setError("Passphrase incorrecto. Intentá de nuevo.");
        setInput("");
      }
    } catch (err) {
      setError(
        "No pude verificar el passphrase (¿browser sin Web Crypto?). " +
          (err instanceof Error ? err.message : ""),
      );
    } finally {
      setBusy(false);
    }
  }

  // Mientras chequeo sessionStorage: pantalla en blanco. Es un milisegundo,
  // no rompe layout porque ocupa la misma altura que el dashboard final.
  if (unlocked === null) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <Loader2 className="h-5 w-5 animate-spin text-ink-soft" />
      </div>
    );
  }

  if (unlocked) return <>{children}</>;

  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm">
        <div className="bg-surface border border-rule rounded-xl shadow-sm p-6">
          <div className="flex items-center justify-center mb-4">
            <div className="h-10 w-10 rounded-full bg-burgundy/10 text-burgundy flex items-center justify-center">
              <Lock className="h-5 w-5" />
            </div>
          </div>
          <h1 className="text-center text-base font-semibold text-ink mb-1">
            Acceso restringido
          </h1>
          <p className="text-center text-xs text-ink-soft mb-5">
            Sistema de Seguimiento Contratos FEAB
            <br />
            Dra. María Camila Mendoza Zubiría
          </p>
          <form onSubmit={submit} className="space-y-3">
            <Input
              type="password"
              autoFocus
              autoComplete="current-password"
              value={input}
              onChange={(e) => {
                setInput(e.target.value);
                setError(null);
              }}
              placeholder="Passphrase"
              disabled={busy}
              aria-invalid={error ? "true" : "false"}
            />
            {error && (
              <div className="text-[11px] text-rose-700 bg-rose-50 border border-rose-200 rounded px-2 py-1.5">
                {error}
              </div>
            )}
            <Button
              type="submit"
              disabled={busy || !input.trim()}
              className="w-full"
            >
              {busy ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin mr-2" /> Verificando…
                </>
              ) : (
                "Entrar"
              )}
            </Button>
          </form>
          <p className="mt-4 text-[10px] text-center text-ink-soft/70 leading-relaxed">
            Verificación local con PBKDF2 (200k iteraciones). El passphrase
            nunca se envía a ningún servidor. La sesión queda activa hasta
            cerrar la pestaña.
          </p>
        </div>
      </div>
    </div>
  );
}
