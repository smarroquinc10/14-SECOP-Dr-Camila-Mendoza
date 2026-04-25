// Sistema de Seguimiento Contratos FEAB · Dra Cami
// Tauri shell — lanza el sidecar FastAPI (PyInstaller-bundled)
// y abre la app Next.js dentro de una ventana nativa Windows.
//
// Filosofía cardinal idéntica al resto del proyecto:
//   - ESPEJO del SECOP. No comer datos.
//   - Si el sidecar no arranca, mostrar error claro a la usuaria;
//     NUNCA seguir como si todo estuviera bien.

#![cfg_attr(
    all(not(debug_assertions), target_os = "windows"),
    windows_subsystem = "windows"
)]

use std::fs::{create_dir_all, File, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use tauri::{Manager, RunEvent, State};

/// Carpeta de datos por-usuario. Coincide con `secop_ii/paths.py:_APP_FOLDER_NAME`
/// para que el sidecar Python y este shell Rust compartan exactamente la
/// misma ubicación on-disk (sin variables de entorno overrides).
const APP_FOLDER: &str = "Dra Cami Contractual";

/// Estado global: handle del sidecar para poder matarlo al cerrar.
struct ApiSidecar(Mutex<Option<Child>>);

/// Carpeta per-usuario donde escribimos logs y leemos el `.cache/`.
/// Idéntica al resultado de `paths.state_dir().parent` en Python.
fn user_state_root() -> PathBuf {
    if cfg!(target_os = "windows") {
        let base = std::env::var("LOCALAPPDATA")
            .ok()
            .map(PathBuf::from)
            .or_else(|| {
                std::env::var("USERPROFILE")
                    .ok()
                    .map(|h| PathBuf::from(h).join("AppData").join("Local"))
            })
            .unwrap_or_else(|| PathBuf::from("."));
        base.join(APP_FOLDER)
    } else if cfg!(target_os = "macos") {
        PathBuf::from(std::env::var("HOME").unwrap_or_else(|_| ".".to_string()))
            .join("Library")
            .join("Application Support")
            .join(APP_FOLDER)
    } else {
        let base = std::env::var("XDG_DATA_HOME")
            .ok()
            .map(PathBuf::from)
            .unwrap_or_else(|| {
                PathBuf::from(std::env::var("HOME").unwrap_or_else(|_| ".".to_string()))
                    .join(".local")
                    .join("share")
            });
        base.join(APP_FOLDER)
    }
}

/// Abre (o crea, append) el log file donde el sidecar escribe stdout/stderr.
/// Si falla cualquier paso, devolvemos None y main() cae a `Stdio::null()`
/// — preferimos un sidecar silencioso a no arrancar.
fn open_sidecar_log(state: &Path) -> Option<File> {
    let log_dir = state.join("logs");
    create_dir_all(&log_dir).ok()?;
    OpenOptions::new()
        .create(true)
        .append(true)
        .open(log_dir.join("sidecar.log"))
        .ok()
}

/// Arranca el `dra-cami-api(.exe)` que PyInstaller dejó en `binaries/`
/// junto a este ejecutable Tauri.
fn spawn_sidecar(app_dir: &Path) -> Result<Child, String> {
    let exe_name = if cfg!(target_os = "windows") {
        "dra-cami-api.exe"
    } else {
        "dra-cami-api"
    };
    let bin_path = app_dir.join("binaries").join(exe_name);

    if !bin_path.exists() {
        return Err(format!(
            "Sidecar no instalado en {bin_path:?}. Reinstalá el MSI."
        ));
    }

    let state = user_state_root();
    let _ = create_dir_all(&state);
    let mut cmd = Command::new(&bin_path);

    // Force UTF-8 for stdout/stderr/locale so scripts that print '→' or '✓'
    // (the user's existing CLI scripts) don't crash on Windows' default
    // cp1252 codec when their output is redirected to a file.
    cmd.env("PYTHONUTF8", "1");
    cmd.env("PYTHONIOENCODING", "utf-8:replace");

    // Header al log file para correlacionar arranques con incidencias.
    if let Some(mut log) = open_sidecar_log(&state) {
        let _ = writeln!(
            log,
            "\n──── sidecar boot · {} ────",
            chrono_lite_now()
        );
        match log.try_clone() {
            Ok(log2) => {
                cmd.stdout(log).stderr(log2);
            }
            Err(_) => {
                cmd.stdout(Stdio::null()).stderr(Stdio::null());
            }
        }
    } else {
        cmd.stdout(Stdio::null()).stderr(Stdio::null());
    }

    cmd.spawn()
        .map_err(|e| format!("No pude lanzar el sidecar {bin_path:?}: {e}"))
}

/// Timestamp ISO-8601 sin agregar dependencia de `chrono`.
/// Suficiente para correlacionar entries del log con los del audit_log.
fn chrono_lite_now() -> String {
    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    format!("epoch={now}")
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(ApiSidecar(Mutex::new(None)))
        .setup(|app| {
            // En el MSI instalado, los recursos viven junto al .exe. En dev
            // (`cargo tauri dev`) suelen estar al `current_dir`. Caemos a
            // `current_dir` solo si Tauri no resolvió el resource_dir.
            let resource_dir = app
                .path()
                .resource_dir()
                .unwrap_or_else(|_| std::env::current_dir().unwrap());
            match spawn_sidecar(&resource_dir) {
                Ok(child) => {
                    let api_state: State<ApiSidecar> = app.state();
                    *api_state.0.lock().unwrap() = Some(child);
                }
                Err(err) => {
                    // No mata la app: el frontend mostrará el error de
                    // conexión al backend si :8000 no responde — al menos
                    // se puede leer la advertencia y reportar.
                    eprintln!("[dra-cami] {err}");
                    if let Some(mut log) = open_sidecar_log(&user_state_root()) {
                        let _ = writeln!(log, "[dra-cami] spawn falló: {err}");
                    }
                }
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error mientras se ejecuta la app Tauri")
        .run(|app, event| {
            if let RunEvent::ExitRequested { .. } = event {
                if let Some(api_state) = app.try_state::<ApiSidecar>() {
                    if let Some(mut child) = api_state.0.lock().unwrap().take() {
                        let _ = child.kill();
                        let _ = child.wait();
                    }
                }
            }
        });
}
