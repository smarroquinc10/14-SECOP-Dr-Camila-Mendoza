"""Append-only, hash-chained audit log — tamper-evident operation history.

Every operation that touches the workbook (fill, replace, validate, verify)
appends one entry to ``.cache/audit_log.jsonl``. Each entry contains:

* ``ts``        — UTC ISO-8601 timestamp
* ``op``        — operation type ("fill", "replace", "validate_flag",
                  "verify_drift", "backup", "snapshot")
* ``row``       — workbook row affected
* ``process_id``— SECOP process id
* ``column``    — column header (when applicable)
* ``old``       — previous cell value (for replaces)
* ``new``       — new cell value
* ``source``    — provenance string ("contrato.fecha_de_firma" etc.)
* ``confidence``— HIGH/MEDIUM/LOW
* ``secop_hash``— SHA-256 of the SECOP payload at this moment
* ``prev_hash`` — SHA-256 of the previous log entry (Merkle-chain)
* ``hash``      — SHA-256 of THIS entry (covers all fields above)

The ``prev_hash`` linkage means: if ANY past entry is altered, the
chain breaks at that point and every later entry's stored ``prev_hash``
no longer matches its predecessor's computed hash. Tamper-evident
without external infrastructure. The Dra. (or an auditor) can run
``verify_audit_log()`` to confirm the entire history is intact.

The log is append-only — never rewritten or truncated by the program.
For long-term archival, the user can periodically gzip+sign older
segments without breaking the chain.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

log = logging.getLogger(__name__)
_LOG_LOCK = threading.Lock()


def _code_version() -> str:
    """Short identifier of the running code (git commit hash + dirty flag).

    Stamped into every audit entry so if a stale Python process is running
    old code while we edit the source on disk, the divergence shows up
    in the log immediately — no more silent skipping.
    """
    import subprocess
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL, timeout=2,
        ).decode().strip()
        # Append "-dirty" if there are uncommitted changes
        try:
            subprocess.check_output(
                ["git", "diff", "--quiet"],
                stderr=subprocess.DEVNULL, timeout=2,
            )
        except subprocess.CalledProcessError:
            sha += "-dirty"
        return sha
    except Exception:
        return "unknown"


# Compute once at import — that's intentional: the value reflects the
# code as loaded in memory, NOT the code on disk. If they differ, we
# can detect it by comparing.
_CODE_VERSION = _code_version()


@dataclass
class AuditEntry:
    ts: str
    op: str
    row: int | None = None
    process_id: str | None = None
    column: str | None = None
    old: Any = None
    new: Any = None
    source: str | None = None
    confidence: str | None = None
    secop_hash: str | None = None
    code_version: str | None = None  # git short SHA of the code in memory
    prev_hash: str | None = None
    hash: str = field(default="")

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None or k == "hash"}


def _entry_hash(entry: AuditEntry) -> str:
    """Compute SHA-256 over all fields EXCEPT the hash field itself."""
    payload = entry.as_dict()
    payload.pop("hash", None)
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _last_hash(log_path: Path) -> str:
    """Return the hash of the last entry in the log (or genesis hash if empty)."""
    if not log_path.exists() or log_path.stat().st_size == 0:
        # Genesis hash — well-known constant so the chain has a deterministic root.
        return "0" * 64
    with log_path.open("rb") as f:
        f.seek(0, 2)  # end
        size = f.tell()
        # Read backwards in chunks to find the last newline.
        chunk = 4096
        pos = size
        buf = b""
        while pos > 0:
            read_size = min(chunk, pos)
            pos -= read_size
            f.seek(pos)
            buf = f.read(read_size) + buf
            if buf.count(b"\n") >= 2:
                break
        # Last non-empty line
        lines = [l for l in buf.splitlines() if l.strip()]
        if not lines:
            return "0" * 64
        last = json.loads(lines[-1].decode("utf-8"))
        return last.get("hash", "0" * 64)


def append_entry(
    log_path: Path | str,
    *,
    op: str,
    row: int | None = None,
    process_id: str | None = None,
    column: str | None = None,
    old: Any = None,
    new: Any = None,
    source: str | None = None,
    confidence: str | None = None,
    secop_hash: str | None = None,
) -> AuditEntry:
    """Append a single audit entry to the log file (thread-safe).

    Returns the entry with its hash computed and prev_hash linked.
    """
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    with _LOG_LOCK:
        prev = _last_hash(log_path)
        entry = AuditEntry(
            ts=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            op=op, row=row, process_id=process_id, column=column,
            old=old, new=new, source=source, confidence=confidence,
            secop_hash=secop_hash,
            code_version=_CODE_VERSION,
            prev_hash=prev,
        )
        entry.hash = _entry_hash(entry)
        with log_path.open("a", encoding="utf-8") as f:
            json.dump(entry.as_dict(), f, ensure_ascii=False, default=str)
            f.write("\n")
    return entry


def iter_entries(log_path: Path | str) -> Iterator[AuditEntry]:
    """Stream all entries in chronological (write) order."""
    log_path = Path(log_path)
    if not log_path.exists():
        return
    with log_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            yield AuditEntry(**{k: data.get(k) for k in AuditEntry.__dataclass_fields__})


def verify_audit_log(log_path: Path | str) -> tuple[bool, list[str]]:
    """Walk the log and check the hash-chain integrity.

    Returns ``(intact, problems)``. ``intact`` is True if every entry's
    ``prev_hash`` matches its predecessor's ``hash`` and every entry's
    ``hash`` matches its computed payload hash.
    """
    problems: list[str] = []
    prev = "0" * 64
    n = 0
    for entry in iter_entries(log_path):
        n += 1
        # Verify the entry's own hash is well-formed
        expected = _entry_hash(entry)
        if entry.hash != expected:
            problems.append(
                f"Entry {n} ({entry.ts}): hash {entry.hash[:16]}… "
                f"≠ computed {expected[:16]}…"
            )
        # Verify the chain link
        if entry.prev_hash != prev:
            problems.append(
                f"Entry {n} ({entry.ts}): prev_hash {entry.prev_hash[:16]}… "
                f"≠ expected {prev[:16]}…"
            )
        prev = entry.hash
    return len(problems) == 0, problems


def render_audit_summary(log_path: Path | str) -> str:
    """Human-readable summary of the audit log for a quick scan."""
    counts: dict[str, int] = {}
    first_ts = last_ts = None
    n = 0
    for entry in iter_entries(log_path):
        n += 1
        counts[entry.op] = counts.get(entry.op, 0) + 1
        if first_ts is None:
            first_ts = entry.ts
        last_ts = entry.ts
    intact, problems = verify_audit_log(log_path)
    lines = [
        f"# Audit log — {Path(log_path).name}",
        "",
        f"**Entries:** {n}",
        f"**Period:** {first_ts or '-'} -> {last_ts or '-'}",
        f"**Hash-chain intact:** {'YES' if intact else 'NO'}",
        "",
        "## Operations",
    ]
    for op, c in sorted(counts.items(), key=lambda x: -x[1]):
        lines.append(f"- `{op}`: {c}")
    if problems:
        lines.append("")
        lines.append("## Chain integrity problems")
        for p in problems:
            lines.append(f"- {p}")
    return "\n".join(lines)


__all__ = [
    "AuditEntry",
    "append_entry",
    "iter_entries",
    "verify_audit_log",
    "render_audit_summary",
]
