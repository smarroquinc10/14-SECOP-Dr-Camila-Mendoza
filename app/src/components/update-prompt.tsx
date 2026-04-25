"use client";

/**
 * Auto-updater UI for the Tauri MSI build.
 *
 * Mounted from `layout.tsx` so it lives next to every page. Polls
 * GitHub Releases on startup + every 4 hours. When a newer signed
 * version is found, it shows a small bottom-right card with two
 * buttons:
 *
 *   - "Más tarde": dismiss until next session.
 *   - "Actualizar": download + install + auto-relaunch.
 *
 * The Dra. only ever sees ONE button to click. Same UX pattern as
 * Word/Chrome/Slack auto-updates.
 *
 * In dev (`npm run dev` in a normal browser, no Tauri runtime), the
 * component detects the missing `__TAURI_INTERNALS__` global and
 * stays silent — never bothers the developer.
 */

import { useEffect, useState } from "react";
import type { Update } from "@tauri-apps/plugin-updater";

type Status =
  | "idle"
  | "checking"
  | "available"
  | "downloading"
  | "installing"
  | "error";

interface AvailableUpdate {
  version: string;
  notes: string;
  // The plugin's `Update` instance — we keep the official type so the
  // signature of `downloadAndInstall` matches whatever Tauri exposes
  // (avoids a brittle hand-rolled callback shape).
  installer: Update;
}

function isInTauri(): boolean {
  if (typeof window === "undefined") return false;
  return "__TAURI_INTERNALS__" in window;
}

export function UpdatePrompt() {
  const [status, setStatus] = useState<Status>("idle");
  const [available, setAvailable] = useState<AvailableUpdate | null>(null);
  const [progress, setProgress] = useState<number>(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isInTauri()) return;

    let cancelled = false;

    const tryCheck = async () => {
      try {
        setStatus((s) => (s === "idle" ? "checking" : s));
        // Dynamic import keeps `next build` happy on a non-Tauri
        // machine (the plugin only resolves at runtime).
        const { check } = await import("@tauri-apps/plugin-updater");
        const update = await check();
        if (cancelled) return;
        if (update) {
          setAvailable({
            version: update.version,
            notes: update.body ?? "",
            installer: update,
          });
          setStatus("available");
        } else {
          setStatus("idle");
        }
      } catch (err) {
        // Silent: the user shouldn't see "no internet" errors when
        // they didn't ask to update. We log for debugging.
        console.warn("[update-prompt] check failed:", err);
        setStatus("idle");
      }
    };

    void tryCheck();
    // Re-check every 4 hours so a long-running session catches releases.
    const interval = setInterval(tryCheck, 4 * 60 * 60 * 1000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  const startUpdate = async () => {
    if (!available) return;
    try {
      setStatus("downloading");
      setProgress(0);
      let downloaded = 0;
      let totalSize = 0;
      await available.installer.downloadAndInstall((event) => {
        switch (event.event) {
          case "Started":
            totalSize = event.data.contentLength ?? 0;
            return;
          case "Progress":
            downloaded += event.data.chunkLength;
            if (totalSize > 0) {
              setProgress(Math.min(100, Math.round((downloaded / totalSize) * 100)));
            }
            return;
          case "Finished":
            setStatus("installing");
            return;
        }
      });
      // Restart so the new .exe takes over from the running one.
      const { relaunch } = await import("@tauri-apps/plugin-process");
      await relaunch();
    } catch (err: unknown) {
      const message =
        err instanceof Error
          ? err.message
          : typeof err === "string"
            ? err
            : "Error desconocido";
      setError(message);
      setStatus("error");
    }
  };

  const dismiss = () => setStatus("idle");

  if (status === "idle" || status === "checking") return null;

  // Card lives bottom-right, fixed. z-50 keeps it above modal dialogs
  // (the contract detail dialog is z-40). Width is constrained so it
  // never crowds the table data the Dra is reading.
  const baseClasses =
    "fixed bottom-4 right-4 max-w-sm w-[22rem] bg-white border rounded-lg shadow-lg p-4 z-50 font-sans";

  if (status === "available" && available) {
    return (
      <div className={`${baseClasses} border-blue-300`} role="status" aria-live="polite">
        <div className="flex items-start gap-2">
          <span className="text-blue-600 text-xl leading-none" aria-hidden>
            ↻
          </span>
          <div className="flex-1 min-w-0">
            <p className="font-semibold text-gray-900">
              Hay una actualización disponible
            </p>
            <p className="text-sm text-gray-700 mt-1">
              <span className="font-mono text-xs text-gray-500">
                v{available.version}
              </span>
              {available.notes && (
                <span className="block mt-1 line-clamp-3">{available.notes}</span>
              )}
            </p>
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-3">
          <button
            type="button"
            onClick={dismiss}
            className="px-3 py-1.5 text-sm text-gray-600 hover:text-gray-900 rounded"
          >
            Más tarde
          </button>
          <button
            type="button"
            onClick={startUpdate}
            className="px-4 py-1.5 text-sm font-medium bg-blue-600 text-white rounded hover:bg-blue-700"
          >
            Actualizar
          </button>
        </div>
      </div>
    );
  }

  if (status === "downloading") {
    return (
      <div className={`${baseClasses} border-blue-300`} role="status" aria-live="polite">
        <p className="font-semibold text-gray-900">Descargando actualización…</p>
        <div className="w-full bg-gray-200 rounded-full h-2 mt-3">
          <div
            className="bg-blue-600 h-2 rounded-full transition-all"
            style={{ width: `${progress}%` }}
          />
        </div>
        <p className="text-xs text-gray-500 mt-1">{progress}%</p>
      </div>
    );
  }

  if (status === "installing") {
    return (
      <div className={`${baseClasses} border-blue-300`} role="status" aria-live="polite">
        <p className="font-semibold text-gray-900">Instalando…</p>
        <p className="text-sm text-gray-600 mt-1">
          La app se va a reiniciar sola en unos segundos.
        </p>
      </div>
    );
  }

  if (status === "error") {
    return (
      <div className={`${baseClasses} border-red-300`} role="alert" aria-live="assertive">
        <p className="font-semibold text-red-900">Error al actualizar</p>
        <p className="text-sm text-gray-600 mt-1 break-all">
          {error ?? "No se pudo descargar la actualización."}
        </p>
        <p className="text-xs text-gray-500 mt-2">
          Intentá de nuevo más tarde o contactá soporte.
        </p>
        <div className="flex justify-end mt-3">
          <button
            type="button"
            onClick={dismiss}
            className="px-3 py-1.5 text-sm bg-gray-100 hover:bg-gray-200 rounded"
          >
            Cerrar
          </button>
        </div>
      </div>
    );
  }

  return null;
}
