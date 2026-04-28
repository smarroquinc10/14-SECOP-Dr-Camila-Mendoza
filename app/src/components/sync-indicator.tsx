"use client";

import * as React from "react";
import { Cloud, CloudOff, Loader2, AlertTriangle } from "lucide-react";
import { getSyncStatus, onSyncStatus } from "@/lib/state-store";

/**
 * Indicador discreto de estado del sync con Gist privado.
 * Cardinal (2026-04-28 · Sergio "más firme con offline"): la Dra ve a
 * simple vista si sus cambios YA están guardados en la nube o si solo
 * existen en este equipo. El mensaje offline es enfático para que ella
 * sepa que sin red, lo que edita NO está respaldado entre máquinas.
 *
 * Estados:
 *   - configured=false → "Solo este equipo" gris
 *   - state=syncing    → "Guardando en la nube…" con spinner
 *   - state=ok         → "Guardado en la nube · hace 12s" verde
 *   - state=error+offline → CloudOff "Sin internet · cambios solo locales"
 *   - state=error      → "Reintentando…" amber
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
        Guardando en la nube…
      </span>
    );
  }

  if (status.state === "error") {
    const offline = (status.last_error ?? "").toLowerCase().includes("sin internet");
    if (offline) {
      return (
        <span
          className="inline-flex items-center gap-1 text-[10px] text-rose-700 font-semibold"
          title="Sin red · tus cambios solo viven en este equipo · subirán al volver internet"
        >
          <CloudOff className="h-3 w-3" />
          Sin internet · cambios solo locales
        </span>
      );
    }
    return (
      <span
        className="inline-flex items-center gap-1 text-[10px] text-amber-700"
        title={status.last_error ?? "Error desconocido"}
      >
        <AlertTriangle className="h-3 w-3" />
        Reintentando…
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
        Guardado en la nube{ago && ` · ${ago}`}
      </span>
    );
  }

  return (
    <span
      className="inline-flex items-center gap-1 text-[10px] text-ink-soft/60"
      title="Esperando cambios para guardar en la nube"
    >
      <Cloud className="h-3 w-3" />
      En espera
    </span>
  );
}

/**
 * Banner sticky superior · solo visible cuando la red está caída.
 * Cardinal (Sergio 2026-04-28): si Cami edita sin internet, debe ver
 * una alerta IMPOSIBLE DE IGNORAR explicando que sus cambios viven
 * solo en este equipo y NO están respaldados en la nube hasta que
 * vuelva la red. El indicator pequeño del header puede pasarle
 * desapercibido · el banner ocupa una franja completa arriba.
 */
export function OfflineBanner() {
  const [status, setStatus] = React.useState(getSyncStatus());

  React.useEffect(() => {
    const off = onSyncStatus(setStatus);
    return off;
  }, []);

  const offline =
    status.configured &&
    status.state === "error" &&
    (status.last_error ?? "").toLowerCase().includes("sin internet");

  if (!offline) return null;

  return (
    <div className="sticky top-0 z-50 bg-rose-50 border-b-2 border-rose-300 text-rose-900 px-4 py-2 text-sm flex items-start gap-2">
      <CloudOff className="h-4 w-4 shrink-0 mt-0.5" />
      <div className="flex-1">
        <strong>Sin internet en este momento.</strong>{" "}
        Lo que edites ahora se guarda <em>solo en este equipo</em> · NO está
        respaldado en la nube ni se ve desde tus otras máquinas hasta que
        vuelva la red. Cuando vuelva, el sistema sube tus cambios automático
        sin que hagas nada.
      </div>
    </div>
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
