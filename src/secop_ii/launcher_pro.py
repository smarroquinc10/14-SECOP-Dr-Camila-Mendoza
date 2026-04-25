"""Launcher de la versión PRO (Next.js + FastAPI).

Arranca:
  1. FastAPI bridge en :8000
  2. Next.js dev server en :3000
  3. Abre el navegador apuntando a :3000

Diseñado para que la Dra. haga doble-click en ``ejecutar_pro.bat`` y
todo arranque solo. Maneja Ctrl+C para detener ambos limpiamente.
"""
from __future__ import annotations

import atexit
import logging
import os
import signal
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

log = logging.getLogger("dra-cami-pro")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

ROOT = Path(__file__).resolve().parent.parent.parent
APP_DIR = ROOT / "app"


def _is_port_open(port: int, timeout: float = 1.5) -> bool:
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    finally:
        s.close()


def _wait_for(port: int, label: str, timeout_s: int = 90) -> bool:
    start = time.time()
    while time.time() - start < timeout_s:
        if _is_port_open(port):
            log.info("%s ready on :%d", label, port)
            return True
        time.sleep(0.5)
    log.warning("%s did not become ready in %ds", label, timeout_s)
    return False


def main() -> None:
    log.info("Dra Cami Contractual — arrancando…")

    # ---- 1) FastAPI -------------------------------------------------------
    py_exe = sys.executable
    api_proc = subprocess.Popen(
        [py_exe, "-m", "secop_ii.api"],
        cwd=str(ROOT),
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )
    log.info("FastAPI PID %d", api_proc.pid)

    # ---- 2) Next.js -------------------------------------------------------
    npm = "npm.cmd" if os.name == "nt" else "npm"
    if not (APP_DIR / "node_modules").exists():
        log.info("Instalando dependencias npm (primera vez, ~1 min)…")
        subprocess.check_call([npm, "install", "--no-fund", "--no-audit"],
                            cwd=str(APP_DIR))

    next_proc = subprocess.Popen(
        [npm, "run", "dev"],
        cwd=str(APP_DIR),
        env={**os.environ, "BROWSER": "none"},
    )
    log.info("Next.js PID %d", next_proc.pid)

    # ---- Cleanup ---------------------------------------------------------
    def _cleanup(*_):
        log.info("Cerrando…")
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
    atexit.register(_cleanup)
    signal.signal(signal.SIGINT, lambda *_: (_cleanup(), sys.exit(0)))

    # ---- 3) Wait + open browser ------------------------------------------
    api_ok = _wait_for(8000, "FastAPI", timeout_s=30)
    next_ok = _wait_for(3000, "Next.js", timeout_s=120)

    if api_ok and next_ok:
        log.info("Abriendo navegador…")
        webbrowser.open("http://localhost:3000")
    else:
        log.error("No pude arrancar ambos servicios. Revisa los logs arriba.")

    log.info("Programa corriendo. Cierra esta ventana (o Ctrl+C) para detener.")
    try:
        while True:
            time.sleep(1)
            if api_proc.poll() is not None:
                log.error("FastAPI murió. Saliendo.")
                break
            if next_proc.poll() is not None:
                log.error("Next.js murió. Saliendo.")
                break
    except KeyboardInterrupt:
        pass
    _cleanup()


if __name__ == "__main__":
    main()
