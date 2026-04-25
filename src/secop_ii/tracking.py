"""Persistent watchlist of SECOP II processes.

The Dra. can pin any SECOP II URL to her own follow-up list. The watchlist
lives in ``%APPDATA%/SecopII/seguimiento.json`` and is independent from
SECOP itself — it's her private curated subset.

Shape of the file:
    {
      "entries": [
        {
          "id": "CO1.NTC.5792792",
          "url": "https://community.secop.gov.co/Public/Tendering/...",
          "added_at": "2026-04-24T21:45:00",
          "note": ""
        },
        ...
      ]
    }

We store both the canonical process ID (when we can derive it) and the
original URL, so the app can drive live queries against SECOP without
any ambiguity.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

_PROCESS_ID_RE = re.compile(r"CO1\.(?:NTC|PPI|REQ|BDOS|PCCNTR)\.\d+", re.I)


def _default_path() -> Path:
    base = os.environ.get("APPDATA") or os.environ.get("HOME") or tempfile.gettempdir()
    p = Path(base) / "SecopII"
    p.mkdir(parents=True, exist_ok=True)
    return p / "seguimiento.json"


@dataclass
class TrackedProcess:
    id: str
    url: str
    added_at: str = ""
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "url": self.url,
            "added_at": self.added_at,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "TrackedProcess":
        return cls(
            id=str(raw.get("id") or ""),
            url=str(raw.get("url") or ""),
            added_at=str(raw.get("added_at") or ""),
            note=str(raw.get("note") or ""),
        )


@dataclass
class Watchlist:
    path: Path = field(default_factory=_default_path)
    _entries: list[TrackedProcess] = field(default_factory=list, init=False)
    _loaded: bool = field(default=False, init=False)

    def entries(self) -> list[TrackedProcess]:
        self._ensure_loaded()
        return list(self._entries)

    def add_url(self, url: str, *, note: str = "") -> TrackedProcess:
        """Add a new process to the watchlist. Returns the created entry.

        Raises ``ValueError`` if ``url`` is empty or can't be parsed into a
        recognizable SECOP II identifier. Idempotent: if the same id is
        already tracked, returns the existing entry (updating the URL if
        it changed).
        """
        if not url or not url.strip():
            raise ValueError("URL vacía")
        url = url.strip()

        pid = _extract_id(url)
        if not pid:
            raise ValueError(
                "La URL no contiene un identificador SECOP II válido "
                "(CO1.NTC.*, CO1.PPI.*, CO1.REQ.*)."
            )

        self._ensure_loaded()
        for existing in self._entries:
            if existing.id == pid:
                # Refresh the URL if the Dra. pasted a newer form.
                if existing.url != url:
                    existing.url = url
                    self._flush()
                return existing

        entry = TrackedProcess(
            id=pid,
            url=url,
            added_at=datetime.now().isoformat(timespec="seconds"),
            note=note,
        )
        self._entries.append(entry)
        self._flush()
        return entry

    def remove(self, pid: str) -> bool:
        """Remove the entry with ``pid``. Returns True if something was removed."""
        self._ensure_loaded()
        before = len(self._entries)
        self._entries = [e for e in self._entries if e.id != pid]
        if len(self._entries) != before:
            self._flush()
            return True
        return False

    def is_tracked(self, pid: str) -> bool:
        self._ensure_loaded()
        return any(e.id == pid for e in self._entries)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self.path.is_file():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        entries = raw.get("entries") if isinstance(raw, dict) else None
        if isinstance(entries, list):
            self._entries = [TrackedProcess.from_dict(e) for e in entries if isinstance(e, dict)]

    def _flush(self) -> None:
        payload = {"entries": [e.to_dict() for e in self._entries]}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass


def _extract_id(url: str) -> str:
    m = _PROCESS_ID_RE.search(url)
    return m.group(0).upper() if m else ""


__all__ = ["TrackedProcess", "Watchlist"]
