"use client";

import * as React from "react";
import { Cloud, CloudOff, Loader2, AlertTriangle } from "lucide-react";
import { getSyncStatus, onSyncStatus } from "@/lib/state-store";

/**
 * Indicador discreto de estado del sync con Gist privado.
 * Cardinal (2026-04-28 · Sergio C-light): la Dra ve a simple vista si
 * sus cambios están viajando entre máquinas o si hay un problema.
 *
 * Estados:
 *   - configured=false → "Sin sync (solo este equipo)" gris
 *   - state=syncing    → "Sincronizando…" con spinner
 *   - state=ok         → "Sincronizado · hace 12s" verde discreto
 *   - state=error      → "Error de sync" amber con tooltip del error
 *   - state=idle       → "Pendiente de sincronizar"
 */
export function SyncIndicator() {
  const [status, setStatus] = React.useState(getSyncStatus());
  const [, setTick] = React.useState(0);

  React.useEffect(() => {
    const off = onSyncStatus(setStatus);
    // Re-render cada 30s para actualizar el "hace Xs"
    const t = setInterval(() => setTick((n) => n + 1), 30_000);
    return () => {
      off();
      clearInterval(t);
    };
  }, []);

  if (!status.configured) {
    return (
      <span
        className="inline-flex items-center gap-1 text-[10px] text-ink-soft/60"
        title="Sync no configurado · tus cambios solo viven en este equipo"
      >
        <CloudOff className="h-3 w-3" />
        Solo este equipo
      </span>
    );
  }

  if (status.state === "syncing") {
    return (
      <span
        className="inline-flex items-center gap-1 text-[10px] text-burgundy"
        title="Subiendo tus cambios al espacio privado en la nube"
      >
        <Loader2 className="h-3 w-3 animate-spin" />
        Sincronizando…
      </span>
    );
  }

  if (status.state === "error") {
    return (
      <span
        className="inline-flex items-center gap-1 text-[10px] text-amber-700"
        title={status.last_error ?? "Error desconocido"}
      >
        <AlertTriangle className="h-3 w-3" />
        Error de sync
      </span>
    );
  }

  if (status.state === "ok" && status.last_synced_at) {
    const ago = humanizeAgo(status.last_synced_at);
    return (
      <span
        className="inline-flex items-center gap-1 text-[10px] text-emerald-700/80"
        title={`Última sincronización exitosa: ${new Date(status.last_synced_at).toLocaleString("es-CO")}`}
      >
        <Cloud className="h-3 w-3" />
        Sincronizado{ago && ` · ${ago}`}
      </span>
    );
  }

  return (
    <span
      className="inline-flex items-center gap-1 text-[10px] text-ink-soft/60"
      title="Esperando cambios para sincronizar"
    >
      <Cloud className="h-3 w-3" />
      En espera
    </span>
  );
}

function humanizeAgo(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  if (ms < 0) return "";
  const s = Math.floor(ms / 1000);
  if (s < 60) return `hace ${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `hace ${m} min`;
  const h = Math.floor(m / 60);
  if (h < 24) return `hace ${h}h`;
  const d = Math.floor(h / 24);
  return `hace ${d}d`;
}
