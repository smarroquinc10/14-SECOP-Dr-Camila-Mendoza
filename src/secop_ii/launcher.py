"""Entry point for the packaged Windows ``.exe``.

Starts a local Streamlit server bound to ``127.0.0.1`` on the first free
port, opens the user's default browser on that URL, and blocks until the
process is killed (closing the browser is enough — the console-less
PyInstaller build exits with the Streamlit server).

Running this file directly during development is also supported:
``python -m secop_ii.launcher`` opens the same UI.
"""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path


def _resource_path(relative: str) -> Path:
    """Resolve a bundled resource path under PyInstaller and in dev.

    PyInstaller extracts data files under ``sys._MEIPASS``. When running
    from source, the path is the regular module location.
    """
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / relative
    return Path(__file__).resolve().parent / relative


def _find_free_port(preferred: int = 8501) -> int:
    for port in (preferred, *range(preferred + 1, preferred + 20)):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    # Fall back to any free port assigned by the OS.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _open_browser_later(url: str, delay_s: float = 1.5) -> None:
    def _open():
        try:
            webbrowser.open(url, new=2)
        except Exception:
            pass

    threading.Timer(delay_s, _open).start()


def main() -> None:
    app_path = _resource_path("ui/streamlit_app.py")
    if not app_path.is_file():
        # Fall back to the packaged location used by PyInstaller --add-data.
        alt = _resource_path("streamlit_app.py")
        if alt.is_file():
            app_path = alt
    if not app_path.is_file():
        print(f"No encuentro la UI en {app_path}", file=sys.stderr)
        sys.exit(1)

    port = _find_free_port()
    url = f"http://127.0.0.1:{port}"
    _open_browser_later(url)

    # Streamlit reads the command line via ``sys.argv`` when called as a
    # module, so we rewrite it to emulate: ``streamlit run <app>``.
    sys.argv = [
        "streamlit",
        "run",
        str(app_path),
        "--server.address=127.0.0.1",
        f"--server.port={port}",
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
        "--global.developmentMode=false",
    ]

    # Import inside main so a missing Streamlit produces a friendly error.
    try:
        from streamlit.web import cli as stcli
    except ImportError as exc:
        print(
            "Streamlit no está instalado. Ejecuta: pip install -r requirements.txt",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc

    # stcli.main() never returns under normal operation; it serves until killed.
    sys.exit(stcli.main())


if __name__ == "__main__":
    main()
