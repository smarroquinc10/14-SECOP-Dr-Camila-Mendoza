# CLAUDE.md — Dashboard FEAB · Dra Cami Contractual

> Este archivo se carga automáticamente cada vez que Claude Code (u otra
> herramienta) trabaja en este repo. **Es el brief que define qué se puede
> y qué NO se puede hacer.** Léelo antes de tocar código.
>
> Estructura inspirada en el bot RUNT Pro (Sergio, Fiscalía) que ya está en
> producción y es espejo perfecto del RUNT. Acá la meta análoga: **el
> dashboard FEAB debe ser espejo perfecto del SECOP en cada uno de los 491
> links del watch list de la Dra**, sin FP, sin FN, sin comerse datos.

---

## ⛔ 5 REGLAS SUPREMAS (no negociables — bloquean deploy)

> Estas 5 son inviolables. Si una sola se rompe, no se hace push. Equivalente
> de las 5 reglas supremas del RUNT (`SYSTEM_PROMPT_RUNT_BOT.md`).

### 1. NUNCA inventar valores derivados del Excel
La verdad es SECOP. Del Excel solo se toma **VIGENCIA + LINK** (y excepcionalmente `numero_contrato` cuando la Dra lo escribió). Toda otra información (estado, valor, proveedor, fechas, modificatorios, adiciones) viene exclusivamente del SECOP en vivo. **No "asumir" que un campo del Excel "es lo mismo" que un campo de SECOP.**

### 2. 0 FP / 0 FN / 0 datos comidos
- **0 FP**: cero filas con `data_source=none` que muestren valor/objeto/proveedor/estado (verificable con `audit_fidelity.py`).
- **0 FN**: cero campos donde la fuente tenga dato y la UI lo descarte. Modal renderiza TODOS los campos del API/Integrado/Portal, no un subset curado.
- **0 datos comidos**: las 491 filas del watch list siempre se muestran. Si SECOP no las tiene, badge "No en API público" + "—" honesto. NUNCA eliminar fila por no estar en SECOP.

### 3. Honesto cuando no sabe
Badge `"No en API público"` para los 273 procs que datos.gov.co no expone. Modal muestra `—` por celda faltante (ej. 829 instancias de `—` en `CO1.PPI.11758446`). NUNCA inventar metadata de relleno.

### 4. Audit log append-only hash-chained
SHA-256 + `prev_hash` + `verifyAuditChain` detecta tampering en 6 escenarios (cambio payload, cambio hash, cambio prev_hash, inserción, borrado intermedio, cadena válida). Append-only por keyPath autoincrement — **no hay path para mutar entries**. Jamás editar `.cache/audit_log.jsonl` ni IndexedDB `audit_log` a mano.

### 5. Observaciones de la Dra SÓLO en modal
Las observaciones manuales (Excel col 72 OBSERVACIONES) se muestran ÚNICAMENTE en el modal de detalle, sección "Observaciones de la Dra". NUNCA en la tabla principal, NUNCA en la columna `notas`, NUNCA con prefijo `(Excel)` engañoso. Cardinal violation reciente: commit `4e029f2` removió leakage de `obs_brief` a `notas`.

---

## 📋 10 REGLAS INMUTABLES OPERACIONALES

> Equivalente de las "10 reglas inmutables grabadas" del RUNT
> (`_PRODUCCION_READY.md` líneas 107-118). No bloquean deploy si una se ve
> tocada, pero rompen UX/coherencia y la Dra las pidió explícitamente.

1. **Espejo del SECOP**: cada link verificable contra portal en vivo (`scripts/verify_watch_list.py` marca `verify_status`).
2. **Cascada `api > integrado > portal > "—"`** jamás se mezcla. El primer match gana entero, no hay merging.
3. **Cada celda con su procedencia clara**: badge "Contrato firmado" / "vía Integrado" / "vía portal cache · hoy" / "No en API público".
4. **UNA sola tabla unificada** (`unified-table.tsx`). No revivir watch list + inventario paralelos.
5. **Sin scroll horizontal**. Máximo 6-8 columnas. Combinar info en sub-líneas dentro de cada celda antes que agregar columnas.
6. **Conteos = Excel exacto**. Filtra por hoja FEAB 2024 (85 filas) → tabla muestra 85. Expandir 1 row por aparición (`expandRowsByAppearance`).
7. **Click fila → modal detalle** con TODO: contratos, mods proceso, adiciones, observaciones de la Dra, secop_hash, code_version.
8. **Vista por defecto = SUS 491 procesos**. NO toggle "ver todos los contratos del FEAB" — confunde. Los 287 del inventario SECOP-completo no son de la Dra.
9. **Idempotente**: re-correr verify, import o scrape no duplica filas ni invalida lo persistido.
10. **Provenance siempre**: cada celda con `secop_hash` SHA-256 + `code_version` (git short SHA) cuando aplique.

