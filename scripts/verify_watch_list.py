"""Verify every URL in `.cache/watched_urls.json` against SECOP.

For each watched item:

* Re-parse the URL → process_id (already done at import time, but we
  re-validate so an upstream parser change is caught).
* Try `resolve_notice_uid` to get the canonical CO1.NTC.* uid.
* Try `get_proceso` and grab the descripción/objeto for human eyeball.
* Cross-check against the contracts dataset by `proceso_de_compra`
  for PCCNTR (contract-level) URLs.

Persists the resolved `notice_uid` back into the watch list so the
UI shows it in the table without re-resolving on click.

Writes a JSONL report to `.cache/watch_verify_<timestamp>.jsonl`
with one line per URL: `{pid, sheet, status, notice_uid, objeto,
error}`.

Usage::

    ./.venv/Scripts/python.exe scripts/verify_watch_list.py
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from secop_ii.paths import state_dir, state_path  # noqa: E402
from secop_ii.secop_client import SecopClient  # noqa: E402
from secop_ii.url_parser import InvalidSecopUrlError, parse_secop_url  # noqa: E402


def main() -> int:
    watch_path = state_path("watched_urls.json")
    if not watch_path.exists():
        print(f"FATAL: {watch_path} not found")
        return 2

    items = json.loads(watch_path.read_text(encoding="utf-8"))
    total = len(items)
    print(f"Verifying {total} watched URLs against SECOP...")
    print()

    client = SecopClient()
    out_dir = state_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    report_path = out_dir / f"watch_verify_{stamp}.jsonl"

    counts = {
        "ok_with_notice": 0,
        "ok_no_notice": 0,
        "found_in_contracts": 0,
        "draft_request": 0,
        "parse_error": 0,
        "secop_error": 0,
        "not_found": 0,
    }

    # Force unbuffered stdout so the user sees live progress when
    # this script is run in background and stdout is captured to a file.
    sys.stdout.reconfigure(line_buffering=True)

    started = time.monotonic()
    with report_path.open("w", encoding="utf-8") as fh:
        for i, it in enumerate(items, start=1):
            pid = it.get("process_id")
            url = it.get("url", "")
            note = (it.get("note") or "").replace(
                "Importado de Excel · hoja ", ""
            ).replace("Importado de Excel - hoja ", "")
            row = {"index": i, "pid": pid, "url": url, "sheet": note,
                  "status": None, "notice_uid": None, "objeto": None,
                  "id_contrato": None, "error": None}

            # Re-parse defensively
            if not pid:
                try:
                    ref = parse_secop_url(url)
                    pid = ref.process_id
                    row["pid"] = pid
                except InvalidSecopUrlError as exc:
                    row["status"] = "parse_error"
                    row["error"] = str(exc)
                    counts["parse_error"] += 1
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                    continue

            # Fast path: CO1.REQ.* and CO1.BDOS.* are PRE-publication
            # workspace IDs from /CO1BusinessLine — they don't have a
            # notice_uid yet because the process is still being prepared.
            # The Dra still tracks them so we don't drop them; we just
            # label them "draft_request" and skip the SECOP queries.
            if pid.startswith("CO1.REQ.") or pid.startswith("CO1.BDOS."):
                row["status"] = "draft_request"
                row["objeto"] = (
                    "Proceso en preparación / borrador interno (sin "
                    "notice_uid publicado todavía)"
                )
                counts["draft_request"] += 1
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                fh.flush()
                if i % 10 == 0 or i == total:
                    elapsed = time.monotonic() - started
                    rate = i / max(elapsed, 0.001)
                    eta = (total - i) / max(rate, 0.001)
                    print(
                        f"  {i:>4}/{total} · {elapsed:.0f}s · "
                        f"{rate:.1f}/s · ETA {eta:.0f}s · "
                        f"{counts['ok_with_notice']} con notice, "
                        f"{counts['found_in_contracts']} en contratos, "
                        f"{counts['draft_request']} drafts, "
                        f"{counts['not_found']} no encontradas, "
                        f"{counts['secop_error']} errores"
                    )
                continue

            try:
                ntc = client.resolve_notice_uid(pid, url=url)
            except Exception as exc:
                row["status"] = "secop_error"
                row["error"] = str(exc)[:200]
                counts["secop_error"] += 1
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                continue

            row["notice_uid"] = ntc

            if ntc:
                # Try to fetch the proceso for the objeto
                try:
                    proceso = client.get_proceso(pid, url=url)
                    if proceso:
                        objeto = (
                            proceso.get("descripci_n_del_procedimiento")
                            or proceso.get("objeto_del_contrato")
                            or proceso.get("objeto_a_contratar")
                        )
                        row["objeto"] = (str(objeto)[:160] if objeto else None)
                        row["status"] = "ok_with_notice"
                        counts["ok_with_notice"] += 1
                    else:
                        row["status"] = "ok_no_notice"
                        counts["ok_no_notice"] += 1
                except Exception as exc:
                    row["status"] = "ok_no_notice"
                    row["error"] = f"proceso fetch: {exc}"[:200]
                    counts["ok_no_notice"] += 1
            else:
                # Maybe it's a PCCNTR — try the contracts dataset by
                # proceso_de_compra or id_contrato
                try:
                    if pid.startswith("CO1.PCCNTR."):
                        rows = client.query(
                            "jbjy-vk9h",
                            where=f"id_contrato='{pid}'",
                            limit=1,
                        )
                    else:
                        rows = client.query(
                            "jbjy-vk9h",
                            where=f"proceso_de_compra='{pid}'",
                            limit=1,
                        )
                    if rows:
                        c = rows[0]
                        row["status"] = "found_in_contracts"
                        row["id_contrato"] = c.get("id_contrato")
                        row["objeto"] = (str(c.get("objeto_del_contrato"))[:160]
                                       if c.get("objeto_del_contrato") else None)
                        counts["found_in_contracts"] += 1
                    else:
                        row["status"] = "not_found"
                        counts["not_found"] += 1
                except Exception as exc:
                    row["status"] = "secop_error"
                    row["error"] = f"contracts fallback: {exc}"[:200]
                    counts["secop_error"] += 1

            # Persist resolved notice_uid back into the watch item so the
            # UI shows it without re-resolving.
            if ntc and not it.get("notice_uid"):
                it["notice_uid"] = ntc

            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()

            # Progress every 10
            if i % 10 == 0 or i == total:
                elapsed = time.monotonic() - started
                rate = i / max(elapsed, 0.001)
                eta = (total - i) / max(rate, 0.001)
                print(
                    f"  {i:>4}/{total} · {elapsed:.0f}s · "
                    f"{rate:.1f}/s · ETA {eta:.0f}s · "
                    f"{counts['ok_with_notice']} con notice, "
                    f"{counts['found_in_contracts']} en contratos, "
                    f"{counts['draft_request']} drafts, "
                    f"{counts['not_found']} no encontradas, "
                    f"{counts['secop_error']} errores"
                )

    # Persist the now-enriched watch list
    watch_path.write_text(
        json.dumps(items, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print()
    print("=" * 60)
    print("RESUMEN FINAL")
    print("=" * 60)
    for k, v in counts.items():
        print(f"  {k:>22}: {v}")
    total_ok = (counts["ok_with_notice"] + counts["ok_no_notice"]
               + counts["found_in_contracts"])
    total_bad = counts["not_found"] + counts["parse_error"] + counts["secop_error"]
    print(f"  {'TOTAL OK':>22}: {total_ok} / {total} "
          f"({100*total_ok/total:.1f}%)")
    print(f"  {'TOTAL FAIL':>22}: {total_bad}")
    print()
    print(f"Detailed JSONL report: {report_path}")
    print(f"Watch list updated with notice_uid where resolved: {watch_path}")
    return 0 if total_bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
