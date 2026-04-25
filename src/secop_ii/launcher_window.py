"""Launcher de ventana nativa (pywebview) — versión PRO con UI propia.

Arranca FastAPI :8000 + Next.js :3000 y abre la app dentro de una ventana
nativa de Windows (sin barra de URL, sin pestañas, sin chrome del browser).
Si pywebview no está disponible, hace fallback al browser por defecto.

Pensado para que la Dra. (y eventualmente Camila) haga doble-click en
``ejecutar_pro.bat`` y vea una ventana institucional con el título
"Sistema de Seguimiento Contratos FEAB · Dra Cami".

Cuando se cierra la ventana se matan FastAPI y Next limpiamente.
"""
from __future__ import annotations

import atexit
import logging
import os
import signal
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

log = logging.getLogger("dra-cami-window")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

ROOT = Path(__file__).resolve().parent.parent.parent
APP_DIR = ROOT / "app"
ICON_PNG = APP_DIR / "public" / "feab-logo.png"
INTEGRADO_CACHE = ROOT / ".cache" / "secop_integrado.json"
INTEGRADO_MAX_AGE_HOURS = 24  # más viejo que esto = re-sync en background

WINDOW_TITLE = "Sistema de Seguimiento Contratos FEAB · Dra Cami"
WINDOW_URL = "http://localhost:3000"


def _maybe_sync_integrado() -> None:
    """Si el cache de SECOP Integrado (rpmr-utcd) es viejo o no existe,
    lanza el script de sync en BACKGROUND. No bloquea el arranque — el
    sync toma ~1s. Si falla (sin red, etc.), la app sigue arrancando
    con el cache anterior (idempotente: nunca borra lo bueno por lo
    nuevo).

    Cardinal: del API público filtrado por NIT FEAB. Si datos.gov.co
    está caído, mostramos lo último que ya teníamos en cache, NUNCA
    inventamos."""
    needs_sync = True
    if INTEGRADO_CACHE.exists():
        age = time.time() - INTEGRADO_CACHE.stat().st_mtime
        if age < INTEGRADO_MAX_AGE_HOURS * 3600:
            needs_sync = False
            log.info(
                "SECOP Integrado cache fresco (%.1fh, < %dh) — skip sync",
                age / 3600, INTEGRADO_MAX_AGE_HOURS,
            )
    if needs_sync:
        log.info("Lanzando sync SECOP Integrado en background…")
        try:
            subprocess.Popen(
                [sys.executable, "scripts/sync_secop_integrado.py"],
                cwd=str(ROOT),
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            log.warning("No pude lanzar sync Integrado: %s", exc)


def _is_port_open(port: int, timeout: float = 1.5) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    finally:
        s.close()


def _wait_for(port: int, label: str, timeout_s: int = 120) -> bool:
    start = time.time()
    while time.time() - start < timeout_s:
        if _is_port_open(port):
            log.info("%s listo en :%d", label, port)
            return True
        time.sleep(0.5)
    log.warning("%s no respondió en %ds", label, timeout_s)
    return False


def _start_servers() -> tuple[subprocess.Popen, subprocess.Popen]:
    py_exe = sys.executable
    api_proc = subprocess.Popen(
        [py_exe, "-m", "secop_ii.api"],
        cwd=str(ROOT),
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )
    log.info("FastAPI PID %d", api_proc.pid)

    npm = "npm.cmd" if os.name == "nt" else "npm"
    if not (APP_DIR / "node_modules").exists():
        log.info("Instalando dependencias npm (primera vez, ~1 min)…")
        subprocess.check_call(
            [npm, "install", "--no-fund", "--no-audit"], cwd=str(APP_DIR)
        )

    next_proc = subprocess.Popen(
        [npm, "run", "dev"],
        cwd=str(APP_DIR),
        env={**os.environ, "BROWSER": "none"},
    )
    log.info("Next.js PID %d", next_proc.pid)
    return api_proc, next_proc


def _cleanup(api_proc: subprocess.Popen, next_proc: subprocess.Popen) -> None:
    log.info("Cerrando servicios…")
    for p in (next_proc, api_proc):
        try:
            if os.name == "nt":
                p.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                p.terminate()
        except Exception:
            pass
    for p in (next_proc, api_proc):
        try:
            p.wait(timeout=5)
        except Exception:
            p.kill()


def _open_window(api_proc: subprocess.Popen, next_proc: subprocess.Popen) -> None:
    """Abre la ventana nativa (pywebview). Bloquea hasta que la cierran."""
    try:
        import webview  # type: ignore
    except ImportError:
        log.warning(
            "pywebview no está instalado — abriendo en navegador. "
            "Para tener ventana propia: pip install pywebview"
        )
        webbrowser.open(WINDOW_URL)
        # Mantener vivo hasta Ctrl+C / muerte de subprocesos
        try:
            while True:
                time.sleep(1)
                if api_proc.poll() is not None or next_proc.poll() is not None:
                    log.error("Un servicio murió. Saliendo.")
                    break
        except KeyboardInterrupt:
            pass
        return

    icon = str(ICON_PNG) if ICON_PNG.exists() else None
    log.info("Abriendo ventana nativa…")
    webview.create_window(
        title=WINDOW_TITLE,
        url=WINDOW_URL,
        width=1400,
        height=900,
        min_size=(900, 600),
        confirm_close=False,
    )
    # icon arg: pywebview en Windows acepta path al .ico/.png en webview.start()
    start_kwargs: dict = {}
    if icon:
        start_kwargs["icon"] = icon
    try:
        webview.start(**start_kwargs)
    except TypeError:
        # Algunas versiones de pywebview no aceptan icon kwarg
        webview.start()


def main() -> None:
    log.info("%s — arrancando…", WINDOW_TITLE)
    _maybe_sync_integrado()
    api_proc, next_proc = _start_servers()
    atexit.register(_cleanup, api_proc, next_proc)
    signal.signal(
        signal.SIGINT,
        lambda *_: (_cleanup(api_proc, next_proc), sys.exit(0)),
    )

    api_ok = _wait_for(8000, "FastAPI", timeout_s=30)
    next_ok = _wait_for(3000, "Next.js", timeout_s=180)

    if not (api_ok and next_ok):
        log.error("Algún servicio no arrancó. Revisá los logs arriba.")
        _cleanup(api_proc, next_proc)
        sys.exit(1)

    _open_window(api_proc, next_proc)
    _cleanup(api_proc, next_proc)


if __name__ == "__main__":
    main()