---

## 🚫 ZONAS PROHIBIDAS DE TOCAR (sin sesión dedicada)

> Equivalente del "PROHIBIDO tocar en sesión productiva" del RUNT
> (`SYSTEM_PROMPT_RUNT_BOT.md` líneas 47-51). Cada función acá tiene
> auditoría cardinal, rollback, o regla suprema detrás. Tocar sin sesión
> dedicada + sample manual de la Dra = riesgo real de romper compliance.

| Función / archivo | Por qué quemada |
|---|---|
| `app/src/lib/state-store.ts::verifyAuditChain` | SHA-256 chain logic — 6/6 tampering tests dependen de esto |
| `app/src/lib/state-store.ts::appendAuditLog` | Append-only invariant: keyPath autoincrement |
| `app/src/components/unified-table.tsx::buildUnifiedRows` | Cascada api>integrado>portal>none. El primer match gana entero (NO merging). Cardinal violation reciente: leakage `obs_brief` → `notas`, fix `4e029f2` |
| `app/src/lib/api.ts::getContracts` / `getIntegrado` | Promise singleton (no cache singleton). BUG-006 fix evitó 3× fetch waterfall |
| `app/src/lib/security/passphrase.ts` | PBKDF2-SHA256 200k iter — capa 1 de 3 |
| `app/src/lib/security/url.ts::assertSafeUrl` | Anti self-XSS; rechaza `javascript:`, `data:`, `file:` |
| CSP meta tag en `app/src/app/layout.tsx` | Capa 3 de 3; 0 CSP violations en producción |
| `next.config.mjs::basePath` | Romperlo rompe TODOS los assets en GitHub Pages |
| `app/src/lib/export-excel.ts::COLUMNS` | BUG-005 fix agregó `Notas`. La hoja "Datos completos crudos" tiene 86 cols con prefijo `api_/integ_/portal_` — preservar prefijos para audit independiente |

**Si necesitás tocar una zona prohibida**: sesión dedicada + plan documentado + sample manual de la Dra (3-5 procesos validados manualmente vs community.secop) post-deploy.

---

## 🎯 SMOKE TEST CANÓNICO (post-deploy)

> Equivalente de las placas canónicas del RUNT (RAK58A=SÍ, BIS51=SÍ,
> CAMION=NF). Después de cada deploy, abrir
> https://smarroquinc10.github.io/14-SECOP-Dr-Camila-Mendoza/ con
> passphrase `cami2026` y verificar **4 procesos canónicos**, uno por
> tipo de cobertura. Si CUALQUIER campo discrepa con community.secop en
> vivo → es FP/FN/comido → NO declarar deploy listo.

| # | Proceso ID | Cobertura | Resultado esperado |
|---|---|---|---|
| 1 | `CO1.PCCNTR.8930451` (CONTRATO-FEAB-0011-2025) | `api` | Badge "Contrato firmado" · modal con 73 campos · valor `$276.830.000` · 6 hermanos en "Otros contratos del mismo proceso" |
| 2 | `CO1.NTC.1416630` | `integrado` | Badge "Proceso verificado vía Integrado" · proveedor "GESVALT E ISAZA" · valor `$12.023.760` · objeto "REALIZAR EL AVALÚO" |
| 3 | `CO1.NTC.5405127` | `portal` | Badge "vía portal cache · hoy" · objeto "TRACTOCAMION KENWORTH" · valor `$12.000.000` · 59 documentos listados |
| 4 | `CO1.PPI.11758446` | `none` | Badge "No en API público" · modal con 829 instancias de `—` honesto · link "Abrir en SECOP II" funcional |

