"use client";

import * as React from "react";
import { AlertCircle, Check, Copy, ExternalLink, Mail } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

// URL del workflow scrape-portal-mensual.yml. Aceptaria un input
// `uids=CO1.NTC.X,CO1.NTC.Y` cuando Sergio clickea "Run workflow" en
// la pagina del Action.
const GITHUB_WORKFLOW_URL =
  "https://github.com/smarroquinc10/14-SECOP-Dr-Camila-Mendoza/actions/workflows/scrape-portal-mensual.yml";

// Mail de Sergio (IT) — fallback cuando no esta al lado para clickear
// el GitHub Action. El cliente de mail abre con asunto + body prellenados.
const SERGIO_EMAIL = "smarroquincabrera@gmail.com";

// CapSolver (per SCRAPER_SETUP.md): ~$0.001 USD por captcha resuelto.
// Asumimos 1 captcha por proceso (en realidad puede ser 0 si las cookies
// estan recientes, conservadoramente cobramos 1).
const COST_PER_PROCESS_USD = 0.001;

// ETA por proceso con CapSolver: ~30s captcha + ~15s navegacion = ~45s.
const SECONDS_PER_PROCESS = 45;

export interface RefreshModalProps {
  uids: string[];
  mode: "selected" | "all_visible";
  open: boolean;
  onClose: () => void;
}

/**
 * Modal de "Refrescar seleccion contra community.secop". Funciona en el
 * deploy de GitHub Pages (sin backend) ofreciendo 3 caminos:
 *   (1) Copiar UIDs al clipboard + abrir GitHub Action → Sergio pega y corre
 *   (2) mailto Sergio con asunto + lista prellenados
 *   (3) (futuro) PAT en localStorage para disparar via GitHub API directo
 *
 * Cardinal: el modal NUNCA dispara el scrape solo. Toda accion requiere
 * confirmacion humana (Sergio aprieta "Run workflow" en la UI de GitHub o
 * manda el mail). Esto evita gastar CapSolver por accidente.
 */
