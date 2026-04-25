# Dra Cami Contractual — Empaquetado Tauri (MSI + NSIS)

Tauri 2 shell que envuelve el FastAPI sidecar (PyInstaller-bundled) y la
app Next.js (export estático). El resultado es **un solo `.msi`** que la
Dra. instala con doble click — sin necesidad de Python ni Node.js en su
máquina.

## Arquitectura

```
┌─────────────────────────────────────────────────┐
│  Dra Cami Contractual.exe  (Tauri 2 / Rust)    │
│  ├── WebView2 (Edge) → carga app/out/index.html │
│  └── spawns sidecar:                            │
│      └── dra-cami-api.exe (PyInstaller, 200MB)  │
│          └── FastAPI :8000 + secop_ii package   │
│              + scripts/* (sync, scrape, verify) │
│              + .cache/ seed (first-run copy)    │
└─────────────────────────────────────────────────┘
                       │
                       ▼
%LOCALAPPDATA%\Dra Cami Contractual\
    .cache/        ← state_dir() del sidecar
    logs/          ← stdout/stderr del sidecar
        sidecar.log
```

**Reglas cardinales (idénticas al resto del proyecto):**
- ESPEJO del SECOP. Nunca comer datos.
- Si el sidecar no arranca, mostrar error claro a la Dra.
- Audit log inmutable (hash-chained) sobrevive entre reinstalaciones.

## Requisitos del entorno de build (una sola vez)

1. **Rust toolchain 1.75+** — https://rustup.rs (instala `rustc` + `cargo`).
2. **Tauri CLI v2**:
   ```powershell
   cargo install tauri-cli --version "^2.0"
   ```
3. **PyInstaller** (ya está en el venv via `pip install -e .[dev]`).
4. **WiX 3** y **NSIS** — Tauri los descarga automáticamente la primera
   vez que corre `cargo tauri build`.
5. **WebView2 Runtime** — pre-instalado en Windows 11. Si la Dra está
   en Windows 10, el MSI ya lo lleva embebido.

## Cómo se arma el `.msi` (paso a paso)

```powershell
# 1) Build de Next.js como export estático → app/out/
cd app
npm run build
cd ..

# 2) Bundle de FastAPI con PyInstaller → tauri/binaries/dra-cami-api.exe
$REPO = "$(pwd)"
.\.venv\Scripts\python.exe -m PyInstaller `
  --onefile `
  --name dra-cami-api `
  --distpath "$REPO/tauri/binaries" `
  --workpath "$REPO/build/pyinstaller-work" `
  --specpath "$REPO/build/pyinstaller" `
  --add-data "$REPO/tauri/seed;seed" `
  --add-data "$REPO/scripts;scripts" `
  --paths "$REPO/src" `
  --hidden-import secop_ii.notice_resolver `
  --collect-submodules uvicorn `
  --exclude-module streamlit `
  --exclude-module matplotlib `
  --exclude-module plotly `
  --exclude-module pdfminer `
  --exclude-module pypdfium2 `
  --exclude-module imageio `
  --exclude-module imageio_ffmpeg `
  --exclude-module pywebview `
  --exclude-module webview `
  --exclude-module IPython `
  --exclude-module pandas.io.formats.style `
  --exclude-module playwright `
  --exclude-module patchright `
  --exclude-module pyee `
  --exclude-module greenlet `
  --noconfirm `
  "$REPO/src/secop_ii/api.py"

# 3) Curated seed dir → tauri/seed/
mkdir -p tauri/seed
cp .cache/watched_urls.json tauri/seed/
cp .cache/audit_log.jsonl tauri/seed/
cp .cache/feab_headers.json tauri/seed/
cp .cache/ppi_ntc.json tauri/seed/
cp .cache/secop_integrado.json tauri/seed/
cp .cache/portal_opportunity.json tauri/seed/
cp -r .cache/snapshots tauri/seed/
cp -r .cache/portal_html tauri/seed/

# 4) Generar tauri/icons/icon.ico desde feab-logo.png (multi-size + padding)
.\.venv\Scripts\python.exe -c "from PIL import Image; src = Image.open('app/public/feab-logo.png').convert('RGBA'); canvas = Image.new('RGBA', (256,256), (0,0,0,0)); target_w = int(256*0.92); target_h = max(1, int(src.size[1]*target_w/src.size[0])); resized = src.resize((target_w, target_h), Image.LANCZOS); canvas.paste(resized, ((256-target_w)//2, (256-target_h)//2), resized); canvas.save('tauri/icons/icon.ico', sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)])"

