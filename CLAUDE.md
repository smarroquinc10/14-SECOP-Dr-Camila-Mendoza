# CLAUDE.md — Dra Cami Contractual · Reglas Cardinales

> Este archivo se carga automáticamente cada vez que Claude Code (u otra
> herramienta) trabaja en este repo. **Es el brief que define qué se puede
> y qué NO se puede hacer.** Léelo antes de tocar código.

## ⛔ Filosofía no negociable: **La verdad es SECOP**

> **El SECOP es la única fuente de verdad. Del Excel sólo se toma
> la VIGENCIA y el LINK. Nada más.**

Toda otra información (estado, valor, proveedor, fecha firma, modificatorios,
adiciones, prórrogas, liquidación, etc.) se obtiene exclusivamente del SECOP
en vivo siguiendo el link. Si el SECOP API público no expone un proceso, la
celda se muestra `—` honestamente y el badge dice "No en API público" — la
Dra abre el portal manualmente desde el botón "Abrir".

**NUNCA**:
- Inventar valores derivados del Excel para llenar la tabla principal.
- Asumir que un campo del Excel "es lo mismo" que un campo de SECOP.
- Mostrar la nota "Modificado" basada solo en una palabra del Excel.
- Eliminar una fila porque el SECOP no la tenga ("comer datos").

**Las observaciones manuales de la Dra (Excel col 72 OBSERVACIONES) se
muestran SÓLO en el modal de detalle**, no en la tabla principal.

## ✅ Reglas de UX (no me las repitan más)

### Tabla
1. **UNA sola tabla** — la unificada (`unified-table.tsx`). No revivir dos
   tablas paralelas (watch list + inventario). Una vista, una verdad.
2. **Sin scroll horizontal**. Máximo 6-8 columnas. Combinar info en
   sub-líneas dentro de cada celda antes que agregar columnas.
3. **Conteos = Excel exacto**: cuando filtra por hoja FEAB 2024 y el Excel
   tiene 85 filas, la tabla muestra 85 filas. Expandir 1 row por
   aparición (ver `expandRowsByAppearance`).
4. **Click fila → modal detalle** con todo: contratos, mods proceso,
   adiciones, observaciones de la Dra, secop_hash, code_version.

### Filtros
- **Siempre ARRIBA**, en un solo bloque. No mezclados con la tabla.
- Slicers tipo pills (`SlicerPills`): Vigencia · Estado · Modalidad · Hoja Excel.
- Toggles: "Solo los procesos del Excel" (ON por default), "Solo
  contratos modificados".
- Botón "Limpiar filtros" cuando hay alguno activo.
- Lenguaje claro: "Filtros rápidos" (no "Marcas"), "Solo los procesos
  del Excel" (no "Solo mis procesos seguidos").

### Botones de acción
- **Rótulo de texto al lado del icono**, siempre: `[↗ Abrir]`,
  `[✏ Editar]`, `[🗑 Quitar]`. Iconos solos confunden.
- Tooltip explica QUÉ hace y QUÉ pasa después.

### Header
- "Auditoría · Gestión Contractual · SECOP" en el eyebrow.
- Saludo: "Bienvenida, Dra. María Camila Mendoza Zubiría".
- Subtítulo: SOLO la fecha. NO repetir "Jefe de Gestión Contractual del FEAB".

### Acciones del watch list
- **Agregar URL**: form arriba con input + botón. Cuando agrega, le
  pregunta a qué hoja pertenece (selector con FEAB 2026/2025/.../2018-2021).
- **Editar URL**: lápiz inline en la fila. Enter para guardar, Esc
  cancela.
- **Quitar**: trash en la fila.
- **NO existe el botón "Importar del Excel"** — los 491 procesos ya están
  importados de una vez. Si la Dra necesita re-importar, IT lo corre por CLI.

### Vista por defecto (no negociable)
- **SIEMPRE mostrar SOLO los procesos que están en el Excel de la Dra**.
  No hay toggle "ver todos los contratos del FEAB" — eso confunde.
  La Dra cuida sus 491 procesos del Excel, no los 287 del inventario
  completo SECOP. La vista es una sola: SUS procesos, enriquecidos
  con SECOP API cuando aplica.
- El bloque "Atajos" arriba solo tiene "Solo contratos modificados"
  (toggle simple, sin sección compleja).

