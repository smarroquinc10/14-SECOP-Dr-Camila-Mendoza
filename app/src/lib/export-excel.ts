/**
 * Exporta las filas FILTRADAS de la tabla unificada a un archivo .xlsx
 * descargable. Pensado para que la Dra mande info por mail rápidamente.
 *
 * SheetJS (`xlsx`) genera el Excel directo en el browser — sin server.
 * El archivo aparece en su carpeta de Descargas con nombre tipo
 * `FEAB-procesos-2026-04-25.xlsx`.
 *
 * Filosofía cardinal: cuando la Dra descarga el Excel, **ve TODO**. El
 * workbook trae 2 hojas:
 *
 *   - "Vista"  — las 17 columnas curadas que ve en la pantalla.
 *                Familiar para mandar por mail.
 *   - "Datos completos crudos"  — UNA columna por cada campo distinto que
 *                devuelven jbjy-vk9h (api), rpmr-utcd (integrado) o el
 *                portal cache. Las columnas vienen prefijadas (`api_`,
 *                `integ_`, `portal_`) para que la Dra sepa de dónde sale
 *                cada valor. Sin filtros, sin curado, sin "comer" datos.
 *
 * NUNCA agregamos campos calculados ni inventamos columnas — solo
 * volcamos lo que el SECOP devolvió tal cual.
 */

import type { UnifiedRow } from "@/components/unified-table";

/**
 * Mapeo de columnas: cada entry define el header del Excel y cómo
 * extraer el valor de una `UnifiedRow`. El orden coincide con el orden
 * de columnas que la Dra ve en la tabla — para que el Excel se sienta
 * familiar.
 */
type Column = {
  header: string;
  pick: (r: UnifiedRow) => string | number | null;
};

const COLUMNS: Column[] = [
  { header: "Vigencia", pick: (r) => r.vigencias?.[0] ?? "" },
  { header: "Hoja Excel", pick: (r) => r.sheets?.join(", ") ?? "" },
  { header: "Numero Contrato", pick: (r) => r.numero_contrato ?? "" },
  { header: "Process ID", pick: (r) => r.process_id ?? "" },
  { header: "Notice UID", pick: (r) => r.notice_uid ?? "" },
  { header: "Objeto", pick: (r) => r.objeto ?? "" },
  { header: "Proveedor", pick: (r) => r.proveedor ?? "" },
  {
    header: "Valor (COP)",
    pick: (r) => (typeof r.valor === "number" ? r.valor : ""),
  },
  { header: "Fecha de firma", pick: (r) => r.fecha_firma ?? "" },
  { header: "Estado", pick: (r) => r.estado ?? "" },
  { header: "Modalidad", pick: (r) => r.modalidad ?? "" },
  {
    header: "Dias adicionados (modificatorios)",
    pick: (r) => (typeof r.dias_adicionados === "number" ? r.dias_adicionados : ""),
  },
  { header: "Liquidado", pick: (r) => (r.liquidado ? "Si" : "No") },
  // Notas vienen del campo `_notas` computado del API (estado_contrato +
  // dias_adicionados) ó de la observación manual (Excel) con prefijo claro.
  // No se exportaba antes y la Dra perdía esa columna al mandar el XLSX.
  { header: "Notas", pick: (r) => r.notas ?? "" },
  { header: "Origen del dato", pick: (r) => labelDataSource(r.data_source) },
  { header: "URL del proceso (SECOP)", pick: (r) => r.url ?? "" },
];

function labelDataSource(s: UnifiedRow["data_source"]): string {
  switch (s) {
    case "api":
      return "SECOP API (datos.gov.co)";
    case "integrado":
      return "SECOP Integrado (datos.gov.co)";
    case "portal":
      return "Portal SECOP (cache)";
    default:
      return "Sin datos publicos";
  }
}

/**
 * Genera y descarga el .xlsx. SheetJS se importa dinámicamente para
 * no inflar el bundle inicial — solo se baja cuando la Dra clickea
 * "Descargar".
 */
