/**
 * Clasificacion cardinal de actos modificatorios desde nombres de PDFs
 * del portal community.secop.
 *
 * Sergio 2026-04-28: "toca que en serio los modificatorios correspondan
 * que se vea el numero del documento y que es el modificatorio si es
 * adicion, prorroga y asi".
 *
 * Antes el dashboard contaba con regex grueso /modificatorio|otrosi|
 * adendo|adicional al contrato/i y solo decia "N modificatorios" sin
 * tipificar. Cobertura real medida sobre 473 procesos: 129/855 = 15%.
 *
 * Clasificador actual:
 *   1. Detecta 11 tipos distintos por keywords especificas.
 *   2. Aplica filtros anti-FP (poliza adicional NO es modificatorio).
 *   3. Extrae numero del documento si aparece (No 1, Nº 2, etc).
 *   4. Cardinal-honesto: si el match es ambiguo, tipo = "Modificatorio"
 *      generico en vez de inventar un subtipo.
 */

export type TipoModificatorio =
  | "Modificatorio"
  | "Otrosi"
  | "Adenda"
  | "Adicion"
  | "Prorroga"
  | "Cesion"
  | "Suspension"
  | "Liquidacion"
  | "Terminacion anticipada"
  | "Reanudacion"
  | "Novacion";

export interface ClassifiedModificatorio {
  /** Tipo cardinal del acto contractual. */
  tipo: TipoModificatorio;
  /** Numero extraido del nombre si aparece (ej. "2", "1A"). null si no. */
  numero: string | null;
  /** Nombre original del PDF tal como vino del scrape. */
  nombre: string;
  /** URL del PDF en community.secop. */
  url: string;
}

const PATTERN_RULES: Array<[TipoModificatorio, RegExp]> = [
  ["Terminacion anticipada", /terminaci[oó]n\s+anticipada/i],
  ["Reanudacion", /reanudaci[oó]n/i],
  ["Liquidacion", /\bliquidaci[oó]n\b|acta\s+de\s+liquidaci/i],
  ["Suspension", /suspensi[oó]n|acta\s+de\s+suspensi/i],
  ["Novacion", /novaci[oó]n/i],
  ["Cesion", /\bcesi[oó]n\b/i],
  ["Prorroga", /\bpr[oó]rroga\b|\bprorroga\b/i],
  ["Adicion", /\badici[oó]n\b(?!al)/i],
  ["Adenda", /\badend[oa]\b/i],
  ["Otrosi", /\botros[ií]\b/i],
  ["Modificatorio", /modificatori[oa]/i],
  ["Modificatorio", /\bmod\b\.?(?:\s|\d|$)/i],
];

const FALSE_POSITIVE_RULES: RegExp[] = [
  /p[oó]liza\s+adicional/i,
  /poliza\s+actualizada\s+de\s+meses\s+adicional/i,
  /\bmodulo\b/i,
  /carta\s+autorizaci[oó]n\s+cesi[oó]n.*libertad/i,
];

const NUMERO_RE =
  /(?:N[°ºo]\.?|n[uú]mero|no\.?)\s*(\d{1,3}[A-Za-z]?)|(?:^|\s)(\d{1,2})\s+(?:firmado|FEAB|de\s+\d{4})/i;

export function classifyDoc(
  doc: { name: string; url: string },
): ClassifiedModificatorio | null {
  const name = (doc.name ?? "").trim();
  if (!name) return null;

  for (const fp of FALSE_POSITIVE_RULES) {
    if (fp.test(name)) return null;
  }

  for (const [tipo, pat] of PATTERN_RULES) {
    if (pat.test(name)) {
      const numeroMatch = NUMERO_RE.exec(name);
      const numero = numeroMatch?.[1] ?? numeroMatch?.[2] ?? null;
      return {
        tipo,
        numero: numero ?? null,
        nombre: name,
        url: doc.url ?? "",
      };
    }
  }
  return null;
}

export function classifyDocs(
  docs: Array<{ name: string; url: string }>,
): ClassifiedModificatorio[] {
  const classified: ClassifiedModificatorio[] = [];
  for (const d of docs) {
    const c = classifyDoc(d);
    if (c) classified.push(c);
  }
  const tipoOrder: Record<TipoModificatorio, number> = {
    "Adicion": 1,
    "Prorroga": 2,
    "Modificatorio": 3,
    "Otrosi": 4,
    "Adenda": 5,
    "Cesion": 6,
    "Suspension": 7,
    "Reanudacion": 8,
    "Terminacion anticipada": 9,
    "Novacion": 10,
    "Liquidacion": 11,
  };
  classified.sort((a, b) => {
    const ta = tipoOrder[a.tipo] ?? 99;
    const tb = tipoOrder[b.tipo] ?? 99;
    if (ta !== tb) return ta - tb;
    const na = parseInt(a.numero ?? "0", 10);
    const nb = parseInt(b.numero ?? "0", 10);
    return na - nb;
  });
  return classified;
}

export function summarizeModificatorios(
  classified: ClassifiedModificatorio[],
): string {
  if (classified.length === 0) return "Sin modificatorios";
  if (classified.length === 1) {
    const c = classified[0];
    return c.numero ? `${c.tipo} N° ${c.numero}` : c.tipo;
  }
  const counts: Partial<Record<TipoModificatorio, number>> = {};
  for (const c of classified) counts[c.tipo] = (counts[c.tipo] ?? 0) + 1;
  const parts: string[] = [];
  const plurals: Record<TipoModificatorio, [string, string]> = {
    "Modificatorio": ["Modificatorio", "Modificatorios"],
    "Otrosi": ["Otrosi", "Otrosies"],
    "Adenda": ["Adenda", "Adendas"],
    "Adicion": ["Adicion", "Adiciones"],
    "Prorroga": ["Prorroga", "Prorrogas"],
    "Cesion": ["Cesion", "Cesiones"],
    "Suspension": ["Suspension", "Suspensiones"],
    "Liquidacion": ["Liquidacion", "Liquidaciones"],
    "Terminacion anticipada": ["Terminacion", "Terminaciones"],
    "Reanudacion": ["Reanudacion", "Reanudaciones"],
    "Novacion": ["Novacion", "Novaciones"],
  };
  for (const [tipo, n] of Object.entries(counts)) {
    if (!n) continue;
    const [s, pl] = plurals[tipo as TipoModificatorio];
    parts.push(`${n} ${n === 1 ? s : pl}`);
  }
  return `${classified.length} actos · ${parts.join(" · ")}`;
}
