"""Tests for the hash-chained audit log.

The audit log is the program's tamper-evident memory. These tests prove:

* Each entry's hash matches its content.
* prev_hash chains correctly to the previous entry.
* ANY post-hoc modification breaks the chain in a detectable way.
* verify_audit_log() correctly reports problems.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from secop_ii.audit_log import (
    AuditEntry,
    append_entry,
    iter_entries,
    render_audit_summary,
    verify_audit_log,
    _entry_hash,
)


def test_empty_log_verifies_clean(tmp_path: Path):
    """A non-existent log is trivially intact (empty chain)."""
    log = tmp_path / "audit.jsonl"
    intact, problems = verify_audit_log(log)
    assert intact is True
    assert problems == []


def test_single_entry_links_to_genesis(tmp_path: Path):
    """First entry's prev_hash must equal the well-known genesis hash."""
    log = tmp_path / "audit.jsonl"
    entry = append_entry(log, op="fill", row=2, column="x", new="value")
    assert entry.prev_hash == "0" * 64
    assert entry.hash != ""
    assert len(entry.hash) == 64


def test_chain_links_correctly_through_many_entries(tmp_path: Path):
    """Each entry's prev_hash equals the previous entry's hash."""
    log = tmp_path / "audit.jsonl"
    entries = []
    for i in range(10):
        entries.append(append_entry(log, op="fill", row=i, new=f"v{i}"))

    # First entry points to genesis
    assert entries[0].prev_hash == "0" * 64
    # Subsequent entries link to predecessor
    for i in range(1, 10):
        assert entries[i].prev_hash == entries[i - 1].hash, (
            f"Entry {i} prev_hash != entry {i-1}.hash"
        )

    intact, problems = verify_audit_log(log)
    assert intact is True
    assert problems == []


def test_tampering_with_old_entry_breaks_chain(tmp_path: Path):
    """Editing any past entry MUST be detected by the verifier."""
    log = tmp_path / "audit.jsonl"
    for i in range(5):
        append_entry(log, op="fill", row=i, new=f"v{i}")

    # Verify clean state
    intact, _ = verify_audit_log(log)
    assert intact

    # Tamper: edit entry 1's "new" field while leaving its hash unchanged.
    lines = log.read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[1])
    entry["new"] = "TAMPERED"
    lines[1] = json.dumps(entry, ensure_ascii=False)
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")

    intact, problems = verify_audit_log(log)
    assert intact is False
    # The tampered entry's hash no longer matches its computed payload
    assert any("hash" in p.lower() for p in problems)


def test_tampering_with_chain_link_is_detected(tmp_path: Path):
    """Changing an entry's prev_hash MUST break the chain."""
    log = tmp_path / "audit.jsonl"
    for i in range(3):
        append_entry(log, op="fill", row=i, new=f"v{i}")

    lines = log.read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[1])
    entry["prev_hash"] = "f" * 64  # bogus chain link
    # Recompute hash so the OWN entry is consistent — only the link is wrong
    fake_entry = AuditEntry(**{
        k: entry.get(k) for k in AuditEntry.__dataclass_fields__
    })
    entry["hash"] = _entry_hash(fake_entry)
    lines[1] = json.dumps(entry, ensure_ascii=False)
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")

    intact, problems = verify_audit_log(log)
    assert intact is False
    assert any("prev_hash" in p for p in problems)


def test_iter_entries_yields_in_chronological_order(tmp_path: Path):
    log = tmp_path / "audit.jsonl"
    for i in range(5):
        append_entry(log, op="fill", row=i, new=f"v{i}")
    rows = [e.row for e in iter_entries(log)]
    assert rows == [0, 1, 2, 3, 4]


def test_summary_includes_operation_counts(tmp_path: Path):
    log = tmp_path / "audit.jsonl"
    for _ in range(3):
        append_entry(log, op="fill", new="x")
    for _ in range(2):
        append_entry(log, op="replace", old="a", new="b")
    summary = render_audit_summary(log)
    assert "fill" in summary
    assert "replace" in summary
    assert "Hash-chain intact" in summary
    assert "YES" in summary  # intact


def test_appending_after_tamper_does_not_repair_chain(tmp_path: Path):
    """Even after fresh appends, a past tamper must still be detected."""
    log = tmp_path / "audit.jsonl"
    for i in range(3):
        append_entry(log, op="fill", row=i, new=f"v{i}")

    # Tamper with entry 0
    lines = log.read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[0])
    entry["new"] = "TAMPERED"
    lines[0] = json.dumps(entry, ensure_ascii=False)
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Continue appending (program doesn't know about the tamper)
    append_entry(log, op="fill", row=99, new="post-tamper")

    intact, problems = verify_audit_log(log)
    assert intact is False
    assert len(problems) >= 1


def test_audit_entry_hash_is_deterministic():
    """Same content -> same hash. Reproducibility for replay/verification."""
    e1 = AuditEntry(ts="2026-04-24T22:00:00+00:00", op="fill", row=2, new="x",
                    prev_hash="0" * 64)
    e1.hash = _entry_hash(e1)
    e2 = AuditEntry(ts="2026-04-24T22:00:00+00:00", op="fill", row=2, new="x",
                    prev_hash="0" * 64)
    e2.hash = _entry_hash(e2)
    assert e1.hash == e2.hash


def test_audit_entry_hash_changes_with_any_field():
    """Modifying any field changes the hash — total integrity coverage."""
    base = AuditEntry(ts="2026-04-24T22:00:00+00:00", op="fill", row=2, new="x",
                      prev_hash="0" * 64)
    base_hash = _entry_hash(base)

    for field, value in [("row", 3), ("new", "y"), ("op", "replace"),
                         ("ts", "2026-04-24T23:00:00+00:00"),
                         ("prev_hash", "1" * 64)]:
        mut = AuditEntry(**{**base.__dict__, field: value})
        mut.hash = ""  # so _entry_hash recomputes ignoring hash field
        assert _entry_hash(mut) != base_hash, f"Mutating {field} didn't change hash"
