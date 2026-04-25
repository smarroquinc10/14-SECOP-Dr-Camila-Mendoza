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

## Auto-updater (la parte clave)

Después del bootstrap install, **vos mandás updates con UN solo comando**.
Cami solo clickea "Actualizar" cuando le aparece el popup.

### Bootstrap (UNA sola vez en la PC de Cami)

1. **Instalar la PRIVATE KEY de Tauri en GitHub Secrets** (esto lo hacés en
   tu PC, una vez):
   ```powershell
   # Lee tu llave privada
   $key = Get-Content "$env:USERPROFILE\.tauri\dra-cami-contractual.key" -Raw

   # Subila a GitHub Secrets via gh CLI (instalá gh con `winget install GitHub.cli`)
   gh secret set TAURI_SIGNING_PRIVATE_KEY --body "$key"

   # Si tu llave NO tiene password, set TAURI_SIGNING_PRIVATE_KEY_PASSWORD vacío:
   gh secret set TAURI_SIGNING_PRIVATE_KEY_PASSWORD --body ""
   ```

2. **Build local del MSI con seed completo** (la versión 1.0.0 que va a la
   PC de Cami):
   ```powershell
   .\scripts\release.ps1 -Version 1.0.0 "v1.0.0 — bootstrap"
   # GitHub Actions compila, pero ese MSI no tiene seed.
   # Para el bootstrap usamos el MSI LOCAL que ya hicimos a mano.
   ```

   El MSI local (con seed de los 491 procesos) está en
   `tauri/target/release/bundle/msi/Dra Cami Contractual_1.0.0_x64_es-ES.msi`.

3. **Instalar en la PC de Cami**:
   - Copiar el `.msi` por USB / OneDrive / mail.
   - Doble click → wizard español → Siguiente → Instalar.
   - Verificar que aparece el ícono "Dra Cami Contractual" en su escritorio.
   - Doble click al ícono. SmartScreen muestra "editor desconocido" la
     primera vez → "Más información" → "Ejecutar de todos modos".
   - La app abre con sus 491 procesos.

Listo. **Eso es lo único manual que vas a hacer en su PC.**

### Updates futuros (todas las veces)

Desde TU PC, al raíz del repo:

```powershell
# 1. Hacés tus cambios al código (lo que sea)
# 2. Un solo comando:
.\release.bat "fix: la tabla rompía con vigencias mixtas"
```

Eso hace TODO:
- Bumpea versión (1.0.0 → 1.0.1) en `tauri.conf.json`, `Cargo.toml`,
  `app/package.json`, `pyproject.toml`
- Commitea `chore: release v1.0.1` + tu mensaje como nota
- Crea tag `v1.0.1` con anotación
- `git push --follow-tags`

GitHub Actions detecta el tag, en ~12 minutos:
- Compila Python + Next + Rust + MSI
- Firma con tu llave Ed25519 (pubkey ya embebida en la app de Cami)
- Publica en GitHub Releases con el `.msi`, `.sig` y `latest.json`

### Lo que ve Cami

La próxima vez que abre la app (o cada 4 horas si la deja abierta), aparece
un cartelito chiquito en la esquina inferior derecha:

```
┌─────────────────────────────────────┐
│  ↻  Hay una actualización           │
│      v1.0.1                         │
│      fix: la tabla rompía con       │
│      vigencias mixtas               │
│                                     │
│         [Más tarde]  [Actualizar]   │
└─────────────────────────────────────┘
```

Click **Actualizar** → barra de progreso → app se reinicia → trabaja con la
versión nueva. Su watch list, audit log y observaciones quedan intactos
(viven en `%LOCALAPPDATA%`, el updater no los toca).

### Variantes del comando release

```powershell
# Patch bump (1.0.0 → 1.0.1) — uso normal para bugs / cambios chicos
.\release.bat "fix: typo en el modal"

# Minor bump (1.0.5 → 1.1.0) — cuando agregás un feature
.\release.bat -Minor "agregada columna de adiciones"

# Major bump (1.x.x → 2.0.0) — cambios que rompen flujo
.\release.bat -Major "rewrite del frontend"

# Versión específica
.\release.bat -Version 2.5.7 "release especial"

# Dry-run (no commitea ni pushea, solo imprime qué haría)
.\release.bat -DryRun "test"
```

### Si CI falla (cómo investigar)

GitHub Actions muestra los logs en:
`https://github.com/smarroquinc10/14-SECOP-Dr-Camila-Mendoza/actions`

Errores comunes:
- **"No .sig found"** → faltó el secret `TAURI_SIGNING_PRIVATE_KEY` o el password
- **PyInstaller fail** → algún cambio en api.py introdujo un import nuevo que
  hay que excluir o whitelistear con `--hidden-import`
- **TypeScript error** → corré `cd app; npm run build` local antes del release

Si algo falla, hacé `git tag -d vX.Y.Z` y `git push origin :vX.Y.Z` para
borrar el tag fallido, arreglá el problema, y volvé a correr el release.
GitHub no permite re-publicar el mismo tag automáticamente.

### Si querés rollback

Si una versión rompe algo en la PC de Cami, **NO pushees un downgrade del
auto-updater** (no funcionan los downgrades). En cambio:

1. Hacés un nuevo release con un fix:
   ```powershell
   .\release.bat "fix: rollback del problema introducido en v1.2.0"
   ```
2. Versión 1.2.0 (rota) → 1.2.1 (con el fix). Cami va a 1.2.1.

Si urge y no tenés tiempo de fixear:
- En tu PC: `git revert <commit-roto>` + `release.bat "rollback"`.
- O entrás a la PC de Cami y le instalás manual el MSI viejo.

## Estado actual

- ✅ `Cargo.toml`, `tauri.conf.json`, `src/main.rs` listos para Tauri 2
- ✅ `capabilities/default.json` con permisos `core:default + updater:default + process:default`
- ✅ Sidecar 200MB (Python + uvicorn + fastapi + secop_ii + seed)
- ✅ Sidecar smoke test verde: /health, /watch (491 items), /entity/feab,
   /audit-log (intact: True), /integrado-sync (runpy con UTF-8)
- ✅ Sidecar UTF-8 stdout (las flechas y checkmarks no rompen los logs)
- ✅ State dir abstraction — `%LOCALAPPDATA%\Dra Cami Contractual\.cache\`
- ✅ First-run seed: copia 8 entries (watch list + audit + caches)
- ✅ Logging a `logs\sidecar.log`
- ✅ **Auto-updater** firmado con minisign Ed25519, popup en frontend,
   GitHub Actions release pipeline en `.github/workflows/release.yml`
- ✅ **Release one-liner** `release.bat "msg"` desde la raíz del repo
