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

use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use tauri::{Manager, RunEvent, State};

/// Estado global: handle del sidecar para poder matarlo al cerrar.
struct ApiSidecar(Mutex<Option<Child>>);

fn spawn_sidecar(app_dir: &std::path::Path) -> Result<Child, String> {
    // El binario se incluye como "externalBin" en tauri.conf.json y se
    // copia a `binaries/dra-cami-api(.exe)` junto al ejecutable Tauri.
    let exe_name = if cfg!(target_os = "windows") {
        "dra-cami-api.exe"
    } else {
        "dra-cami-api"
    };
    let bin_path = app_dir.join("binaries").join(exe_name);
    Command::new(&bin_path)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|e| format!("No pude lanzar el sidecar {bin_path:?}: {e}"))
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(ApiSidecar(Mutex::new(None)))
        .setup(|app| {
            let resource_dir = app
                .path()
                .resource_dir()
                .unwrap_or_else(|_| std::env::current_dir().unwrap());
            match spawn_sidecar(&resource_dir) {
                Ok(child) => {
                    let state: State<ApiSidecar> = app.state();
                    *state.0.lock().unwrap() = Some(child);
                }
                Err(err) => {
                    eprintln!("[dra-cami] {err}");
                    // Continuar igual: el frontend mostrará el error de
                    // conexión al backend si :8000 no responde.
                }
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error mientras se ejecuta la app Tauri")
        .run(|app, event| {
            if let RunEvent::ExitRequested { .. } = event {
                let state: State<ApiSidecar> = app.state();
                if let Some(mut child) = state.0.lock().unwrap().take() {
                    let _ = child.kill();
                }
            }
        });
}
