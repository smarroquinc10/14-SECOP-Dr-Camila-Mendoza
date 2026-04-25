# Prompt para iniciar nueva sesión de Claude · Dra Cami Contractual

Copia y pega TODO esto al iniciar una nueva sesión:

---

```
Trabajo en el proyecto Dra Cami Contractual.

Path: C:\Users\FGN\01 Claude Repositorio\14 SECOP Dr Camila Mendoza
Branch: claude/secop-ii-integration-ee0Lr (ya en GitHub: https://github.com/smarroquinc10/Secop-II)

ANTES DE TOCAR CUALQUIER LÍNEA DE CÓDIGO:

1. Lee el archivo CLAUDE.md en la raíz del repo. Tiene TODAS las
   reglas cardinales (filosofía, UX, qué SÍ y qué NO). NO repreguntes
   cosas que están ahí — léelo y aplícalo.

2. Lee tu memoria persistente:
   - feedback_secop_truth_excel_link.md → "verdad = SECOP, Excel solo
     vigencia + link + numero_contrato"
   - reference_excel_layout.md → 6 hojas, LINK col 74/72, header row 1/4
   - feedback_python_module_caching.md → MATAR python antes de editar

3. Antes de editar archivos Python, mata cualquier proceso corriendo:
   powershell -Command "Get-Process python,node | Stop-Process -Force"
   (si no, los cambios al código no se reflejan)

CONTEXTO RÁPIDO:
- Sistema: FastAPI bridge (puerto 8000) + Next.js 16 (puerto 3000)
  + Excel master "BASE DE DATOS FEAB CONTRATOS2.xlsx" + watch list
  persistido en .cache/watched_urls.json (491 procesos únicos del
  Excel, no en git por PII).
- Lanzar: ejecutar_pro.bat (doble click). Mata todo y relanza con
  el comando arriba.
- Tests: ./.venv/Scripts/python.exe -m pytest -q  →  165/165 verdes.
- TS check: cd app; ./node_modules/.bin/tsc --noEmit  →  0 errors.

PRINCIPIO CARDINAL (no negociable):
La verdad vive en SECOP. Del Excel SOLO se toma:
  • la VIGENCIA (col 3.VIGENCIA)
  • el LINK (col LINK)
  • el numero_contrato (col 2 — identificador interno de la Dra,
    legítimo igual que vigencia + link)

NUNCA derivar estado/valor/proveedor/fecha-firma del Excel para la
tabla principal. Si SECOP API no tiene un proceso → mostrar "—"
honestamente y badge "No en API público". Las observaciones manuales
de la Dra (col 72 OBSERVACIONES) van SÓLO al modal de detalle.

ESTADO ACTUAL (commit más reciente: en HEAD del branch):
✅ Tabla unificada compacta (6 columnas, sin scroll horizontal)
✅ Filtros arriba (Buscar/Vigencia/Estado/Modalidad/Hoja)
✅ Filtro por hoja expande a row-per-appearance (FEAB 2024 → 85 rows)
✅ Columnas: Contrato (con numero FEAB) · Objeto/Proveedor ·
   Valor/Firma · Estado · Modificatorios · Origen · Acciones
✅ Botones con rótulo: [↗ Abrir] [✏ Editar] [🗑 Quitar]
✅ Verify masivo: GET /verify-progress + POST /verify-watch
✅ Barra de progreso con elapsed + ETA + percent visible cuando running
✅ Vista única: SIEMPRE solo procesos del Excel (491), sin toggle
✅ Filosofía cardinal enforced en backend y frontend

PENDIENTE (priorizar según pida la Dra):
1. Filtros estilo Excel en cada column header (sort + popover de
   checkboxes). El componente contracts-table.tsx (no usado actualmente)
   tiene la lógica con TanStack Table — reusarlo dentro de
   unified-table.tsx en vez de la tabla simple actual.
2. Selector de hoja al hacer click "Agregar" — el backend POST /watch
   ya acepta {url, sheet, note}. Falta UI: cuando la Dra paste URL,
   le muestra un dropdown con FEAB 2026/2025/.../2018-2021 antes de
   confirmar.

LA DRA ES NO TÉCNICA — usa lenguaje claro, evita jerga, y NUNCA le
preguntes algo que esté en CLAUDE.md o en sus memorias persistentes.
Si algo no es obvio para una persona no técnica, mejora el rótulo.

Comenzá leyendo CLAUDE.md ahora.
```

---

## Cómo usarlo

1. Abrí Claude Code en el path del proyecto
2. Pegá TODO el bloque de arriba (entre los ` ``` `) como primer mensaje
3. Claude leerá el CLAUDE.md automáticamente y va a tener el contexto completo
4. NO necesitás repetir las reglas — están en CLAUDE.md

## Qué leerá Claude automáticamente

Todo esto se carga en contexto al arrancar:
- `CLAUDE.md` (raíz del repo) — reglas cardinales
- `~/.claude/projects/.../memory/MEMORY.md` — pointers a memorias persistentes
- Las 6 memorias persistentes (project, references, feedback)

## Si algo se rompe en la nueva sesión

Decile a Claude:
- "Lee CLAUDE.md primero"
- "Recordá la regla cardinal: verdad = SECOP, Excel solo vigencia + link + numero_contrato"
- "Mata los procesos Python antes de editar"
