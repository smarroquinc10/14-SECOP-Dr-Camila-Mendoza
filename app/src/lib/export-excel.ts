/**
 * Exporta las filas FILTRADAS de la tabla unificada a un archivo .xlsx
 * descargable. Pensado para que la Dra mande info por mail rápidamente.
 *
 * SheetJS (`xlsx`) genera el Excel directo en el browser — sin server.
 * El archivo aparece en su carpeta de Descargas con nombre tipo
 * `FEAB-procesos-2026-04-25.xlsx`.
 *
 * Filosofía cardinal: lo que se exporta es exactamente lo que ella ve
 * en pantalla en ese momento (mismos filtros, mismo orden). NUNCA
 * agregamos campos calculados ni inventamos columnas.
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
    return { wch: 16 };
  });

  const wb = xlsx.utils.book_new();
  xlsx.utils.book_append_sheet(wb, ws, "Procesos FEAB");

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