# 5) cargo tauri build → MSI + NSIS portable
cd tauri
cargo tauri build
```

Salida:
- `tauri/target/release/bundle/msi/Dra_Cami_Contractual_1.0.0_x64_es-ES.msi`
- `tauri/target/release/bundle/nsis/Dra_Cami_Contractual_1.0.0_x64-setup.exe`

## Filosofía: state_dir() y first-run seed

El sidecar Python (`dra-cami-api.exe`) NO escribe en `Program Files\`
(es read-only para usuarios standard). En su lugar, usa
`secop_ii/paths.py:state_dir()` que en frozen mode resuelve a
`%LOCALAPPDATA%\Dra Cami Contractual\.cache\`.

En el **primer arranque** después del install, el sidecar detecta el
state dir vacío y copia los seeds embebidos (`tauri/seed/*` → bundleados
en `_MEIPASS/seed/` por PyInstaller `--add-data`) a `state_dir()`. La
Dra ve sus 491 procesos al instante.

En **arranques siguientes**, el seed se salta — la data del usuario
nunca se sobreescribe (incluso si reinstala el MSI con un seed más
nuevo).

## Logging (debugging post-mortem)

El sidecar escribe stdout/stderr a:
```
%LOCALAPPDATA%\Dra Cami Contractual\logs\sidecar.log
```

Si la Dra reporta "no abre" o "no carga la tabla", abrir ese archivo
muestra el boot timestamp, el code_version (git short SHA), errores
de uvicorn, etc. El header de cada arranque incluye `epoch=<seconds>`
para correlacionar con incidentes.

## CORS (importante para el frontend)

El frontend Next.js corre dentro de WebView2 desde
`http://tauri.localhost` (Windows) o `tauri://localhost` (otros OS) y
hace `fetch` directo a `http://127.0.0.1:8000`. La whitelist en
`src/secop_ii/api.py` incluye:

```python
allow_origins = [
    "http://localhost:3000", "http://127.0.0.1:3000",   # dev
    "http://tauri.localhost", "https://tauri.localhost",  # MSI Windows
    "tauri://localhost",                                  # MSI macOS/Linux
]
allow_methods = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
```

Sin estas entradas el browser bloquea el preflight de DELETE/PUT
(usados por `watchRemove` y `watchUpdate`).

## Code signing (opcional)

Sin firma, Windows muestra "SmartScreen — editor desconocido" la
primera vez. La Dra puede igual instalar haciendo click en "Más
información" → "Ejecutar de todos modos". Para firmar (requiere
certificado pagado de DigiCert/Sectigo/etc):

```powershell
$env:TAURI_SIGNING_PRIVATE_KEY = "<path al .key>"
$env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD = "<contraseña>"
cargo tauri build
```

## Troubleshooting

**"Error loading ASGI app. Could not import module secop_ii.api"**
→ El bundled .exe trata `api.py` como `__main__`, no como `secop_ii.api`.
Verificar que `main()` use `uvicorn.run(app, ...)` (objeto), no
`uvicorn.run("secop_ii.api:app", ...)` (string).

**`UnicodeEncodeError: 'charmap' codec can't encode character '→'`**
→ Stdout default de PyInstaller en Windows es cp1252. `main()` debe
hacer `sys.stdout.reconfigure(encoding='utf-8', errors='replace')`
cuando `getattr(sys, "frozen", False)`.

**`/integrado-sync` retorna 200 pero no actualiza el cache**
→ En MSI mode el script corre via `runpy.run_path` (no subprocess).
Verificar el log en `%LOCALAPPDATA%\Dra Cami Contractual\logs\sidecar.log`
para ver el traceback del thread que ejecutó el script.

**MSI install fail con error de WiX**
→ Tauri descarga WiX 3 a `%USERPROFILE%\AppData\Local\tauri\WixTools`.
Borrar esa carpeta y re-correr `cargo tauri build` fuerza la re-descarga.

**"El sistema no puede encontrar la ruta especificada" en beforeBuildCommand**
→ Tauri ejecuta el comando vía `cmd /c`, que se confunde con paths
absolutos con espacios. Solución: pre-correr `npm run build` antes
de `cargo tauri build` y dejar `beforeBuildCommand` vacío en la config.

## Estado actual

- ✅ `Cargo.toml`, `tauri.conf.json`, `src/main.rs` listos para Tauri 2
- ✅ `capabilities/default.json` (mandatorio en Tauri 2)
- ✅ Sidecar 200MB (Python + uvicorn + fastapi + secop_ii + seed)
- ✅ Sidecar smoke test verde: /health, /watch (491 items), /entity/feab,
   /audit-log (intact: True), /integrado-sync (runpy con UTF-8)
- ✅ Sidecar UTF-8 stdout (las flechas y checkmarks no rompen los logs)
- ✅ State dir abstraction — `%LOCALAPPDATA%\Dra Cami Contractual\.cache\`
- ✅ First-run seed: copia 8 entries (watch list + audit + caches)
- ✅ Logging a `logs\sidecar.log`