**Cómo cross-checkear**: en otra pestaña, abrir community.secop con el process_id y comparar campo por campo el modal del dashboard vs lo que muestra el portal. Esto es **sample manual obligatorio** análogo al de Sergio en RUNT (`_APRENDIZAJES_LOTE_16647_v918.md` líneas 156-180).

---

## ✅ 5 CHECKS PRE-DEPLOY VISIBLES

> Equivalente de los 5 CHECKS del RUNT (`SYSTEM_PROMPT_RUNT_BOT.md` líneas
> 77-83). Antes de `git push`, mostrar los 5 checks con ✅/❌. Si alguno
> ❌ → no se hace push.

1. **Tests Python**: `.\.venv\Scripts\python.exe -X utf8 -m pytest -q` → debe dar **192/192 PASS**
2. **TypeScript**: `cd app; .\node_modules\.bin\tsc --noEmit` → debe dar **0 errors**
3. **Audit log integrity**: `.\.venv\Scripts\python.exe -m secop_ii audit-log` → debe dar **íntegro** (chain SHA-256 verificada)
4. **Smoke test canónico**: 4 procesos arriba verificados manualmente en producción
5. **Console errors**: F12 → Console al cargar URL pública con `cami2026` → debe dar **0 errors, 0 warnings, 0 failed network requests**

**Rollback ready**: el commit anterior siempre debe estar identificado y restaurable con `git revert HEAD` antes de cada deploy. Si post-deploy el smoke test ❌, **rollback inmediato**, no defender el fix roto (regla del RUNT: "1 fix por deploy, rollback al md5 previo si rompe").

---

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

---

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
viene del SECOP API.** Auditoría forense (`audit_fidelity.py` prueba 5):
**0 / 491 items con `excel_data` populated** → no hay nada que leakear.

---

## ⚠️ Cosas que se hacen automáticamente y NO debes deshacer

- `setup.ps1` instala Python venv + npm install + Playwright en primera ejecución.
- `ejecutar_pro.bat` lanza FastAPI :8000 + Next.js :3000 + abre browser.
- `.cache/audit_log.jsonl` es la chain inmutable — no editar a mano.
- `.cache/watched_urls.json` es persistido — los scripts lo actualizan.
- GitHub Action `Refrescar seeds (datos.gov.co)` corre cron diario 06:00 UTC.
- GitHub Action `Deploy a GitHub Pages` corre en cada push a `main` (~40s).

## 🔒 Policy de pinning de dependencies

> El RUNT Pro pinea Python a versiones exactas (`requests==2.32.0`) porque
> pip no tiene lockfile estándar. Acá el patrón se aplica de forma
> diferente — leerlo antes de "modernizar" deps:

- **Python (`requirements.txt`)**: usa `>=` con tradeoffs documentados.
  Ejemplo: `tenacity>=8.1` tiene nota explícita "loosen para compatibilidad
  con streamlit (pinea <9)". **NO cambiar a `==` sin entender cada caso** —
  varios paquetes streamlit-* tienen peer deps frágiles. Si necesitás
  reproducibilidad total, generá un `requirements.lock` aparte con
  `pip freeze`, no toques el `.txt`.
- **Node (`app/package.json`)**: usa `^X.Y.Z` (rangos). El **`package-lock.json`
  es la fuente de verdad** — pinea las versiones exactas instaladas y
  garantiza reproducibilidad en CI. Pinear el `package.json` (quitar `^`)
  introduce drift con el lock y rompe `npm ci` strict mode en GitHub
  Action. **NO regenerar el lock sin sesión dedicada** — un cambio en el
  lock = un cambio de surface real, no cosmético.

---

## 🚫 Skills auto-sugeridas que NO aplican (skipearlas)

Estas se sugieren por hooks pero no aplican a este proyecto:
- `vercel:*`, `nextjs`, `next-cache-components`, `next-upgrade`,
  `react-best-practices`, `shadcn`, `turbopack`, `verification`,
  `workflow`, `vercel-cli`, `chat-sdk`.

Razón: app local Tauri-target con FastAPI dev server + Next.js static export → GitHub Pages. **No es deploy Vercel ni AI SDK.**