export async function exportRowsToExcel(
  rows: UnifiedRow[],
  filenameStem: string,
): Promise<void> {
  if (rows.length === 0) {
    throw new Error("No hay filas que descargar con los filtros actuales.");
  }

  const xlsx = await import("xlsx");

  // Convertir filas a array of objects con headers como keys.
  const data = rows.map((r) => {
    const out: Record<string, string | number | null> = {};
    for (const col of COLUMNS) {
      out[col.header] = col.pick(r);
    }
    return out;
  });

  const ws = xlsx.utils.json_to_sheet(data, {
    header: COLUMNS.map((c) => c.header),
  });

  // Anchos de columna proporcionales al contenido — visual mejor que
  // todas iguales. Solo set en columnas largas (Objeto, URL).
  ws["!cols"] = COLUMNS.map((c) => {
    if (c.header === "Objeto") return { wch: 60 };
    if (c.header === "URL del proceso (SECOP)") return { wch: 80 };
    if (c.header === "Proveedor") return { wch: 40 };
    if (c.header === "Notice UID" || c.header === "Process ID") return { wch: 22 };
    if (c.header === "Numero Contrato") return { wch: 24 };
    if (c.header === "Notas") return { wch: 50 };
    return { wch: 16 };
  });

  const wb = xlsx.utils.book_new();
  xlsx.utils.book_append_sheet(wb, ws, "Vista");

  // ──────────────────────────────────────────────────────────────────
  // SHEET 2 — "Datos completos crudos": dump exhaustivo de TODOS los
  // campos que cada fila trae de cada fuente. Es la columna vertebral
  // del cardinal "ver todo": el Excel le muestra a la Dra cada valor
  // que el SECOP devolvió, sin curado, con prefijo de origen para que
  // sepa de dónde viene cada cosa.
  // ──────────────────────────────────────────────────────────────────
  const noiseFields = new Set<string>([
    "_id", "_notas",
    ":@computed_region_y8tx_xa3w",
    ":@computed_region_b8mb_y23g",
    ":@computed_region_kpa3_pdzn",
    ":@computed_region_ck25_dyt8",
    ":@computed_region_g8jr_8txm",
    ":@computed_region_yyfu_pwt8",
  ]);
  const apiKeys = new Set<string>();
  const integKeys = new Set<string>();
  const portalKeys = new Set<string>();
  for (const r of rows) {
    if (r._raw_api) {
      for (const k of Object.keys(r._raw_api)) {
        if (!noiseFields.has(k)) apiKeys.add(k);
      }
    }
    if (r._raw_integrado) {
      for (const k of Object.keys(r._raw_integrado)) {
        if (!noiseFields.has(k)) integKeys.add(k);
      }
    }
    if (r._raw_portal) {
      // Para portal, nos interesan los `fields` (claves curadas por
      // el scraper) y `all_labels` (raw del HTML). Aplanamos ambos
      // bajo prefijos distintos para que sea explícito.
      const fields = (r._raw_portal.fields ?? {}) as Record<string, unknown>;
      const allLabels = (r._raw_portal.all_labels ?? {}) as Record<string, unknown>;
      for (const k of Object.keys(fields)) portalKeys.add(`field.${k}`);
      for (const k of Object.keys(allLabels)) portalKeys.add(`label.${k}`);
      // Metadata del scrape
      portalKeys.add("scraped_at");
      portalKeys.add("status");
    }
  }
  const sortedApiKeys = Array.from(apiKeys).sort();
  const sortedIntegKeys = Array.from(integKeys).sort();
  const sortedPortalKeys = Array.from(portalKeys).sort();

  // Headers: identificación primero (process_id / contrato), luego
  // todos los api_* / integ_* / portal_* en orden alfa.
  const idHeaders = ["process_id", "id_contrato", "notice_uid", "url"];
  const headers = [
    ...idHeaders,
    ...sortedApiKeys.map((k) => `api_${k}`),
    ...sortedIntegKeys.map((k) => `integ_${k}`),
    ...sortedPortalKeys.map((k) => `portal_${k}`),
  ];

  function flat(v: unknown): string | number {
    if (v === null || v === undefined) return "";
    if (typeof v === "string" || typeof v === "number") return v;
    if (typeof v === "boolean") return v ? "Si" : "No";
    // Objetos/arrays se serializan a JSON para no perder data.
    try {
      return JSON.stringify(v);
    } catch {
      return String(v);
    }
  }

  const rawData = rows.map((r) => {
    const out: Record<string, string | number | null> = {
      process_id: r.process_id ?? "",
      id_contrato: r.id_contrato ?? "",
      notice_uid: r.notice_uid ?? "",
      url: r.url ?? "",
    };
    for (const k of sortedApiKeys) {
      out[`api_${k}`] = r._raw_api ? flat(r._raw_api[k]) : "";
    }
    for (const k of sortedIntegKeys) {
      out[`integ_${k}`] = r._raw_integrado ? flat(r._raw_integrado[k]) : "";
    }
    for (const k of sortedPortalKeys) {
      if (!r._raw_portal) {
        out[`portal_${k}`] = "";
        continue;
      }
      if (k === "scraped_at" || k === "status") {
        out[`portal_${k}`] = flat(r._raw_portal[k]);
      } else if (k.startsWith("field.")) {
        const sub = k.slice("field.".length);
        const fields = (r._raw_portal.fields ?? {}) as Record<string, unknown>;
        out[`portal_${k}`] = flat(fields[sub]);
      } else if (k.startsWith("label.")) {
        const sub = k.slice("label.".length);
        const allLabels = (r._raw_portal.all_labels ?? {}) as Record<string, unknown>;
        out[`portal_${k}`] = flat(allLabels[sub]);
      } else {
        out[`portal_${k}`] = "";
      }
    }
    return out;
  });

  const ws2 = xlsx.utils.json_to_sheet(rawData, { header: headers });
  // Anchos compactos — son muchas columnas, queremos que entren.
  ws2["!cols"] = headers.map(() => ({ wch: 18 }));
  xlsx.utils.book_append_sheet(wb, ws2, "Datos completos crudos");

  // Metadatos del workbook — la Dra puede ver Properties → Author en Excel.
  if (wb.Props == null) wb.Props = {};
  wb.Props.Title = "Sistema de Seguimiento Contratos FEAB";
  wb.Props.Author = "Dra. María Camila Mendoza Zubiría";
  wb.Props.Company = "FEAB · Fiscalía General de la Nación";
  wb.Props.Subject = "Procesos SECOP II — exportado del dashboard";

  const today = new Date().toISOString().slice(0, 10);
  const safeStem = (filenameStem || "FEAB-procesos").replace(/[^a-zA-Z0-9_-]/g, "-");
  const filename = `${safeStem}-${today}.xlsx`;

  xlsx.writeFile(wb, filename);
}
