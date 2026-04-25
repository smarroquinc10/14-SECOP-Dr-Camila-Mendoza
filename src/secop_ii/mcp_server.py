"""MCP server local para Dra Cami Contractual.

Expone el watch list, los snapshots del portal SECOP, el scraper y el
audit-log como tools de Model Context Protocol (MCP). Cuando este server
está corriendo y conectado a Claude Desktop / Claude Code, la Dra (o
cualquier sesión de Claude) puede preguntar:

    "¿Cuántos contratos del FEAB 2024 están sin firmar?"
    "Leé del portal SECOP el proceso CO1.NTC.5405127."
    "Mostrame las últimas 20 entradas del audit log."
    "¿Qué procesos del watch list no tienen notice_uid?"

…sin tener que abrir el browser ni el código. Es la forma natural de
"actualizarse rápido" — Claude consulta los datos vivos del FEAB.

Filosofía cardinal:
- ESPEJO: las tools devuelven exactamente lo que está en el cache /
  watch list / audit log. NUNCA inventan campos.
- HONESTO: si un proceso no tiene snapshot, decimos `available: False`
  y ofrecemos el tool `scrape_notice` para leerlo.
- INMUTABLE: el audit log se LEE, nunca se escribe desde aquí.

Cómo usarlo:

    # Instalar dependencia (primera vez)
    pip install "mcp[cli]>=1.0"

    # Lanzar server (stdio transport — para Claude Desktop / Code)
    python -m secop_ii.mcp_server

    # O agregarlo a ~/.claude/mcp.json:
    {
      "mcpServers": {
        "dra-cami": {
          "command": "python",
          "args": ["-m", "secop_ii.mcp_server"],
          "cwd": "C:/Users/FGN/01 Claude Repositorio/14 SECOP Dr Camila Mendoza"
        }
      }
    }

Nota: ``mcp`` es la lib oficial. Si no está instalada, ``main()`` imprime
el comando de instalación y sale con código 2.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent

WATCH_PATH = ROOT / ".cache" / "watched_urls.json"
PORTAL_CACHE_PATH = ROOT / ".cache" / "portal_opportunity.json"
AUDIT_LOG_PATH = ROOT / ".cache" / "audit_log.jsonl"


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _build_server():  # type: ignore[no-untyped-def]
    """Construye y devuelve la instancia FastMCP. Aislado para que el
    import de ``mcp`` ocurra sólo cuando realmente lanzamos el server.
    """
    try:
        from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]
    except ImportError as exc:
        raise SystemExit(
            "El package 'mcp' no está instalado. Corré:\n"
            "    pip install \"mcp[cli]>=1.0\"\n"
            f"Detalle: {exc}"
        ) from exc

    mcp = FastMCP("dra-cami-contractual")

    # ------------------------------------------------------------------
    # Watch list — tracked SECOP processes (the Dra's 491 from Excel)
    # ------------------------------------------------------------------
    @mcp.tool()
    def list_watched(
        sheet: str | None = None,
        vigencia: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Lista procesos del watch list (los que la Dra sigue).

        Args:
            sheet: filtra por hoja del Excel (FEAB 2024, FEAB 2025, …).
            vigencia: filtra por vigencia ("2024", "2025", …).
            limit: máximo a devolver (default 100, max razonable 500).

        Devuelve campos persistidos: url, process_id, notice_uid, sheets,
        vigencias, appearances, added_at, note. NUNCA derivamos
        estado/valor/proveedor del Excel — eso vive en SECOP.
        """
        items = _load_json(WATCH_PATH, [])
        if not isinstance(items, list):
            return []
        out = []
        for it in items:
            if sheet and sheet not in (it.get("sheets") or []):
                continue
            if vigencia and vigencia not in (it.get("vigencias") or []):
                continue
            out.append(
                {
                    "url": it.get("url"),
                    "process_id": it.get("process_id"),
                    "notice_uid": it.get("notice_uid"),
                    "sheets": it.get("sheets") or [],
                    "vigencias": it.get("vigencias") or [],
                    "appearances": len(it.get("appearances") or []),
                    "added_at": it.get("added_at"),
                    "note": it.get("note"),
                }
            )
            if len(out) >= max(1, min(limit, 500)):
                break
        return out

    @mcp.tool()
    def watch_summary() -> dict[str, Any]:
        """Resumen de la lista: total, por hoja, por vigencia, sin notice_uid."""
        items = _load_json(WATCH_PATH, [])
        if not isinstance(items, list):
            return {"total": 0, "by_sheet": {}, "by_vigencia": {}, "without_notice_uid": 0}
        by_sheet: dict[str, int] = {}
        by_vig: dict[str, int] = {}
        without_uid = 0
        for it in items:
            for s in it.get("sheets") or []:
                by_sheet[s] = by_sheet.get(s, 0) + 1
            for v in it.get("vigencias") or []:
                by_vig[v] = by_vig.get(v, 0) + 1
            if not it.get("notice_uid"):
                without_uid += 1
        return {
            "total": len(items),
            "by_sheet": dict(sorted(by_sheet.items())),
            "by_vigencia": dict(sorted(by_vig.items())),
            "without_notice_uid": without_uid,
        }

    # ------------------------------------------------------------------
    # Portal snapshots — espejo del HTML del portal SECOP
    # ------------------------------------------------------------------
    @mcp.tool()
    def get_portal_snapshot(notice_uid: str) -> dict[str, Any]:
        """Snapshot del portal SECOP para ``notice_uid`` (CO1.NTC.X).

        Devuelve TODOS los labels capturados (cada link tiene campos
        distintos). Si todavía no fue scrapeado, ``available: false`` —
        en ese caso usá ``scrape_notice`` para iniciarlo.
        """
        cache = _load_json(PORTAL_CACHE_PATH, {})
        if not isinstance(cache, dict) or notice_uid not in cache:
            return {"available": False, "notice_uid": notice_uid}
        raw = cache[notice_uid]
        return {
            "available": True,
            "notice_uid": notice_uid,
            "fields": raw.get("fields", {}),
            "all_labels": raw.get("all_labels", {}),
            "documents": raw.get("documents", []),
            "notificaciones": raw.get("notificaciones", []),
            "status": raw.get("status"),
            "missing_fields": raw.get("missing_fields", []),
            "scraped_at": raw.get("scraped_at"),
            "raw_length": raw.get("raw_length"),
        }

    @mcp.tool()
    def list_portal_snapshots(limit: int = 50) -> list[dict[str, Any]]:
        """Lista los notice_uid que tienen snapshot del portal cacheado.

        Útil para ver de un vistazo qué ya fue scrapeado y con qué status.
        """
        cache = _load_json(PORTAL_CACHE_PATH, {})
        if not isinstance(cache, dict):
            return []
        out = []
        for uid, raw in cache.items():
            out.append(
                {
                    "notice_uid": uid,
                    "status": raw.get("status"),
                    "scraped_at": raw.get("scraped_at"),
                    "field_count": len(raw.get("all_labels") or {}),
                    "doc_count": len(raw.get("documents") or []),
                    "missing_fields": raw.get("missing_fields") or [],
                }
            )
            if len(out) >= max(1, min(limit, 500)):
                break
        return out

    @mcp.tool()
    def scrape_notice(
        notice_uid: str | None = None,
        force: bool = False,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Lanza el scraper del portal SECOP en segundo plano.

        Args:
            notice_uid: si está, scrapea sólo ese (CO1.NTC.X).
            force: re-scrapea aunque haya cache OK.
            limit: tope de procesos cuando no se pasa notice_uid.

        Returns: PID del subproceso. Para ver progreso usá la app web
        (barra de progreso del portal) o leé ``.cache/portal_progress.jsonl``.
        """
        cmd = [sys.executable, "scripts/scrape_portal.py"]
        if notice_uid:
            cmd += ["--uid", notice_uid]
        if force:
            cmd.append("--force")
        if limit is not None:
            cmd += ["--limit", str(int(limit))]
        proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return {"started": True, "pid": proc.pid, "cmd": " ".join(cmd)}

    # ------------------------------------------------------------------
    # Audit log — chain of custody (read-only)
    # ------------------------------------------------------------------
    @mcp.tool()
    def audit_log_tail(limit: int = 20) -> list[dict[str, Any]]:
        """Últimas N entradas del audit log (hash-chain inmutable).

        El audit log registra cada replace/fill/verify con SHA-256 del
        payload SECOP, code_version (git short SHA) y prev_hash. Si la
        chain se rompió, una entrada tiene prev_hash incorrecto — la UI
        muestra "alerta" en el chip del header.
        """
        if not AUDIT_LOG_PATH.exists():
            return []
        try:
            lines = AUDIT_LOG_PATH.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        tail = lines[-max(1, min(limit, 500)) :]
        out = []
        for line in tail:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
        return out

    # ------------------------------------------------------------------
    # Resources — readonly bulk dumps for context window
    # ------------------------------------------------------------------
    @mcp.resource("watch://summary")
    def res_watch_summary() -> str:
        """Resumen del watch list como texto plano (para context window)."""
        s = watch_summary()
        lines = [
            "Watch list — Dra Cami Contractual (FEAB / Fiscalía)",
            f"Total: {s['total']}  ·  Sin notice_uid: {s['without_notice_uid']}",
            "Por hoja:",
        ]
        for sheet, n in s["by_sheet"].items():
            lines.append(f"  {sheet}: {n}")
        lines.append("Por vigencia:")
        for v, n in s["by_vigencia"].items():
            lines.append(f"  {v}: {n}")
        return "\n".join(lines)

    @mcp.resource("portal://summary")
    def res_portal_summary() -> str:
        """Resumen de los snapshots del portal (cuántos OK, parciales, etc.)."""
        cache = _load_json(PORTAL_CACHE_PATH, {})
        if not isinstance(cache, dict):
            return "(cache vacío)"
        by_status: dict[str, int] = {}
        for raw in cache.values():
            st = raw.get("status") or "(sin status)"
            by_status[st] = by_status.get(st, 0) + 1
        lines = [f"Portal snapshots: {len(cache)} total"]
        for st, n in sorted(by_status.items()):
            lines.append(f"  {st}: {n}")
        return "\n".join(lines)

    return mcp


def main() -> None:
    """Entry point — lanza el server con stdio transport."""
    server = _build_server()
    server.run()


if __name__ == "__main__":
    main()