---

## 📌 Comandos clave

```powershell
# Tests Python
.\.venv\Scripts\python.exe -X utf8 -m pytest -q     # debe dar 192/192

# TypeScript check
cd app; .\node_modules\.bin\tsc --noEmit            # debe dar 0 errors

# Audit log integrity
.\.venv\Scripts\python.exe -m secop_ii audit-log

# Verify masivo contra SECOP (toma ~17 min)
.\.venv\Scripts\python.exe -X utf8 -u scripts\verify_watch_list.py

# Importar desde Excel (sólo IT, una vez)
curl -X POST http://localhost:8000/watch/import-from-excel -d "{}"

# Lanzar app (ella usa esto)
.\ejecutar_pro.bat

# Matar processes antes de editar Python (CRÍTICO)
powershell -Command "Get-Process python,pythonw,node | Stop-Process -Force"

# Build local + servir con basePath para test pre-push
cd app && MSYS_NO_PATHCONV=1 NEXT_PUBLIC_BASE_PATH=/14-SECOP-Dr-Camila-Mendoza npm run build
mkdir -p out_test/14-SECOP-Dr-Camila-Mendoza && cp -r out/* out_test/14-SECOP-Dr-Camila-Mendoza/
python -m http.server 8770 --directory out_test --bind 127.0.0.1

# Bajar LIVE Socrata para cross-check forense
curl "https://www.datos.gov.co/resource/jbjy-vk9h.json?nit_entidad=901148337&\$limit=2000" -o /tmp/contratos.json
curl "https://www.datos.gov.co/resource/rpmr-utcd.json?nit_de_la_entidad=901148337&\$limit=2000" -o /tmp/integrado.json
```

---

## 📝 Formato `Error #N` para capturar incidentes

> Inspirado en `_APRENDIZAJES_LOTE_16647_v918.md` del RUNT Pro. Cuando
> aparezca un bug/incidente en producción del dashboard (la Dra reporta
> celda mal, console error nuevo, modificatorio que no llega, etc),
> capturarlo con formato fijo en un archivo `_APRENDIZAJES_DASHBOARD_*.md`
> al lado de los reports de auditoría existentes:

```
### Error #N — NOMBRE_CORTO
**Proceso (si aplica)**: CO1.X.X
**Hora**: HH:MM:SS
**Síntoma exacto**: [lo que la Dra ve / mensaje console / response 4xx/5xx]
**Causa**: [diagnóstico]
**Fix propuesto**: archivo:línea + cambio específico
**Impacto**: tabla / modal / Excel / audit log / passphrase / 0 si cosmético
**Status**: PENDIENTE_DEPLOY / DEPLOYED / INVALIDATED
```

**Regla análoga al RUNT**: cada error → handler permanente en código. No tapar síntoma — diagnosticar causa, fix con test que regresione, deploy con smoke canónico.

---

## 🎯 Compliance reality

Esto es trabajo real para la Dra María Camila Mendoza Zubiría, Jefe de
Gestión Contractual del **FEAB** (Fondo Especial para la Administración
de Bienes), Fiscalía General de la Nación. NIT FEAB: **901148337**.

Falsos positivos / falsos negativos / "comer datos" tienen consecuencias
legales reales para una persona. La filosofía cardinal **NO ES OPINIÓN —
es protección**.

**Estado verificado** (2026-04-25):
- `AUDIT-REPORT-2026-04-25.md` → 6 bugs identificados (1 CRÍTICO, 2 ALTO, 3 MEDIO) — TODOS arreglados en commits subsiguientes
- `VERIFICATION-REPORT-2026-04-25.md` → 18/18 chequeos PASS
- `COMPLIANCE-REPORT-2026-04-25.md` → 5 fidelidad + 6 tampering = TODO LIMPIO

La Dra puede decir a Compliance:
> "Cada celda viene del SECOP en vivo o de un snapshot del portal con
> badge de procedencia. Las celdas vacías son `—` honestos cuando la
> fuente no expone el dato — no se inventan. Mis observaciones manuales
> viven solo en el modal, no en la data oficial. El audit log
> hash-chained certifica que nadie alteró el historial. Código fuente
> público en GitHub, seeds versionados, workflows registrados."
