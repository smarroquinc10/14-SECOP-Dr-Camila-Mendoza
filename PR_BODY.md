# Empaquetar app como MSI + NSIS con Tauri 2 (instala con doble click)

## Resumen

La Dra. María Camila Mendoza Zubiría ahora puede instalar el sistema de seguimiento contractual del FEAB con **doble click sobre un `.msi`**, sin Python, sin Node, sin Playwright. El resultado del build (verificado en esta máquina):

- 📦 **MSI 206 MB**: `tauri/target/release/bundle/msi/Dra Cami Contractual_1.0.0_x64_es-ES.msi`
- 📦 **NSIS 205 MB**: `tauri/target/release/bundle/nsis/Dra Cami Contractual_1.0.0_x64-setup.exe`

La app abre como ventana nativa Windows (WebView2) con el frontend Next.js (export estático) y el sidecar FastAPI (PyInstaller) corriendo en `127.0.0.1:8000`.

## Cambios principales

### `src/secop_ii/paths.py` (nuevo)
- `state_dir()`: en dev → `<repo>/.cache/`; en frozen MSI → `%LOCALAPPDATA%\Dra Cami Contractual\.cache\`
- Override con `DRA_CAMI_STATE_DIR` env var (útil para tests)
- Reemplaza los `Path(".cache/X")` hardcoded en `api.py`, audit_log writes, `changelog`, `feab_fill`, `notice_resolver`, `portal_scraper`, `pdf_reader` y los 3 `scripts/*.py`

### `src/secop_ii/api.py`
- `main()` pasa el `app` FastAPI por referencia (no como string `"secop_ii.api:app"`) — uvicorn no resuelve el dotted name dentro de un PyInstaller bundle
- `sys.stdout/stderr.reconfigure(encoding="utf-8", errors="replace")` cuando frozen — sin esto los scripts con `→`/`✓` revientan con UnicodeEncodeError en cp1252
- `_seed_state_dir_if_empty()`: el primer arranque del MSI copia `tauri/seed/*` (bundleado via PyInstaller `--add-data`) a `state_dir()`. Nunca sobreescribe data del usuario en arranques posteriores
- `_run_script_async()`: los 3 endpoints `/verify-watch`, `/integrado-sync`, `/portal-scrape` ejecutan los scripts via `subprocess.Popen` en dev y via `runpy.run_path` en thread cuando frozen (en frozen `sys.executable` es el `.exe`, no `python.exe`)
- CORS: `http(s)://tauri.localhost`, `tauri://localhost` agregados a `allow_origins`; `DELETE/PUT/OPTIONS` agregados a `allow_methods` (sin estos el preflight de `watchRemove`/`watchUpdate` falla)

### `app/src/lib/api.ts` y `app/next.config.ts`
- `BASE = "http://127.0.0.1:8000"` (era `/api/secop`) — el proxy rewrite no aplica en `output: "export"`
- 2 inline fetches (DELETE/PUT) ahora usan `${BASE}`
- `next.config.ts`: `output: "export"` + drop `rewrites()` (estático para Tauri)

### `tauri/`
- `Cargo.toml`, `tauri.conf.json` y `src/main.rs` listos para Tauri 2
- `main.rs`: setea `PYTHONUTF8=1` y `PYTHONIOENCODING` en el `Command`; redirige stdout/stderr del sidecar a `%LOCALAPPDATA%\Dra Cami Contractual\logs\sidecar.log` (debugging post-mortem); kill+wait del `Child` en `ExitRequested`; `user_state_root()` coincide con `paths.py`
- `tauri.conf.json`: `bundle.resources` copia el `dra-cami-api.exe` (no `externalBin` para evitar el sufijo target-triple); WiX language `es-ES`; ventana `label: "main"`; identifier `co.gov.fiscalia.feab.dra-cami`
- `capabilities/default.json`: requerido por Tauri 2
- `README.md`: flujo completo (PyInstaller → seed → npm build → cargo tauri build) + troubleshooting documentado (PDB error, UTF-8, externalBin)

## Verificación end-to-end (máquina de build)

- ✅ `192/192 pytest` verde después del refactor de paths
- ✅ Sidecar PyInstaller `dra-cami-api.exe` 202MB (excluyendo `streamlit/matplotlib/plotly/playwright`)
- ✅ Smoke test del sidecar standalone: `/health`, `/watch` (491 items), `/entity/feab`, `/audit-log` (1859 entries, intact: True), CORS preflight para DELETE desde `http://tauri.localhost`, `/integrado-sync` runpy refresca 382 procesos sin UnicodeEncodeError
- ✅ `cargo tauri build` produce MSI + NSIS sin errores
- ✅ Test de la app instalada: ventana abre, sidecar arranca, frontend hace `fetch` a `/health`, `/watch`, `/entity/feab`, `/audit-log`, `/integrado-bulk`, `/modificatorios-recientes`, `/contracts` — todas 200 OK
- ✅ 491 procesos cargan desde el seed bundleado (espejo del Excel)

## Filosofía cardinal preservada

- ✅ **Excel sigue siendo solo vigencia + link** — el seed bundleado tiene `watched_urls.json` que respeta esto
- ✅ **Audit log inmutable** sobrevive entre instalaciones (no se sobreescribe en re-installs)
- ✅ **State dir nunca sobreescribe data del usuario** en re-installs (el seed se salta si `watched_urls.json` ya existe)
- ✅ **No comer datos** — el sidecar rinde `—` honesto cuando una fuente no expone un campo

## NO incluido (deliberado, sin gasto)

- ❌ Code signing — la Dra dijo "no hay dinero". Windows muestra SmartScreen "editor desconocido" la primera vez pero igual instala con un click extra
- ❌ Auto-updater — requeriría hosting + endpoints. Para v1 la Dra recibe el `.msi` por mail/USB cuando hay update
- ❌ Single-instance plugin — agrega ~30s de compile, baja prioridad para v1

## Test plan

- [ ] Copiar `Dra Cami Contractual_1.0.0_x64_es-ES.msi` a la máquina de Cami
- [ ] Doble-click → wizard español → siguiente → instalar (puede pedir admin)
- [ ] Click en el ícono FEAB del escritorio
- [ ] Verificar: ventana abre con título "Sistema de Seguimiento Contratos FEAB · Dra Cami"
- [ ] Verificar: tabla carga los 491 procesos del watch list
- [ ] Click en "Sincronizar Integrado" → progress bar → 382 procesos refrescados
- [ ] Click en una fila → modal abre con datos de Integrado/Portal
- [ ] Cerrar la app → verificar que el sidecar `dra-cami-api.exe` también termina (no queda zombie)
- [ ] Re-abrir la app → state persistente (`%LOCALAPPDATA%\Dra Cami Contractual\.cache\watched_urls.json`)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
