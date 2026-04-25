r"""Per-environment state directory for the FEAB system.

When the app runs from the dev tree (`python -m secop_ii.api`,
`ejecutar_pro.bat`, pytest), `state_dir()` resolves to ``<repo>/.cache/``
exactly like the legacy code expected.

When it runs from a PyInstaller-frozen MSI (`dra-cami-api.exe` spawned
by Tauri), the executable lives under ``Program Files\Dra Cami
Contractual\`` which is read-only for the user, and ``__file__`` of
every bundled module points into ``sys._MEIPASS`` — a temp directory
that PyInstaller wipes on exit. Persistent state has to live elsewhere,
so on Windows we use ``%LOCALAPPDATA%\Dra Cami Contractual\.cache\``
(per-user, writable, survives reboots and uninstalls).

Filosofía cardinal: this module never DECIDES anything about the data
itself — it only relocates the directory. The audit log, watch list,
integrado cache and portal snapshots keep their exact names and
formats. Tests can still monkeypatch ``api._WATCH_PATH`` etc.

The shape of the resolved tree (whether dev or MSI) is:

    <state_dir>/
        watched_urls.json
        audit_log.jsonl
        secop_integrado.json
        portal_opportunity.json
        portal_progress.jsonl
        portal_html/
        snapshots/
        ...

so anyone reading or writing it doesn't care which environment they're in.
"""
from __future__ import annotations

import functools
import os
import sys
from pathlib import Path

_APP_FOLDER_NAME = "Dra Cami Contractual"


def _frozen() -> bool:
    """True when running inside a PyInstaller bundle (the MSI sidecar)."""
    return bool(getattr(sys, "frozen", False))


def _user_state_root() -> Path:
    """Per-user, writable application data directory for the current OS."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / _APP_FOLDER_NAME
        return Path.home() / "AppData" / "Local" / _APP_FOLDER_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / _APP_FOLDER_NAME
    # Linux / *nix — XDG
    base = os.environ.get("XDG_DATA_HOME")
    if base:
        return Path(base) / _APP_FOLDER_NAME
    return Path.home() / ".local" / "share" / _APP_FOLDER_NAME


def _dev_state_root() -> Path:
    """Repo-local ``.cache/`` (legacy dev layout)."""
    # paths.py lives at <repo>/src/secop_ii/paths.py, so parent.parent.parent
    # is the repo root.
    return Path(__file__).resolve().parent.parent.parent


@functools.lru_cache(maxsize=1)
def state_dir() -> Path:
    """Return ``<root>/.cache/`` for the current execution context.

    Override with the ``DRA_CAMI_STATE_DIR`` environment variable when
    you want the same code to use a custom location — useful for testing
    a frozen bundle against a known-good seed directory.
    """
    override = os.environ.get("DRA_CAMI_STATE_DIR")
    if override:
        d = Path(override)
    elif _frozen():
        d = _user_state_root() / ".cache"
    else:
        d = _dev_state_root() / ".cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def state_path(*parts: str) -> Path:
    """Resolve a relative path inside the state dir.

    Example::

        state_path("watched_urls.json")
        state_path("portal_html", "CO1.NTC.123.html")
    """
    return state_dir().joinpath(*parts)


def reset_state_dir_cache() -> None:
    """Clear the LRU cache (only used by tests that change DRA_CAMI_STATE_DIR)."""
    state_dir.cache_clear()


__all__ = ["state_dir", "state_path", "reset_state_dir_cache"]
