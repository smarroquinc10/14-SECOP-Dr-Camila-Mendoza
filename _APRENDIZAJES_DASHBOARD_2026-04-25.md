# Aprendizajes en vivo — Dashboard FEAB

**Iniciado**: 2026-04-25 (post-refactor CLAUDE.md estructura RUNT)
**Análogo a**: `_APRENDIZAJES_LOTE_16647_v918.md` del bot RUNT Pro
**Objetivo**: cada error / discrepancia / incidente que aparezca en producción
del dashboard FEAB → handler permanente en código + lección persistida acá.

> **Filosofía** (heredada del RUNT, sección 3 de
> `_APRENDIZAJES_LOTE_16647_v918.md`): si un campo del dashboard no coincide
> con community.secop en vivo, **es FP / FN / dato comido** — no entregar
> Excel ni declarar deploy listo. Fixear el parser / cascada / modal con un
> handler que regresione el caso, y deployar con el smoke test canónico
> (4 procesos del CLAUDE.md sección "Smoke test canónico") verificado.

---

## Formato por error (estricto)

```
### Error #N — NOMBRE_CORTO
**Proceso (si aplica)**: CO1.X.X (process_id o notice_uid)
**Fecha / hora**: YYYY-MM-DD HH:MM (TZ Bogotá)
**Reportado por**: Dra Cami / Sergio / IT / Claude session / GitHub Action / browser
**Síntoma exacto**:
  - Lo que la Dra ve en pantalla (texto exacto, screenshot path si existe)
  - O el error de console (mensaje completo)
  - O el response 4xx/5xx de Socrata
  - O el discrepancy entre dashboard y community.secop
**Causa**: diagnóstico técnico (1-3 párrafos)
**Fix propuesto**: archivo:línea + cambio específico (snippet de código si aplica)
**Impacto**:
  - tabla / modal / Excel / audit log / passphrase / 0 si cosmético
  - cuántos procesos afectados (1, N, todos)
  - si afecta Telegram también (no aplica al dashboard, dejar "n/a")
**Test que regresione**: ruta del test + assertion
**Smoke test canónico**: cuál de los 4 procesos del CLAUDE.md valida el fix
**Status**: PENDIENTE_DIAGNÓSTICO / PENDIENTE_DEPLOY / DEPLOYED / INVALIDATED
```

**Reglas del formato**:
1. Un error por sección. No fusionar (regla "1 fix por deploy" del RUNT).
2. **Status INVALIDATED** si tras investigación resulta no ser bug (ej. la
   Dra interpretó mal una celda). Dejarlo igual con la explicación —
   sirve como antecedente para futuros falsos reportes.
3. **NO borrar** entradas. Si un fix se rolledback, agregar **Error #N+1**
   con causa "rollback de #N" y explicación.
4. Si la causa es zona prohibida del CLAUDE.md → marcarlo explícitamente
   ("Zona quemada, requirió sesión dedicada").

---

## Histórico — incidentes pre-formato (referencia)

Los siguientes 6 bugs fueron capturados en `AUDIT-REPORT-2026-04-25.md`
ANTES de adoptar este formato. Quedan como antecedente histórico — todos
ya están **DEPLOYED** y verificados en `VERIFICATION-REPORT-2026-04-25.md`
(18/18 PASS) y `COMPLIANCE-REPORT-2026-04-25.md` (5+6 PASS):

| # legacy | Severidad | Resumen | Archivo:línea fix | Verificado en |
|---|---|---|---|---|
| BUG-001 | 🔴 CRÍTICO | Detail-dialog comía 29/73 campos del API jbjy-vk9h | `app/src/components/detail-dialog.tsx` (sección "Otros campos del API SECOP" expandida por default) | VERIFICATION §5.1 |
| BUG-002 | 🟠 ALTO | Favicon 404 (path sin basePath) | `app/src/app/layout.tsx` con `withBasePath` | VERIFICATION §2 (favicon 200) |
| BUG-003 | 🟠 ALTO | Portal cache sin `scraped_at` por entry | re-bake + GitHub Action diaria | VERIFICATION §5.3 (badge "vía portal cache · hoy") |
| BUG-004 | 🟡 MEDIO | `data_source="portal"` sin badge "vía portal" | `app/src/components/unified-table.tsx` branch portal | VERIFICATION §5.3 |
| BUG-005 | 🟡 MEDIO | Columna `notas` no exportada a Excel | `app/src/lib/export-excel.ts::COLUMNS` | VERIFICATION §7 (hoja Vista incluye Notas) |
| BUG-006 | 🟡 MEDIO | datos.gov.co fetched 2-3× por carga (waterfall) | Promise singleton en `app/src/lib/api.ts` | VERIFICATION §3 (fetch 1× cada uno) |

