# Dra Cami Contractual — Tauri shell

Empaquetado nativo Windows (MSI + NSIS) del Sistema de Seguimiento
Contratos FEAB · Dra Cami. Cuando esté firmado y testeado, Camila
recibe **un solo `.msi`** que instala con doble click — sin Python,
sin Node, sin browser.

## Requisitos del entorno de build (una sola vez)

1. **Rust toolchain** — https://rustup.rs (instala `rustc` + `cargo`).
2. **Tauri CLI v2**:
   ```powershell
   cargo install tauri-cli --version "^2.0"
   ```
3. **WiX Toolset 3.x** (para MSI) — instalado por Tauri en el primer build.
4. **PyInstaller** (ya está en `pyproject.toml [dev]`).

## Cómo se arma el `.msi`

```powershell
# 1) Bundlear FastAPI como sidecar Windows (.exe)
.\.venv\Scripts\python.exe -m PyInstaller `
    --onefile `
    --name dra-cami-api `
    --distpath tauri/binaries `
    --add-data "src/secop_ii;secop_ii" `
    src/secop_ii/api.py

# 2) Generar icon.ico desde feab-logo.png (PowerShell + System.Drawing)
#    (Tauri necesita .ico en tauri/icons/icon.ico)
.\.venv\Scripts\python.exe -c "from PIL import Image; Image.open('app/public/feab-logo.png').save('tauri/icons/icon.ico', sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)])"

# 3) Build estático del frontend Next.js
cd app
npm run build       # requiere `output: 'export'` en next.config (ver nota)
cd ..

# 4) Build del MSI
cd tauri
cargo tauri build
```

El instalador queda en `tauri/target/release/bundle/msi/Dra_Cami_Contractual_*.msi`.

## Nota: Next.js export estático

`next.config.js` necesita:

```js
module.exports = {
  output: 'export',
  images: { unoptimized: true },
}
```

Si la app usa endpoints `/api/*` del propio Next, hay que reemplazarlos
por llamadas directas al sidecar `http://127.0.0.1:8000/...`.

## Code signing (opcional pero recomendado)

Sin firma, Windows muestra "SmartScreen — editor desconocido" la primera
vez. Para firmar:

```powershell
# Comprar / generar certificado de signing (DigiCert, Sectigo, etc.)
$env:TAURI_SIGNING_PRIVATE_KEY = "<path al .key>"
$env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD = "<contraseña>"
cargo tauri build
```

## Estado actual del scaffold

✓ `Cargo.toml` — crate manifest
✓ `tauri.conf.json` — title, MSI bundle, sidecar declarado
✓ `src/main.rs` — entry point Rust que lanza/mata el sidecar FastAPI
✓ `build.rs` — build script default

⚠ Pendiente para que `cargo tauri build` corra de punta a punta:
- Instalar Rust (rustup) en la máquina de build
- Generar `tauri/icons/icon.ico` desde `app/public/feab-logo.png`
- Bundlear el FastAPI con PyInstaller a `tauri/binaries/dra-cami-api.exe`
- Configurar Next.js para `output: 'export'` y reemplazar endpoints `/api/*`
- (Opcional) certificado de signing

Mientras tanto, la Dra usa `ejecutar_pro.bat` que abre la ventana con
**pywebview** (sin URL bar, ya nativa) — equivalente funcional sin
necesidad de Rust.
