# Prompt para iniciar nueva sesión de Claude · Sistema de Seguimiento Contratos FEAB Dra Cami

Copia y pega TODO esto al iniciar una nueva sesión:

---

```
Trabajo en el proyecto "Sistema de Seguimiento Contratos FEAB Dra Cami".

Path: C:\Users\FGN\01 Claude Repositorio\14 SECOP Dr Camila Mendoza
Branch: claude/secop-ii-integration-ee0Lr (GitHub: https://github.com/smarroquinc10/Secop-II)

ANTES DE TOCAR CÓDIGO:

1. Leé CLAUDE.md (raíz del repo) — TODAS las reglas cardinales (filosofía,
   UX, qué SÍ y qué NO). NO repreguntes lo que está ahí.

2. Leé tus memorias persistentes (MEMORY.md apunta a ellas):
   - feedback_secop_truth_excel_link.md → "del Excel SOLO vigencia + link"
     (NI siquiera numero_contrato — ese también es de SECOP)
   - project_final_deliverable.md → meta es Tauri MSI para Camila
   - reference_excel_layout.md → 6 hojas, LINK col 74/72
   - feedback_python_module_caching.md → MATAR python antes de editar

3. Antes de editar Python, mata procesos:
   powershell -Command "Get-Process python,node | Stop-Process -Force"

REGLA CARDINAL ACTUALIZADA (no negociable):
La verdad vive 100% en SECOP. Del Excel SOLO se toma:
  • la VIGENCIA (col 3.VIGENCIA)
  • el LINK (col 74 / 72 según hoja)

NADA MÁS. El numero_contrato también viene de SECOP
(`referencia_del_contrato`). Si SECOP no expone un proceso → "—"
honesto + badge "No en API público". Las observaciones manuales (col 72)
van SÓLO al modal de detalle.

META FINAL DEL PROYECTO:
Empaquetar como Tauri MSI instalable que la Dra le pasa a Camila
(usuaria final, no técnica). Doble click → instala → ícono FEAB en
escritorio → app abre como ventana nativa Windows con identidad
institucional. Cero "instala Python primero", cero browser, cero consola.

Arquitectura final del .exe:
- Tauri shell (Rust + WebView2 nativo Windows ~15 MB) — ventana
- Next.js export estático — frontend bundleado
- FastAPI vía PyInstaller — sidecar que Tauri lanza/mata
- %LOCALAPPDATA%/Dra-Cami/profile — captcha SECOP persistido entre runs

CONTEXTO TÉCNICO RÁPIDO:
- FastAPI bridge (puerto 8000) + Next.js 16 (puerto 3000)
- Excel master "BASE DE DATOS FEAB CONTRATOS2.xlsx" (no en git por PII)
- Watch list persistido en .cache/watched_urls.json (491 procesos únicos)
- Lanzar dev: ejecutar_pro.bat (mata todo y relanza)
- Tests: ./.venv/Scripts/python.exe -m pytest -q  →  165/165 verdes
- TS check: cd app; ./node_modules/.bin/tsc --noEmit  →  0 errors

ESTADO ACTUAL (sesión 1 de UX completada):
✅ Identidad FEAB integrada: logo Fiscalía top-strip, sellos gov.co
   + Colombia Compra + Gob.linea en footer institucional
✅ Título oficial: "Sistema de Seguimiento Contratos FEAB · Dra Cami"
   (en layout.tsx metadata + browser tab)
✅ Logos descargados a app/public/ (feab-logo.png, fiscalia-horizontal.jpg,
   feab-banner.png, sellos/Todos_pais.png, Col_compra.png, gov.co-footer.png,
   Gob_linea.png, Ponal.png, MedLegal.png) — bajados de feab.fiscalia.gov.co
✅ ETA visible en barra de refresh — separada a línea propia con badge
   "Tiempo restante ≈ Xm Ys" (ya no se cortaba a la derecha)
✅ Quitado fallback `numero_contrato_excel` en unified-table.tsx —
   ahora solo muestra `referencia_del_contrato` de SECOP, "—" si no hay
✅ Filtros tipo Excel en cada columna de unified-table:
   - Sort asc/desc/none clickeando el título
   - Popover con search + checkbox list de valores únicos por columna
   - "Limpiar" / "Seleccionar todos" / banner "Tabla con filtros
     personalizados" + botón Restablecer formato cuando hay filtros activos
   - TanStack Table como engine, ColumnHeader compartido con contracts-table.tsx
   - Filtros inteligentes por columna:
     · Contrato → filtra por numero_contrato/id
     · Objeto/Proveedor → filtra por proveedor (más útil que objeto largo)
     · Valor/Firma → ordena numérico, filtra por año de firma
     · Estado → multi-select estados
     · Modificatorios → "Modificado" vs "Sin modificatorios"
     · Origen → "Contrato firmado / Verificado / Borrador / No en API"
✅ 165/165 pytest verdes · 0 errors tsc

PENDIENTE PARA LA SESIÓN 2 — SCRAPER PORTAL SECOP:
Los 201 NTCs que datos.gov.co no expone se ven como "—" en la tabla.
La verdad está en el portal community.secop.gov.co — el sistema debe
LEER cada link directamente.

Infra existente (los `_probe_*.py` en raíz):
- _probe_portal.py → Playwright headful + persistent context + captcha
- _probe_patchright.py → patchright (Playwright stealth)
- _probe_solver.py → captcha solver
- _captcha_page.html → ejemplo de página captcha

Trabajo a hacer:
1. Convertir probes en servicio batch: scripts/scrape_portal.py
   - Recibe lista de notice_uid (los 201 que no_en_api)
   - Lanza Playwright con persistent context (.cache/browser_profile/)
   - Por cada URL: navega, espera captcha si aparece (1ª vez Camila
     resuelve, después está cacheado), parsea el DOM, extrae:
     numero_contrato, valor, proveedor, estado, fecha_firma, modalidad,
     mods proceso, adiciones, etc.
   - Persiste en .cache/portal_snapshots/{notice_uid}.json con
     secop_hash SHA-256 + code_version + fetched_at
2. Endpoint /contract-portal/{id} en FastAPI que devuelve el snapshot
3. UI: cuando verifyStatus === "no_en_api" Y hay snapshot, mostrar los
   datos del snapshot con badge "Leído del portal" (en vez de "—")
4. Botón "Leer del portal" por fila para forzar re-scrape
5. Tests: pytest cubriendo el parser + endpoint

PENDIENTE PARA LA SESIÓN 3 — EMPAQUETADO TAURI:
1. Setup Tauri en /tauri (cargo init, tauri.conf.json)
2. Configurar:
   - Title: "Sistema de Seguimiento Contratos FEAB · Dra Cami"
   - Icon: FEAB logo
   - Sidecar: FastAPI bundleado con PyInstaller (en /api_server/dist/)
   - Frontend: Next.js export estático (next build → /out/)
3. tauri build → MSI instalable
4. Test en VM Windows limpia (sin Python ni Node) — debe funcionar

LA DRA ES NO TÉCNICA — lenguaje claro, evita jerga, NUNCA preguntes
algo que esté en CLAUDE.md o en mi memoria persistente. Si algo no es
obvio para una persona no técnica, mejora el rótulo.

Empezá leyendo CLAUDE.md ahora.
```

---

## Cómo usarlo

1. Abrí Claude Code en el path del proyecto
2. Pegá TODO el bloque de arriba (entre los ` ``` `) como primer mensaje
3. Claude leerá CLAUDE.md automáticamente y va a tener el contexto completo
4. NO necesitás repetir las reglas — están en CLAUDE.md

## Qué leerá Claude automáticamente

Todo esto se carga en contexto al arrancar:
- `CLAUDE.md` (raíz del repo) — reglas cardinales
- `~/.claude/projects/.../memory/MEMORY.md` — pointers a memorias persistentes
- Las memorias persistentes (project, references, feedback)

## Si algo se rompe en la nueva sesión

Decile a Claude:
- "Lee CLAUDE.md primero"
- "Recordá la regla cardinal: verdad = SECOP, Excel SOLO vigencia + link"
- "El numero_contrato también es de SECOP, no del Excel"
- "Mata los procesos Python antes de editar"
- "La meta final es Tauri MSI para Camila"