### Numero de contrato (excepción legítima al Excel)
- El **numero_contrato** que la Dra escribe (CONTRATO-FEAB-X-Y) ES
  un identificador legítimo del Excel — igual que vigencia + link.
  No es "Excel-derived data" sino un ID interno que la Dra usa
  para referirse a sus contratos.
- Si el SECOP API tiene `referencia_del_contrato`, usar esa.
- Si no, usar el `numero_contrato` del Excel (col 2).
- NUNCA mostrar `CO1.NTC.X` como código primario si la Dra escribió
  el suyo en el Excel.

## ✅ Lo que SÍ debe hacer el sistema

1. **Espejo del SECOP**: cada link del watch list se debe poder verificar
   contra el SECOP en vivo. El script `scripts/verify_watch_list.py`
   marca cada item con su `verify_status` (ok_with_notice /
   found_in_contracts / draft_request / not_found).
2. **Provenance siempre**: cada celda lleva (cuando aplica) `secop_hash`
   SHA-256 + `code_version` (git short SHA del código que la escribió).
3. **Audit log inmutable**: hash-chained, blockchain-style. Cada
   replace/fill se registra. El indicador del header muestra
   "X entradas · íntegro" o "alerta" si la chain se rompió.
4. **Honesto cuando no sabe**: badge "No en API público" para los 201
   NTCs que datos.gov.co no expone — sin inventar metadata.
5. **Idempotente**: re-correr el verify o el import nunca duplica filas
   ni invalida lo persistido.

## ✅ Lo que SÍ se persiste por item del watch list

```jsonc
{
  "url": "https://community.secop.gov.co/...",
  "process_id": "CO1.NTC.5405127",
  "notice_uid": "CO1.NTC.5405127",          // resuelto via SECOP API
  "sheets": ["FEAB 2024"],                   // del Excel
  "vigencias": ["2024"],                     // del Excel (col 3.VIGENCIA)
  "appearances": [
    {"sheet": "FEAB 2024", "row": 2, "vigencia": "2024", "url": "..."}
  ],
  "added_at": "2026-04-25T...",
  "edited_at": "2026-04-25T..."  // sólo si fue editada
}
```

**No se persiste `excel_data` con estado/valor/etc. — eso es runtime y
viene del SECOP API.**

## ⚠️ Cosas que se hacen automáticamente y NO debes deshacer

- `setup.ps1` instala Python venv + npm install + Playwright en primera ejecución.
- `ejecutar_pro.bat` lanza FastAPI :8000 + Next.js :3000 + abre browser.
- `.cache/audit_log.jsonl` es la chain inmutable — no editar a mano.
- `.cache/watched_urls.json` es persistido — los scripts lo actualizan.

## 🚫 Skills auto-sugeridas que NO aplican (skipearlas)

Estas se sugieren por hooks pero no aplican a este proyecto:
- `vercel:*`, `nextjs`, `next-cache-components`, `next-upgrade`,
  `react-best-practices`, `shadcn`, `turbopack`, `verification`,
  `workflow`, `vercel-cli`.

Razón: app local Tauri-target con FastAPI + Next dev server. No es deploy Vercel.

## 📌 Comandos clave

```powershell
# Tests Python
.\.venv\Scripts\python.exe -m pytest -q     # debe dar 165/165

# TypeScript check
cd app; .\node_modules\.bin\tsc --noEmit    # debe dar 0 errors

# Audit log integrity
.\.venv\Scripts\python.exe -m secop_ii audit-log

# Verify masivo contra SECOP (toma ~17 min)
.\.venv\Scripts\python.exe -X utf8 -u scripts\verify_watch_list.py

# Importar desde Excel (sólo IT, una vez)
curl -X POST http://localhost:8000/watch/import-from-excel -d "{}"

# Lanzar app (ella usa esto)
.\ejecutar_pro.bat

# Matar processes antes de editar Python (CRÍTICO)
powershell -Command "Get-Process python,node | Stop-Process -Force"
```

## 🎯 Compliance reality

Esto es trabajo real para la Dra María Camila Mendoza Zubiría, Jefe de
Gestión Contractual del **FEAB** (Fondo Especial para la Administración
de Bienes), Fiscalía General de la Nación. NIT FEAB: **901148337**.

Falsos positivos / falsos negativos / "comer datos" tienen consecuencias
legales reales para una persona. La filosofía cardinal **NO ES OPINIÓN —
es protección**.
