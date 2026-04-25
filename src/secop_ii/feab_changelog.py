"""Track what moved in SECOP between refreshes of the FEAB dashboard.

The Dra. is the head of contratación. When she opens the app, what she
cares about isn't "how many total contracts exist" — she already knows.
She wants "what moved since I last looked": new processes, new
contracts, phase changes, state changes, adjudication events.

How it works:

1. Every time the dashboard pulls a fresh snapshot from SECOP, we persist
   a compact fingerprint of every process + contract under
   ``%APPDATA%/SecopII/feab_snapshots/<timestamp>.json``.
2. On the next pull, we load the most recent previous snapshot and diff
   it against the current one. The diff is what the UI shows.
3. We only keep watched fields in the fingerprint (fase, adjudicado,
   estado_contrato, valor_del_contrato) so snapshots stay small (a few
   hundred KB for ~1000 FEAB processes).
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd

from secop_ii.feab_dashboard import FeabSnapshot

_WATCHED_PROC = ("fase", "adjudicado", "valor_total_adjudicacion")
_WATCHED_CTR = ("estado_contrato", "valor_del_contrato", "valor_pagado")


def _default_dir() -> Path:
    base = os.environ.get("APPDATA") or os.environ.get("HOME") or tempfile.gettempdir()
    p = Path(base) / "SecopII" / "feab_snapshots"
    p.mkdir(parents=True, exist_ok=True)
    return p


@dataclass
class FeabChangelog:
    prev_at: str = ""                          # timestamp of the previous snapshot
    new_processes: list[str] = field(default_factory=list)
    new_contracts: list[str] = field(default_factory=list)
    phase_changes: list[tuple[str, str, str]] = field(default_factory=list)  # (pid, old, new)
    adjudicated_now: list[str] = field(default_factory=list)                  # pids that flipped No→Si
    contract_state_changes: list[tuple[str, str, str]] = field(default_factory=list)
    gone_processes: list[str] = field(default_factory=list)
    gone_contracts: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return (
            len(self.new_processes) + len(self.new_contracts)
            + len(self.phase_changes) + len(self.adjudicated_now)
            + len(self.contract_state_changes)
            + len(self.gone_processes) + len(self.gone_contracts)
        )

    @property
    def is_empty(self) -> bool:
        return self.total == 0


def _extract(snap: FeabSnapshot) -> dict:
    """Reduce a snapshot to just the watched columns keyed by ID."""
    procs: dict[str, dict] = {}
    ctrs: dict[str, dict] = {}
    if not snap.processes.empty and "id_del_proceso" in snap.processes.columns:
        for _, row in snap.processes.iterrows():
            pid = str(row.get("id_del_proceso") or "")
            if not pid:
                continue
            procs[pid] = {f: _stringify(row.get(f)) for f in _WATCHED_PROC}
    if not snap.contracts.empty and "id_contrato" in snap.contracts.columns:
        for _, row in snap.contracts.iterrows():
            cid = str(row.get("id_contrato") or "")
            if not cid:
                continue
            ctrs[cid] = {f: _stringify(row.get(f)) for f in _WATCHED_CTR}
    return {"processes": procs, "contracts": ctrs}


def save_snapshot(snap: FeabSnapshot, *, cache_dir: Path | None = None) -> Path:
    cache_dir = cache_dir or _default_dir()
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    target = cache_dir / f"{stamp}.json"
    payload = {
        "stamp": stamp,
        "fetched_at": snap.fetched_at,
        **_extract(snap),
    }
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def load_previous_snapshot(
    current_stamp: str = "", *, cache_dir: Path | None = None
) -> dict | None:
    """Return the most recent snapshot strictly before ``current_stamp``."""
    cache_dir = cache_dir or _default_dir()
    if not cache_dir.is_dir():
        return None
    files = sorted(cache_dir.glob("*.json"), reverse=True)
    for p in files:
        if current_stamp and p.stem >= current_stamp:
            continue
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
    return None


def compute_changelog(current: FeabSnapshot, previous: dict | None) -> FeabChangelog:
    cur = _extract(current)
    if previous is None:
        return FeabChangelog()  # empty diff = "no previous baseline"

    prev_proc = previous.get("processes") or {}
    prev_ctr = previous.get("contracts") or {}

    cur_proc_ids = set(cur["processes"])
    prev_proc_ids = set(prev_proc)
    cur_ctr_ids = set(cur["contracts"])
    prev_ctr_ids = set(prev_ctr)

    cl = FeabChangelog(prev_at=str(previous.get("fetched_at") or ""))
    cl.new_processes = sorted(cur_proc_ids - prev_proc_ids)
    cl.gone_processes = sorted(prev_proc_ids - cur_proc_ids)
    cl.new_contracts = sorted(cur_ctr_ids - prev_ctr_ids)
    cl.gone_contracts = sorted(prev_ctr_ids - cur_ctr_ids)

    for pid in sorted(cur_proc_ids & prev_proc_ids):
        c = cur["processes"][pid]
        p = prev_proc.get(pid) or {}
        if c.get("fase") != p.get("fase") and c.get("fase") and p.get("fase"):
            cl.phase_changes.append((pid, p.get("fase", ""), c.get("fase", "")))
        if p.get("adjudicado") == "No" and c.get("adjudicado") == "Si":
            cl.adjudicated_now.append(pid)

    for cid in sorted(cur_ctr_ids & prev_ctr_ids):
        c = cur["contracts"][cid]
        p = prev_ctr.get(cid) or {}
        if c.get("estado_contrato") != p.get("estado_contrato") \
                and c.get("estado_contrato") and p.get("estado_contrato"):
            cl.contract_state_changes.append(
                (cid, p.get("estado_contrato", ""), c.get("estado_contrato", ""))
            )

    return cl


def _stringify(v) -> str:
    if v is None:
        return ""
    try:
        if pd.isna(v):
            return ""
    except (TypeError, ValueError):
        pass
    return str(v).strip()


__all__ = [
    "FeabChangelog",
    "compute_changelog",
    "load_previous_snapshot",
    "save_snapshot",
]