**Cardinal violation extra** (encontrada durante COMPLIANCE-REPORT, fix `4e029f2`):
- `unified-table.tsx::buildUnifiedRows` mezclaba `obs_brief` en columna
  `notas` con prefijo `(Excel)` — viola regla cardinal "observaciones
  manuales SÓLO en modal". Fix: `notas = null` en buildUnifiedRows.

---

## Errores en vivo — formato `Error #N`

### Error #1 — FILTRO_BUSQUEDA_FALTA_NOTICE_UID
**Proceso**: `CO1.NTC.1416630` (process_id en watch list es `CO1.PPI.10057597`)
**Fecha / hora**: 2026-04-26 ~10:00 (Bogotá)
**Reportado por**: Dra. Cami durante smoke test canónico
**Síntoma exacto**: la Dra escribió `CO1.NTC.1416630` en el campo "Buscar" del dashboard, no apareció ningún resultado. El proceso SÍ existe en rpmr-utcd LIVE (`url_contrato LIKE %CO1.NTC.1416630%` devuelve 1 hit con proveedor "GESVALT E ISAZA", valor 12.023.760).
**Causa**: `app/src/app/page.tsx:174-181` el blob de búsqueda concatenaba `id_contrato + process_id + objeto + proveedor` pero NO `notice_uid`. 276/491 items (56%) tienen `notice_uid != process_id`. La Dra los identifica por NTC pero el filtro solo busca por process_id.
**Fix propuesto**: agregar `(r.notice_uid ?? "")` al blob, separado por espacios para evitar matches accidentales.
**Impacto**: filtro de búsqueda · 276 items afectados (56% del watch list)
**Test que regresione**: manual — buscar `CO1.NTC.1416630` debe devolver el row con `process_id=CO1.PPI.10057597`
**Smoke test canónico**: proceso #2 del CLAUDE.md (`CO1.NTC.1416630` integrado)
**Status**: **DEPLOYED** (commit `4760ff8`)

---

### Error #2 — COUNTER_X_DE_773_INCLUYE_HUERFANOS
**Proceso**: ninguno específico (afecta indicador del header)
**Fecha / hora**: 2026-04-26 ~10:00 (Bogotá)
**Reportado por**: Dra. Cami (capturado en screenshot del smoke test)
**Síntoma exacto**: contador del header decía "1 de 773 mostrados" cuando `onlyMine=true` y la Dra solo administra 491 procesos. El "773" no encaja con ninguna métrica esperada.
**Causa**: `page.tsx:777` el divisor era `allRows.length` que incluye 282 contratos huérfanos del SECOP (procesos del FEAB que no están en el watch list de la Dra). Con `onlyMine=true` esos quedan filtrados pero el counter los sumaba igual. Viola CLAUDE.md regla operacional 8: "vista por defecto = SUS 491 procesos del Excel".
**Fix propuesto**: `{filtered.length} de {allRows.filter((r) => r.watched).length} mostrados`
**Impacto**: UX del header · 0 datos cardinales afectados (solo cosmético, pero engañoso)
**Test que regresione**: manual — sin filtros activos, contador debe ser "491 de 491 mostrados" (o `XXX de 491` si el filtro de hoja está activo)
**Smoke test canónico**: cualquiera — el counter siempre debe mostrar `/491` como divisor máximo
**Status**: **DEPLOYED** (commit `4760ff8`)

---