export function RefreshModal({ uids, mode, open, onClose }: RefreshModalProps) {
  const [copied, setCopied] = React.useState(false);

  const count = uids.length;
  const costUsd = count * COST_PER_PROCESS_USD;
  const etaSeconds = count * SECONDS_PER_PROCESS;
  const etaHumano =
    etaSeconds < 60
      ? `${etaSeconds}s`
      : etaSeconds < 3600
      ? `~${Math.round(etaSeconds / 60)} min`
      : `~${Math.round((etaSeconds / 3600) * 10) / 10} h`;

  const uidsCsv = uids.join(",");
  const uidsList = uids.join("\n");

  // Reset clipboard state when modal re-opens.
  React.useEffect(() => {
    if (open) setCopied(false);
  }, [open]);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(uidsCsv);
      setCopied(true);
      setTimeout(() => setCopied(false), 3000);
    } catch (err) {
      console.error("clipboard.writeText fallo:", err);
    }
  }

  // mailto: con asunto + body prellenados. Limita body a 1500 chars para
  // no romper en clientes viejos. Si excede, sugiere usar "Copiar IDs".
  const mailSubject = encodeURIComponent(
    `[Dashboard FEAB] Refrescar ${count} ${
      count === 1 ? "proceso" : "procesos"
    } del portal SECOP`
  );
  const mailBodyRaw =
    `Sergio, refrescá estos ${count} procesos en community.secop ` +
    `(ya están seleccionados por mí en el dashboard).\n\n` +
    `UIDs:\n${uidsList}\n\n` +
    `Cuando termine el scrape, el seed se actualiza solo y veo los ` +
    `datos nuevos al refrescar la página.\n\n` +
    `Cami`;
  const mailBody =
    mailBodyRaw.length > 1500
      ? `Sergio, refrescá ${count} procesos del portal SECOP. La lista ` +
        `completa está en mi clipboard del dashboard (uso el botón ` +
        `"Copiar IDs"). — Cami`
      : mailBodyRaw;
  const mailtoHref = `mailto:${SERGIO_EMAIL}?subject=${mailSubject}&body=${encodeURIComponent(
    mailBody
  )}`;

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            {mode === "selected"
              ? `Refrescar ${count} ${
                  count === 1 ? "proceso seleccionado" : "procesos seleccionados"
                }`
              : `Refrescar ${count} procesos visibles`}
          </DialogTitle>
          <DialogDescription>
            Pasale estos UIDs a Sergio para que dispare el scrape contra
            community.secop. Cuando termine, los datos nuevos aparecen en
            tu dashboard automáticamente (el cron de deploy a Pages corre solo).
          </DialogDescription>
        </DialogHeader>

        <div className="px-6 py-5 space-y-5 overflow-y-auto">
          {/* Cost + ETA banner */}
          <div className="flex items-start gap-3 bg-amber-50 border border-amber-200 rounded-md px-4 py-3">
            <AlertCircle className="h-4 w-4 text-amber-700 mt-0.5 shrink-0" />
            <div className="text-xs text-amber-900 space-y-1">
              <div>
                <span className="font-semibold">Costo estimado:</span>{" "}
                <span className="font-mono">≈ ${costUsd.toFixed(2)} USD</span>
                {" · "}
                <span className="font-semibold">Tiempo:</span>{" "}
                <span className="font-mono">{etaHumano}</span>
              </div>
              <div className="text-amber-800">
                CapSolver resuelve los captchas automáticamente
                (~$0.001 por proceso). Cuando termine, el seed se commitea
                solo y se hace deploy.
              </div>
            </div>
          </div>

          {/* UIDs preview + copy */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="eyebrow text-ink-soft">
                {count} {count === 1 ? "UID" : "UIDs"} a refrescar
              </span>
              <Button
                size="sm"
                variant="outline"
                onClick={handleCopy}
                className="gap-2"
              >
                {copied ? (
                  <>
                    <Check className="h-3.5 w-3.5 text-emerald-700" />
                    Copiado
                  </>
                ) : (
                  <>
                    <Copy className="h-3.5 w-3.5" />
                    Copiar IDs
                  </>
                )}
              </Button>
            </div>
            <div className="border border-rule rounded-md bg-stone-50 p-3 max-h-48 overflow-y-auto">
              <pre className="font-mono text-[11px] text-ink whitespace-pre-wrap break-all">
                {uidsList}
              </pre>
            </div>
          </div>

          {/* Action options */}
          <div className="space-y-2 pt-2 border-t border-rule">
            <div className="eyebrow text-ink-soft mb-2">¿Cómo dispararlo?</div>

            {/* Option 1: GitHub Action — copia primero al clipboard */}
            <a
              href={GITHUB_WORKFLOW_URL}
              target="_blank"
              rel="noopener noreferrer"
              onClick={() => {
                if (!copied) handleCopy();
              }}
              className="flex items-start gap-3 border border-rule rounded-md px-4 py-3 hover:border-burgundy/40 hover:bg-burgundy/5 transition-colors"
            >
              <ExternalLink className="h-4 w-4 text-burgundy mt-0.5 shrink-0" />
              <div className="text-xs flex-1">
                <div className="font-semibold text-ink mb-0.5">
                  Disparar GitHub Action ahora (Sergio)
                </div>
                <div className="text-ink-soft leading-relaxed">
                  Te lleva a la página del workflow. Click{" "}
                  <span className="font-mono">Run workflow</span> → pegá los
                  IDs (ya copiados a tu clipboard) en el campo{" "}
                  <span className="font-mono">uids</span> → click{" "}
                  <span className="font-mono">Run workflow</span>. Toma{" "}
                  {etaHumano}.
                </div>
              </div>
            </a>

            {/* Option 2: mailto Sergio */}
            <a
              href={mailtoHref}
              className="flex items-start gap-3 border border-rule rounded-md px-4 py-3 hover:border-burgundy/40 hover:bg-burgundy/5 transition-colors"
            >
              <Mail className="h-4 w-4 text-burgundy mt-0.5 shrink-0" />
              <div className="text-xs flex-1">
                <div className="font-semibold text-ink mb-0.5">
                  Mandárselo a Sergio por mail
                </div>
                <div className="text-ink-soft leading-relaxed">
                  Abre tu cliente de mail con asunto y la lista de UIDs
                  prellenados. Útil cuando Sergio no está al lado para clickear.
                </div>
              </div>
            </a>
          </div>

          {/* Footer hint */}
          <div className="text-[10px] text-ink-soft italic pt-2 border-t border-rule">
            Cardinal: estos {count} procesos se refrescan contra
            community.secop. El dashboard pasa de mostrar el snapshot viejo
            a uno fresco con todos los campos, documentos y notificaciones
            actuales del portal.
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