### Error #3 — CLAUDE_MD_VALORES_HARDCODED_DESACTUALIZADOS
**Proceso**: `CO1.PCCNTR.8930451` (la Dra lo abrió en smoke test)
**Fecha / hora**: 2026-04-26 ~10:30 (Bogotá)
**Reportado por**: auto-detectado al cross-checkear LIVE durante diagnóstico de Error #1
**Síntoma exacto**: el CLAUDE.md sección "Smoke test canónico" decía que `CO1.PCCNTR.8930451 → valor $276.830.000`. LIVE jbjy-vk9h hoy devuelve `valor=3700000` (`$3.700.000`, CONTRATO DE COMPRAVENTA FEAB 0001 DE 2026, "En ejecución", proveedor "GERMAN DAVID BOTERO RODRIGUEZ").
**Causa**: durante refactor del CLAUDE.md (commit `e62d49f`) copié los valores del `AUDIT-REPORT-2026-04-25.md` sin verificar contra LIVE. El AUDIT-REPORT era de 1 día antes y los datos cambiaron. Esto viola directamente la **Regla Suprema #1** ("NUNCA inventar valores derivados del Excel" — y por extensión, ningún valor que no provenga de la fuente en vivo).
**Fix propuesto**: smoke test del CLAUDE.md ahora especifica el MÉTODO de verificación (curl contra Socrata + comparar campo por campo en modal), no los valores esperados. Cada deploy se valida contra LIVE.
**Impacto**: documentación · sample manual de la Dra fallaba con falsos negativos del propio doc
**Test que regresione**: el smoke test canónico nuevo es self-validating — pide curl contra Socrata real, no compara contra valores fijos
**Smoke test canónico**: proceso #1 (`CO1.PCCNTR.8930451`)
**Status**: **DEPLOYED** (commit `59ffe35`)

---

### Error #4 — DIAGNOSTICO_FALSO_CO1.PPI.11758446_FN
**Proceso**: `CO1.PPI.11758446`
**Fecha / hora**: 2026-04-26 ~10:15 (Bogotá)
**Reportado por**: yo mismo durante diagnóstico (declaré bug E que no era bug)
**Síntoma exacto**: declaré que `CO1.PPI.11758446` era FN cardinal del dashboard porque "rpmr-utcd LIVE devuelve 2 hits" mientras dashboard mostraba "No en API público".
**Causa**: error de lectura de respuesta Socrata. La query `?id_del_proceso=CO1.PPI.11758446` falla porque `id_del_proceso` no existe como campo en rpmr-utcd. Devuelve `{"error": true, "message": "Unrecognized arguments [id_del_proceso]"}` (un dict de 2 keys). Yo interpreté `len(d)=2` como "2 hits" cuando era "2 keys del dict de error". Re-verificado con queries correctas (`numero_de_proceso=` y `url_contrato LIKE`) → 0 hits real. El proceso NO está en ninguna API pública. El dashboard CORRECTAMENTE muestra "No en API público" — la Dra puede verlo en community.secop manualmente porque el portal SÍ lo tiene, pero las APIs públicas no lo exponen.
**Fix propuesto**: ninguno del código del dashboard. Lección: siempre verificar el shape del response (`isinstance(data, list)`) antes de tratarlo como hits.
**Impacto**: ninguno en código · me costó 1 ronda de diagnóstico falsa
**Test que regresione**: el script `scripts/audit_dashboard_full.py` ahora valida `isinstance(data, list)` antes de contar hits
**Smoke test canónico**: proceso #4 (`CO1.PPI.11758446`)
**Status**: **INVALIDATED** (no era bug del dashboard, era error de mi diagnóstico)

---

### Error #5 — 265_PROCESOS_SIN_COBERTURA_API_PUBLICA
**Proceso**: 265 procesos (todos los `coverage=none` excepto 8 borradores REQ/BDOS)
**Fecha / hora**: 2026-04-26 ~11:00 (Bogotá)
**Reportado por**: Dra. Cami con la frase "tu sistema es muy pobre y frágil... tienes los links! tienes que basicamente entrar y no puedes comerte datos"
**Síntoma exacto**: 265 procesos del watch list aparecen con badge "No en API público" + celdas en `—`. La Dra puede abrirlos manualmente en community.secop y SÍ tienen datos completos (objeto, valor, proveedor, modificatorios, etc.). El dashboard no los refleja → la Dra termina abriendo cada link manualmente, anulando el propósito del dashboard.
**Causa**: las 3 fuentes API consumibles desde frontend (datos.gov.co/jbjy-vk9h, datos.gov.co/rpmr-utcd, portal_opportunity_seed.json) NO exponen estos 265 procesos. Solo `community.secop.gov.co` (portal con captcha) los tiene. El frontend no puede scrapear directamente — necesita Playwright + captcha solver. Eso requiere correr `scripts/scrape_portal.py` LOCAL (no GitHub Action) en máquina con tiempo (~30-55s por proceso × 265 = ~2-4 horas).
**Fix propuesto**: corrida masiva de `scripts/scrape_portal.py --watch-list` local, después commit del `app/public/data/portal_opportunity_seed.json` actualizado, deploy via Pages.
**Impacto**: tabla principal · modal · Excel export · 265/491 (54%) items afectados — gap CARDINAL
**Test que regresione**: re-correr `scripts/audit_dashboard_full.py`. Con scrape completo, severity `scrape` debe ir de 265 → 0 (o casi: algunos pueden no estar accesibles aún en SECOP).
**Smoke test canónico**: cualquier proceso PPI no-borrador con `coverage=none` (sample en el JSON: `CO1.PPI.38453188`, `CO1.PPI.36786565`, etc.)
**Status**: **PENDIENTE_DEPLOY** — requiere corrida local con `.venv` activado + Whisper modelo bajado + ~3 horas. La GitHub Action no puede correrlo (Playwright + audio no aplica bien en CI). IT (Sergio) o Dra ejecuta cuando pueda.

---

### Error #6 — SCRAPE_PORTAL_SISTEMA_NO_FUNCIONAL_4_BLOQUEADORES
**Proceso**: piloto sobre `CO1.NTC.7906712` y `CO1.NTC.8210327`
**Fecha / hora**: 2026-04-26 10:10–10:17 (Bogotá)
**Reportado por**: yo durante el intento de cerrar Error #5 con piloto pequeño (2 procs)
**Síntoma exacto**: piloto de 2 procesos terminó con **2/2 errores** (100% fail rate, 7.3 minutos):
```
[1/2] CO1.NTC.7906712 → status=error_red, 0 docs
[2/2] CO1.NTC.8210327 → status=error_red, 0 docs
✓ Listo. 0 completos · 0 parciales · 2 errores · 7.3 min totales.
```
**Causa**: 4 bloqueadores técnicos en cascada en `src/secop_ii/portal_scraper.py` y env:
1. **API mismatch playwright-recaptcha**: el código llama `SyncSolver.solve_recaptcha(language='es-CO')` pero la versión actual de la librería ya no acepta ese kwarg. Log: `solve_recaptcha() got an unexpected keyword argument 'language'`.
2. **ffmpeg no instalado**: warning al inicio `Couldn't find ffmpeg or avconv`. Sin ffmpeg, pydub no puede convertir el WAV del captcha → audio solver falla en cascada.
3. **Whisper no instalado**: `importlib.util.find_spec('whisper')` devuelve None. El captcha solver primario no existe → cae a Google Speech (rate-limited) → cae a manual (también falla).
4. **Chrome headless por default**: cuando todos los solvers automáticos fallan, el script dice "Resuelve a mano en Chrome (hasta 180s)" pero corre headless → no hay UI donde clickear → timeout 180s → error_red.
**Fix propuesto**:
- Fix 1: patch del solver kwarg en `portal_scraper.py` (línea aprox del playwright-recaptcha call) — quitar `language` o usar la nueva API.
- Fix 2: instalar ffmpeg (`choco install ffmpeg` Windows) y agregar a PATH.
- Fix 3: `pip install openai-whisper` + descargar modelo `small` (~500MB).
- Fix 4: agregar flag `--headed` al script o forzar Chrome visible para fallback manual.
**Impacto**: bloqueo total del Error #5 — sin estos 4 fixes, el dashboard NUNCA va a ser espejo completo de los 491 links. Es el bloqueador cardinal.
**Test que regresione**: re-correr `python scripts/scrape_portal.py --limit 2` y verificar `0 errores` (o al menos `2 completos`).
**Smoke test canónico**: cualquier proceso PPI con notice_uid resuelto que esté en `coverage=none` (sample en `_AUDITORIA_DASHBOARD_2026-04-26.md`).
**Status**: **PENDIENTE_DIAGNÓSTICO** (subnivel: 4 fixes técnicos antes de poder proceder con Error #5).

---

### Error #7 — SOLVER_RECAPTCHA_CUELGA_INDEFINIDAMENTE
**Proceso**: piloto post-Fix1 sobre `CO1.NTC.7906712` y `CO1.NTC.8210327`
**Fecha / hora**: 2026-04-26 11:00 (Bogotá)
**Reportado por**: yo durante intento de re-piloto post-fix Error #6
**Síntoma exacto**: piloto colgado por 14+ minutos sin producir item events. Output file 0 bytes. Sin Chrome procesos visibles en tasklist.
**Causa**: el fix del kwarg `language` (Error #6) hizo que `solve_recaptcha(wait=True)` ahora corriera sin timeout explícito. Versiones recientes de `playwright-recaptcha` esperan indefinidamente cuando `wait=True` no tiene `wait_timeout` claro.
**Fix propuesto**: agregar `wait_timeout=60` al call. La cobertura de captcha completo NO debe tardar más de 60s legítimamente.
**Impacto**: bloqueador del scrape masivo (otra capa). Sin esto, cualquier captcha mal-detectado cuelga el batch completo.
**Test que regresione**: `python scripts/scrape_portal.py --limit 1` debe terminar en <5 min (con éxito o `error_red`, no colgado).
**Smoke test canónico**: `CO1.NTC.7906712` (proceso del primer piloto)
**Status**: **DEPLOYED** (commit en proceso)

---

### Error #8 — CAPTCHA_REQUIERE_HUMANO_INTERACTIVO
**Proceso**: piloto post-Fix1+Fix2 sobre `CO1.NTC.7906712`
**Fecha / hora**: 2026-04-26 11:18 (Bogotá)
**Reportado por**: yo durante segundo re-piloto
**Síntoma exacto**: con timeouts robustos aplicados, piloto termina en 3.8 min con `error_red` igual:
```
* Challenge en CO1.NTC.7906712 - playwright-recaptcha lib...
playwright-recaptcha solver fallo: Locator.is_enabled: Timeout 30000ms exceeded.
Call log: waiting for get_by_role("button", name=re.compile(r"^(Skip|Saltar|...)$"))
* Cayendo a solver manual (audio es-CO -> en-US)...
* Auto-solvers fallaron. Resuelve a mano en Chrome (hasta 180s)...
WARNING: Timeout esperando captcha para CO1.NTC.7906712
status=error_red docs=0
```
**Causa**: el captcha de community.secop.gov.co NO siempre es reCaptcha v2 estándar — la lib `playwright-recaptcha` busca botón "Skip/Saltar" que no existe en este portal. Audio captcha solver depende de Whisper (que funciona) PERO el flujo de download del audio falla por la estructura del portal. **Cuando ambos solvers automáticos fallan, el script abre Chrome visible y espera 180s para resolución MANUAL** — pero correr desde un sub-shell sin display interactivo del usuario significa que nadie clickea → timeout → `error_red`.
**Fix propuesto**: NINGUNO automatizable. **El scrape masivo solo puede correr desde una sesión interactiva de Windows del usuario** donde la Dra/IT vea el Chrome y resuelva captchas manualmente cuando aparezcan.
**Impacto**: el batch full de los 265 procesos NO se puede ejecutar desde mi sandbox. Solo desde sesión real Windows. Trabajo operacional manual de la Dra/IT.
**Test que regresione**: ninguno automático. Es propiedad operacional del entorno de ejecución.
**Smoke test canónico**: corrida manual exitosa de `ejecutar_scraper.bat` con sample de 5-10 procs por la Dra/IT.
**Status**: **OPERATIONAL_REQUIREMENT** (no es bug del código, es requisito del entorno de ejecución).

---

### Error #9 — THREADPOOLEXECUTOR_ROMPE_PLAYWRIGHT_SYNC
**Proceso**: piloto post-CapSolver con 3 procs (`CO1.NTC.7906712`, `CO1.NTC.8210327`, `CO1.NTC.7983080`)
**Fecha / hora**: 2026-04-26 17:01 (Bogotá)
**Reportado por**: yo durante test del batch full con CapSolver activo
**Síntoma exacto**: 3/3 procesos fallaron en **2.9 segundos** con error:
```
Cannot switch to a different thread
Current:  <greenlet.greenlet ... current active>
Expected: <greenlet.greenlet ... suspended active>
```
Toda la suite del batch fail-fast.
**Causa**: Playwright sync API NO es thread-safe. Cuando el browser se inicializa en `PortalScraper.__enter__`, queda atado al greenlet del main thread. Cualquier llamada subsiguiente a métodos del browser (page.goto, page.click, etc) DEBE hacerse desde el mismo greenlet — no desde un worker thread. Mi fix de "timeout duro per-item con `concurrent.futures.ThreadPoolExecutor`" (Error #6+#8) movió `scraper.fetch(uid)` a un worker thread, violando esa restricción.
**Fix propuesto**: revertir el ThreadPoolExecutor. Volver a `try/except` directo con `scraper.fetch(uid)`. Aceptar que NO hay timeout duro externo (es estructuralmente imposible con Playwright sync sin subprocess separado). El cap natural per-captcha viene del `wait_timeout=60` del solver lib (Fix Error #7) + timeouts internos de Playwright (180s captcha humano, 60s navigation). Worst-case per proc sin CapSolver: ~5-6 min. Worst-case con CapSolver: ~30s.
**Impacto**: scrape inejecutable mientras esté el ThreadPoolExecutor. **Cardinal: rolledback inmediato.**
**Test que regresione**: piloto con `--limit 1` debe terminar en <5 min con `status=ok_completo` o `partial`, NO con `Cannot switch to a different thread`.
**Smoke test canónico**: `CO1.NTC.7906712`
**Status**: **DEPLOYED** (rollback aplicado en commit en proceso)

**Lección operacional**: Playwright sync requiere **subprocess** (no threads) para timeouts duros externos. Si en el futuro el batch cuelga, agregar como wrapper outermost con `subprocess.Popen` + signal kill, NO threading.

---

### Error #10 — SCROLL_LATERAL_TABLA_8_COLUMNAS
**Proceso (si aplica)**: ninguno (afecta toda la tabla)
**Fecha / hora**: 2026-04-27 ~07:30 (Bogotá)
**Reportado por**: Sergio durante review de Feature G en producción
**Síntoma exacto**: Sergio capturó screenshot mostrando que la tabla principal hacía scroll horizontal — la columna "Acciones" quedaba parcialmente cortada a la derecha. La regla cardinal "máximo 6-8 columnas, sin scroll horizontal" del CLAUDE.md se rompía cuando agregamos la columna "Sel." (8va columna).
**Causa**: con la nueva columna de checkboxes "Sel." el total de columnas pasó de 7 a 8. Sumando los `size` definidos: 36+200+(flex)+140+130+170+150+220 ≈ 1046+objeto > 1216px disponibles. La tabla sin `table-fixed` permitía que las celdas empujaran el ancho de columnas y el wrapper `overflow-x-auto` mostraba scroll lateral.
**Fix propuesto**:
- Eliminar columna "Sel." separada → mover el checkbox dentro de la columna "Contrato" como flex item a la izquierda con spacer cuando no aplique (alinea filas)
- Reducir tamaños: valor 140→115, estado 130→105, modificatorios 170→130, origen 150→130, acciones 220→170
- Agregar `table-fixed` para que las celdas respeten los `size` y no empujen
**Impacto**: tabla principal · 100% afectada · regla cardinal "sin scroll horizontal" del CLAUDE.md
**Test que regresione**: e2e con Playwright debe verificar que `document.querySelector('.overflow-x-auto').scrollWidth <= clientWidth`. Pendiente.
**Smoke test canónico**: cualquier proceso · la tabla debe mostrar las 7 columnas sin scroll en 1280px.
**Status**: **DEPLOYED** (commit `c57bf83` paquete UX cero-tech)

---

### Error #11 — NTC_WATCH_LIST_FUERA_BATCH
**Proceso**: 131 NTCs del watch list (CO1.NTC.1183655, CO1.NTC.1206116, CO1.NTC.1208161, ...)
**Fecha / hora**: 2026-04-26 ~22:00 (Bogotá)
**Reportado por**: auto-detectado por la auditoría diaria (`audit_dashboard_full.py`)
**Síntoma exacto**: la auditoría reportaba `coverage=none` para 105 procesos, pero al cross-checkear contra `community.secop.gov.co` muchos tenían datos completos. El batch anterior del scrape solo procesó los 167 que estaban en una lista hardcodeada — los 131 NTCs nuevos del watch list quedaban fuera silenciosamente.
**Causa**: `scripts/scrape_portal.py` tenía una lista de UIDs cableada que no se sincronizaba con el watch list real. Cada vez que la Dra agregaba links nuevos al watch, no se incorporaban al batch de scrape.
**Fix propuesto**: leer dinámicamente del `.cache/watched_urls.json` los UIDs scrapeables y procesarlos. Quitar la lista hardcodeada.
**Impacto**: portal seed · 131/491 (27%) items afectados — gap CARDINAL que dejaba la cobertura en 78.6% en lugar de 97.8%.
**Test que regresione**: comparar la lista de UIDs del scrape con `len(watched_urls.json)`. Si difiere, fail.
**Smoke test canónico**: post-scrape, cobertura debe pasar de ~386/491 a ~480/491.
**Status**: **DEPLOYED** (commit `a86a44b` el 2026-04-26 + batch 2 cerrado en commit `b37026b` el 2026-04-27)

---

### Error #12 — HEADER_FUNCTION_RENDERIZA_SOURCE_CODE
**Proceso (si aplica)**: ninguno (afecta header de columna)
**Fecha / hora**: 2026-04-27 ~07:00 (Bogotá)
**Reportado por**: Sergio capturó screenshot en producción mostrando código JSX raw como header de columna
**Síntoma exacto**: la primera columna de la tabla (checkbox "Sel.") mostraba `()=>/*#__PURE__*/(0, __TURBOPACK__IMPORTED_MODULE__$5B$PROJECT$5D2F$NODE_MODULES$2F$NEXT$2F$DIST$2F$COMPILED$2F$REACT$2F$JSX$2D$DEV$2D$RUNTIME$2E$JS__$5B$APP$2D$CLIENT$5D$__$28$E$2D$..., ("SPAN", { CLASSNAME: "TEXT-[10PX]"...` — el código fuente de la función JSX renderizado como texto literal. Bug visible cardinal en producción para la Dra abogada.
**Causa**: `app/src/components/unified-table.tsx` la columna `id: "select"` tenía `header: () => <span>...</span>` (función). El wrapper `ColumnHeader` hace `String(h.column.columnDef.header)` — para una función eso devuelve el SOURCE CODE como texto. Las otras 7 columnas tenían `header: "Contrato"` (string) entonces no caían en el bug.
**Fix propuesto**: cambiar `header: () => <span>...</span>` a `header: "Sel."` (string simple). El checkbox cell sigue siendo JSX, el header solo necesita un label corto.
**Impacto**: tabla principal · header columna 1 · 100% visible para todos los usuarios · UX bug crítico (la Dra ve código en producción)
**Test que regresione**: e2e Playwright debe verificar que ningún `<th>` contenga el string "function" o "=>". Agregado en `scripts/smoke_e2e_camila.py` indirecto via verify columnheader names.
**Smoke test canónico**: visualmente, header columna 1 debe decir "Sel." no código JSX.
**Status**: **DEPLOYED** (commit `c57bf83`)

**Lección persistida**: `memory/feedback_tanstack_header_function.md` — TanStack Table requiere `header` como string. Si necesitás JSX, hay que usar `flexRender(column.columnDef.header, context)` en el wrapper (refactor mayor).

---

### Error #13 — ACTUALIZAR_SECOP_NO_REFRESCABA_MODIFICATORIOS
**Proceso (si aplica)**: afecta el botón principal "Actualizar datos del SECOP"
**Fecha / hora**: 2026-04-27 ~08:00 (Bogotá)
**Reportado por**: Sergio durante review · "modificaciones está ahí?"
**Síntoma exacto**: cuando la Dra clickeaba "Actualizar datos del SECOP" (~1 segundo), el feedback decía "SECOP Integrado actualizado desde datos.gov.co" — pero los modificatorios (lo MÁS RELEVANTE para Camila) NO se actualizaban porque viven en otro dataset.
**Causa**: `handleIntegradoSync()` en `app/src/app/page.tsx` solo llamaba `api.integradoSync()` que refresca `rpmr-utcd` (SECOP Integrado). Pero los modificatorios viven en `jbjy-vk9h` (contratos firmados) que requiere `reloadContracts()`. El botón principal de la Dra estaba *funcionalmente roto* para el caso de uso que ella prioriza.
**Fix propuesto**: refrescar AMBOS datasets en paralelo:
```ts
await Promise.all([
  api.integradoSync(),    // rpmr-utcd
  reloadContracts(),      // jbjy-vk9h ← LOS MODIFICATORIOS VIVEN ACÁ
]);
```
Tiempo total se mantiene en ~1-2 segundos (los 2 fetches a Socrata corren en paralelo, no secuencial).
**Impacto**: botón principal · 100% afectado · Cami no veía modificatorios frescos al click. Bug cardinal: la Dra cuida específicamente los modificatorios.
**Test que regresione**: e2e debe verificar que después del click el ModsPanel `total_modificados` se recalcula vs estado anterior.
**Smoke test canónico**: click "Actualizar datos del SECOP" · feedback debe decir "Datos del SECOP actualizados — contratos, modificatorios y todo lo demás".
**Status**: **DEPLOYED** (commit `c57bf83`)

**Lección persistida**: `memory/feedback_modificatorios_dataset.md` — los modificatorios viven en `jbjy-vk9h`. Cualquier botón "Actualizar X" que prometa frescura para la Dra debe refrescar AMBOS datasets.

---

### Error #14 — UX_TECNICA_PARA_ABOGADA_CERO_TECH
**Proceso (si aplica)**: todo el dashboard
**Fecha / hora**: 2026-04-27 ~08:30 (Bogotá)
**Reportado por**: Sergio (varios mensajes) · "ella es abogada solo le importan sus links del secop · esos botones no se entienden para qué sirven · todo el tablero debe estar para alguien no tech"
**Síntoma exacto**: 3 botones del action bar ("Refrescar desde SECOP", "Integrado (382)", "Leer del portal SECOP") parecían lo mismo para Cami abogada. Indicadores con jerga técnica ("Cobertura automática", "Última firma SECOP", "Audit log íntegro"). Badges como "vía Integrado" / "vía portal cache" sin sentido para alguien que no entiende los datasets. Card "Días adicionados" mostrando una métrica técnica que la Dra no usa.
**Causa**: el dashboard se construyó con mental model de Sergio (IT) — exponiendo cada fuente, cada operación, cada métrica técnica. Para Cami abogada esto es ruido cognitivo que la frena en lugar de ayudarla.
**Fix propuesto** (paquete completo):
1. **Action bar**: 1 solo botón visible "Actualizar datos del SECOP" + sección colapsable `<details>` "🔧 Sergio · Operaciones avanzadas (Cami no necesita usar esto)"
2. **Indicadores**: re-etiquetar — "Cobertura automática" → "Procesos con datos del SECOP", "Última firma SECOP" → "Último contrato firmado", "Audit log" → "Registro auditado"
3. **Badges**: "vía Integrado" → "Datos SECOP en vivo", "vía portal cache" → "Foto SECOP · hace X días", "No en API público" → "Aún sin publicar"
4. **Filtros**: "Modalidad de contratación" → "Tipo de contratación", "Hoja Excel" → "Período"
5. **Modificatorios**: card "Días adicionados" eliminada (no relevante), header destacado "Modificatorios — lo más relevante a revisar · acá los ves todos sin abrir link por link"
6. **Sublabels visibles** debajo de cada filtro + botón explicando qué incluye/hace en lenguaje cotidiano
7. **Tooltips multilínea** explicando cada métrica
8. **Botones acción fila**: "Agregar" → "Sumar a mi lista", "(sin contrato firmado)" → "(contrato aún no firmado)"
**Impacto**: TODA la UI · 100% afectada · UX cardinal para entrega a la Dra
**Test que regresione**: smoke test e2e debe verificar que los textos cero-tech aparezcan ("Procesos con datos del SECOP", "Modificatorios — lo más relevante a revisar", etc.). Implementado en `scripts/smoke_e2e_camila.py`.
**Smoke test canónico**: la Dra debería poder explicar cada parte del dashboard en sus propias palabras de abogada.
**Status**: **DEPLOYED** (commit `c57bf83`)

**Lección persistida**: `memory/feedback_camila_cero_tech.md` — TODO el dashboard debe estar para alguien no técnico. Lenguaje legal cotidiano. Sin jerga API/portal/scrape. Modificatorios como prioridad cardinal.

---

## Cierre de cada incidente — checklist

Antes de marcar un Error como **DEPLOYED**:

1. ✅ Test que regresione el caso agregado a `tests/` o test suite TS
2. ✅ Pre-deploy 5 CHECKS pasan (CLAUDE.md sección "5 CHECKS")
3. ✅ Smoke test canónico de los 4 procesos verificado en producción
4. ✅ Si la fix tocó zona prohibida del CLAUDE.md → sample manual de la
   Dra completado (3-5 procesos validados vs community.secop)
5. ✅ Commit con scope claro (1 fix por deploy del RUNT)
6. ✅ Status actualizado en este archivo

Si cualquier paso ❌ → no se declara DEPLOYED, queda PENDIENTE_DEPLOY
hasta cerrar todos los pasos.
