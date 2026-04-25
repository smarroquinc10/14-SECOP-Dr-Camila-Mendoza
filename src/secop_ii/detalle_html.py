"""Per-process HTML drill-down generator.

Builds a self-contained HTML file per row in ``detalles/<process_id>.html``
that mirrors EVERYTHING SECOP knows about the process: proceso, contratos,
adiciones, garantías, pagos, ejecución, suspensiones, portal cache, docs,
plus the SHA-256 evidence hash.

Design constraints:

* Self-contained (single file per process, no external CSS/JS) — works
  offline, can be emailed, can be printed as PDF.
* Institutional FGN palette: dark navy (#1A2B5F), Fiscalía red (#A50034),
  gold (#C9A227). No emojis, no whimsy — this is compliance evidence.
* Confidence badges per cell so the Dra. instantly sees what's solid
  vs what needs review.
* Data-attribute-tagged sections so a future Tauri/Next.js shell could
  parse it for navigation.

Generated files are written next to the source workbook:

    BASE DE DATOS FEAB CONTRATOS2.xlsx
    detalles/
      CO1.NTC.4156515.html
      CO1.NTC.5405127.html
      ...
"""
from __future__ import annotations

import html
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

# FGN institutional palette
NAVY = "#1A2B5F"
RED = "#A50034"
GOLD = "#C9A227"
GREY_BG = "#F4F5F7"
GREY_BORDER = "#D8DCE0"
GREY_TEXT = "#5A6470"
GREEN = "#2E7D32"
AMBER = "#F57C00"
ROSE = "#C62828"


@dataclass
class DetalleData:
    """All the inputs the HTML generator needs for one process."""
    process_id: str
    notice_uid: str | None
    source_url: str | None
    proceso: dict | None
    contratos: list[dict]
    adiciones_by_contrato: dict[str, list[dict]]
    garantias_by_contrato: dict[str, list[dict]]
    pagos_by_contrato: dict[str, list[dict]]
    ejecucion_by_contrato: dict[str, list[dict]]
    suspensiones_by_contrato: dict[str, list[dict]]
    mods_proceso: list[dict]
    docs: list[dict]
    portal_data: dict | None
    feab_fills: dict[str, Any]
    feab_confidences: dict[str, str]
    feab_sources: dict[str, str]
    feab_discrepancies: list[str]
    feab_revisar: list[str]
    feab_hash: str
    feab_obs: str | None  # the Dra.'s OBSERVACIONES note
    generated_at: str


def render_detalle(data: DetalleData) -> str:
    """Return the full HTML document as a string."""
    title = f"Dra Cami Contractual — {data.process_id}"
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(title)}</title>
<style>
{_CSS}
</style>
</head>
<body>
<header class="hdr">
  <div class="hdr-row">
    <div>
      <div class="hdr-eyebrow">Dra Cami Contractual · FEAB · Fiscalía General de la Nación</div>
      <h1>{html.escape(data.process_id)}</h1>
      <div class="hdr-sub">{html.escape(data.notice_uid or '—')}</div>
    </div>
    <div class="hdr-meta">
      <div><span class="lbl">Generado</span> {html.escape(data.generated_at)}</div>
      <div><span class="lbl">Hash SECOP</span>
        <code class="hash" title="SHA-256 del payload SECOP">{data.feab_hash[:16]}…</code>
      </div>
      <div><span class="lbl">Confianza</span> {_confidence_badge(_global_confidence(data.feab_confidences))}</div>
    </div>
  </div>
</header>

<main class="grid">
{_section_resumen(data)}
{_section_observaciones(data)}
{_section_discrepancias(data)}
{_section_proceso(data)}
{_section_contratos(data)}
{_section_modificatorios(data)}
{_section_garantias(data)}
{_section_pagos(data)}
{_section_ejecucion(data)}
{_section_suspensiones(data)}
{_section_documentos(data)}
{_section_portal(data)}
{_section_evidencia(data)}
</main>

<footer class="ftr">
  <div><strong>Dra Cami Contractual</strong> — espejo automático del SECOP II.
  La data mostrada es lo que SECOP devolvió en {html.escape(data.generated_at)}.
  Para validar la integridad: compare el hash SHA-256 con la celda del programa.</div>
</footer>
</body>
</html>"""


# ---- Sections ----------------------------------------------------------------


def _section_resumen(data: DetalleData) -> str:
    """Top-of-page key facts grid."""
    rows = []
    for col in [
        "2. NÚMERO DE CONTRATO",
        "4. OBJETO",
        "12. MODALIDAD DE SELECCIÓN",
        "13. CLASE DE CONTRATO",
        "10.ESTADO DEL CONTRATO",
        "43. CONTRATISTA : NOMBRE COMPLETO",
        "28.VALOR INICIAL DEL CONTRATO (INCLUIDAS VIGENCIA ACTUAL Y FUTURAS)",
        "36. VALOR TOTAL",
        "5. FECHA SUSCRIPCIÓN",
        "8. FECHA INICIO",
        "9. FECHA TERMINACIÓN",
        "67.REQUIERE LIQUIDACIÓN?",
    ]:
        v = data.feab_fills.get(col)
        if v in (None, "", "—"):
            continue
        conf = data.feab_confidences.get(col, "")
        src = data.feab_sources.get(col, "")
        rows.append(f"""
<div class="kv">
  <div class="k">{html.escape(_short(col))} {_confidence_badge(conf, mini=True)}</div>
  <div class="v">{html.escape(str(v))}</div>
  {f'<div class="src" title="{html.escape(src)}">{html.escape(src)}</div>' if src else ''}
</div>""")
    return f"""<section data-section="resumen" class="card">
<h2>Resumen del proceso</h2>
<div class="kv-grid">{''.join(rows) or '<div class="empty">Sin datos.</div>'}</div>
</section>"""


def _section_observaciones(data: DetalleData) -> str:
    """The Dra.'s manual note. Read-only, sits above SECOP data."""
    if not data.feab_obs:
        return ""
    return f"""<section data-section="observaciones" class="card highlight-amber">
<h2>Observación FEAB (manual de la Dra.)</h2>
<p class="quote">{html.escape(str(data.feab_obs))}</p>
<div class="caption">Esta nota es referencia humana, NO autoridad. La verdad viene de SECOP.</div>
</section>"""


def _section_discrepancias(data: DetalleData) -> str:
    """Conflicts: manual vs SECOP, or validation flags."""
    if not data.feab_discrepancies and not data.feab_revisar:
        return f"""<section data-section="discrepancias" class="card highlight-green">
<h2>Discrepancias detectadas</h2>
<p class="ok">Ninguna. Cada celda llenada coincide con SECOP y pasa todos los chequeos.</p>
</section>"""
    items = []
    for d in data.feab_discrepancies:
        items.append(f"<li>{html.escape(d)}</li>")
    revisar = ""
    if data.feab_revisar:
        revisar = f"""<div class="caption">
        <strong>Celdas marcadas para revisión humana:</strong>
        {html.escape(', '.join(data.feab_revisar))}</div>"""
    return f"""<section data-section="discrepancias" class="card highlight-rose">
<h2>Discrepancias detectadas</h2>
<ul class="issues">{''.join(items)}</ul>
{revisar}
</section>"""


def _section_proceso(data: DetalleData) -> str:
    proceso = data.proceso or {}
    if not proceso:
        return ""
    rows = _kv_table_from_dict(proceso)
    return f"""<section data-section="proceso" class="card">
<h2>Proceso (dataset p6dx-8zbt) — {len(proceso)} campos</h2>
{rows}
</section>"""


def _section_contratos(data: DetalleData) -> str:
    if not data.contratos:
        return f"""<section data-section="contratos" class="card">
<h2>Contratos (dataset jbjy-vk9h)</h2>
<div class="empty">No hay contratos adjudicados en SECOP para este proceso.</div>
</section>"""
    parts = []
    for i, c in enumerate(data.contratos, start=1):
        parts.append(f"""<details class="contract" {'open' if i == 1 else ''}>
<summary>{html.escape(c.get('referencia_del_contrato') or c.get('id_contrato') or '(sin id)')}
  — {html.escape(c.get('estado_contrato') or '—')}
  — ${_format_money(c.get('valor_del_contrato'))}</summary>
{_kv_table_from_dict(c)}
</details>""")
    return f"""<section data-section="contratos" class="card">
<h2>Contratos (dataset jbjy-vk9h) — {len(data.contratos)}</h2>
{''.join(parts)}
</section>"""


def _section_modificatorios(data: DetalleData) -> str:
    items = []
    for cid, adis in data.adiciones_by_contrato.items():
        if not adis:
            continue
        items.append(f"<h3>{html.escape(cid)} — {len(adis)} adiciones</h3>")
        items.append(_table_from_dicts(adis,
            cols=["valor", "tipo", "descripcion_adicion", "fecha_adicion"]))
    if not items:
        return ""
    return f"""<section data-section="modificatorios" class="card">
<h2>Adiciones / Modificatorios contractuales</h2>
{''.join(items)}
</section>"""


def _section_garantias(data: DetalleData) -> str:
    items = []
    for cid, gar in data.garantias_by_contrato.items():
        if not gar:
            continue
        items.append(f"<h3>{html.escape(cid)} — {len(gar)} pólizas</h3>")
        items.append(_table_from_dicts(gar,
            cols=["tipopoliza", "aseguradora", "numeropoliza",
                 "fechainiciopoliza", "fechafinpoliza", "valor", "estado"]))
    if not items:
        return ""
    return f"""<section data-section="garantias" class="card">
<h2>Garantías</h2>
{''.join(items)}
</section>"""


def _section_pagos(data: DetalleData) -> str:
    items = []
    for cid, fact in data.pagos_by_contrato.items():
        if not fact:
            continue
        items.append(f"<h3>{html.escape(cid)} — {len(fact)} facturas</h3>")
        items.append(_table_from_dicts(fact,
            cols=["fecha_factura", "numero_de_factura", "estado",
                 "valor_total", "valor_a_pagar", "pago_confirmado"]))
    if not items:
        return ""
    return f"""<section data-section="pagos" class="card">
<h2>Pagos / Facturas</h2>
{''.join(items)}
</section>"""


def _section_ejecucion(data: DetalleData) -> str:
    items = []
    for cid, ej in data.ejecucion_by_contrato.items():
        if not ej:
            continue
        items.append(f"<h3>{html.escape(cid)}</h3>")
        items.append(_table_from_dicts(ej,
            cols=["porcentaje_de_avance_real", "porcentajedeavanceesperado",
                 "fechadeentregareal", "fechadeentregaesperada"]))
    if not items:
        return ""
    return f"""<section data-section="ejecucion" class="card">
<h2>Ejecución contractual</h2>
{''.join(items)}
</section>"""


def _section_suspensiones(data: DetalleData) -> str:
    items = []
    for cid, sus in data.suspensiones_by_contrato.items():
        if not sus:
            continue
        items.append(f"<h3>{html.escape(cid)}</h3>")
        items.append(_table_from_dicts(sus,
            cols=["fecha_de_creacion", "tipo", "estado",
                 "proposito_de_la_modificacion"]))
    if not items:
        return ""
    return f"""<section data-section="suspensiones" class="card highlight-amber">
<h2>Suspensiones</h2>
{''.join(items)}
</section>"""


def _section_documentos(data: DetalleData) -> str:
    if not data.docs:
        return ""
    return f"""<section data-section="documentos" class="card">
<h2>Documentos publicados — {len(data.docs)}</h2>
{_table_from_dicts(data.docs,
    cols=["tipo", "nombre", "fecha_publicacion", "url"])}
</section>"""


def _section_portal(data: DetalleData) -> str:
    if not data.portal_data:
        return ""
    return f"""<section data-section="portal" class="card">
<h2>Portal SECOP (cache local) — {len(data.portal_data)} campos</h2>
{_kv_table_from_dict(data.portal_data)}
</section>"""


def _section_evidencia(data: DetalleData) -> str:
    """Audit panel: full SHA-256 hash + raw JSON dump for archive."""
    raw = {
        "notice_uid": data.notice_uid,
        "process_id": data.process_id,
        "proceso": data.proceso,
        "contratos": data.contratos,
    }
    raw_json = html.escape(json.dumps(raw, ensure_ascii=False, indent=2,
                                      default=str))
    return f"""<section data-section="evidencia" class="card highlight-grey">
<h2>Evidencia para auditoría</h2>
<div class="kv">
  <div class="k">SHA-256 del payload SECOP</div>
  <div class="v"><code class="hash-full">{data.feab_hash}</code></div>
</div>
<details>
  <summary>Ver payload SECOP raw (JSON)</summary>
  <pre class="json">{raw_json}</pre>
</details>
</section>"""


# ---- Renderers ---------------------------------------------------------------


def _kv_table_from_dict(d: dict) -> str:
    """A 2-column table for a single dict's key/value pairs."""
    if not d:
        return '<div class="empty">Sin campos.</div>'
    rows = []
    for k in sorted(d.keys()):
        v = d[k]
        if isinstance(v, dict):
            v = v.get("url") or json.dumps(v, ensure_ascii=False)
        if v in (None, "", "No definido", "No Definido"):
            continue
        v_str = html.escape(str(v))
        if str(v).startswith("http"):
            v_str = f'<a href="{html.escape(str(v))}" target="_blank">{v_str}</a>'
        rows.append(f'<tr><th>{html.escape(k)}</th><td>{v_str}</td></tr>')
    if not rows:
        return '<div class="empty">Todos los campos están vacíos.</div>'
    return f'<table class="kv-table"><tbody>{"".join(rows)}</tbody></table>'


def _table_from_dicts(rows: list[dict], *, cols: list[str]) -> str:
    """A traditional table with the given columns from a list of dicts."""
    if not rows:
        return '<div class="empty">Sin filas.</div>'
    head = "".join(f"<th>{html.escape(c)}</th>" for c in cols)
    body_rows = []
    for r in rows:
        cells = []
        for c in cols:
            v = r.get(c, "")
            if isinstance(v, dict):
                v = v.get("url") or json.dumps(v)
            v_str = html.escape(str(v)) if v not in (None, "") else "—"
            if str(v).startswith("http"):
                v_str = f'<a href="{html.escape(str(v))}" target="_blank">link</a>'
            cells.append(f"<td>{v_str}</td>")
        body_rows.append("<tr>" + "".join(cells) + "</tr>")
    return f"""<table class="data-table">
<thead><tr>{head}</tr></thead>
<tbody>{''.join(body_rows)}</tbody>
</table>"""


def _confidence_badge(conf: str, *, mini: bool = False) -> str:
    if not conf:
        return ""
    cls = {
        "HIGH": "conf-high",
        "MEDIUM": "conf-med",
        "LOW": "conf-low",
    }.get(conf, "conf-unk")
    cls += " mini" if mini else ""
    label = {"HIGH": "✓", "MEDIUM": "·", "LOW": "!"}.get(conf, "?") if mini else conf
    return f'<span class="badge {cls}">{label}</span>'


def _global_confidence(confidences: dict[str, str]) -> str:
    if not confidences:
        return ""
    vals = list(confidences.values())
    if all(v == "HIGH" for v in vals):
        return "HIGH"
    if vals.count("HIGH") / len(vals) >= 0.7:
        return "HIGH"
    if "LOW" in vals:
        return "LOW"
    return "MEDIUM"


def _short(col: str) -> str:
    """Strip the leading number prefix from a column for display."""
    import re
    return re.sub(r"^\d+[A-Z]?\.\s*", "", col)


def _format_money(value: Any) -> str:
    if value in (None, ""):
        return "—"
    try:
        n = float(str(value).replace(",", "").replace("$", ""))
        return f"{int(n):,}".replace(",", ".")
    except (ValueError, TypeError):
        return str(value)


# ---- Static CSS --------------------------------------------------------------


_CSS = f"""
:root {{
  --navy: {NAVY};
  --red: {RED};
  --gold: {GOLD};
  --bg: {GREY_BG};
  --bd: {GREY_BORDER};
  --tx: {GREY_TEXT};
  --green: {GREEN};
  --amber: {AMBER};
  --rose: {ROSE};
}}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; background: var(--bg);
  color: #1a1a1a;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
    "Helvetica Neue", Arial, sans-serif;
  font-size: 14px; line-height: 1.5; }}
.hdr {{ background: var(--navy); color: white; padding: 24px 40px;
  border-bottom: 3px solid var(--gold); }}
.hdr-row {{ display: flex; justify-content: space-between; align-items: flex-start;
  max-width: 1400px; margin: 0 auto; }}
.hdr-eyebrow {{ font-size: 11px; letter-spacing: 0.1em; text-transform: uppercase;
  color: rgba(255,255,255,0.7); margin-bottom: 4px; }}
.hdr h1 {{ margin: 0; font-size: 28px; font-weight: 600; letter-spacing: -0.01em; }}
.hdr-sub {{ color: rgba(255,255,255,0.7); font-size: 13px;
  font-family: "SF Mono", Menlo, Consolas, monospace; margin-top: 4px; }}
.hdr-meta {{ font-size: 12px; color: rgba(255,255,255,0.85); text-align: right; }}
.hdr-meta div {{ margin: 2px 0; }}
.hdr-meta .lbl {{ display: inline-block; min-width: 80px;
  color: rgba(255,255,255,0.6); }}
.hdr-meta .hash {{ background: rgba(255,255,255,0.1); padding: 2px 6px;
  border-radius: 3px; }}
main.grid {{ max-width: 1400px; margin: 24px auto; padding: 0 40px;
  display: grid; gap: 16px; grid-template-columns: 1fr 1fr; }}
.card {{ background: white; border: 1px solid var(--bd);
  border-radius: 6px; padding: 20px 24px;
  break-inside: avoid; }}
.card.highlight-amber {{ border-left: 4px solid var(--amber); }}
.card.highlight-rose {{ border-left: 4px solid var(--rose); }}
.card.highlight-green {{ border-left: 4px solid var(--green); }}
.card.highlight-grey {{ background: #FAFAFB; }}
section[data-section="resumen"],
section[data-section="contratos"],
section[data-section="proceso"],
section[data-section="evidencia"] {{ grid-column: 1 / -1; }}
.card h2 {{ margin: 0 0 16px; font-size: 16px; font-weight: 600;
  color: var(--navy); padding-bottom: 8px; border-bottom: 1px solid var(--bd); }}
.card h3 {{ margin: 16px 0 8px; font-size: 13px; font-weight: 600;
  color: var(--navy); font-family: "SF Mono", Menlo, Consolas, monospace; }}
.kv-grid {{ display: grid; gap: 12px;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); }}
.kv {{ padding: 8px 0; border-bottom: 1px dashed var(--bd); }}
.kv .k {{ font-size: 11px; color: var(--tx); text-transform: uppercase;
  letter-spacing: 0.04em; margin-bottom: 4px; }}
.kv .v {{ font-size: 14px; font-weight: 500; color: #1a1a1a;
  word-break: break-word; }}
.kv .src {{ font-size: 10px; color: var(--tx); margin-top: 2px;
  font-family: "SF Mono", Menlo, Consolas, monospace; }}
.kv-table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
.kv-table th {{ text-align: left; padding: 6px 12px 6px 0; vertical-align: top;
  color: var(--tx); font-weight: 500; width: 40%;
  border-bottom: 1px solid var(--bd); }}
.kv-table td {{ padding: 6px 0; vertical-align: top;
  border-bottom: 1px solid var(--bd); word-break: break-word; }}
.data-table {{ width: 100%; border-collapse: collapse; font-size: 12px;
  margin: 8px 0; }}
.data-table th {{ background: #FAFAFB; text-align: left; padding: 8px;
  font-weight: 600; color: var(--navy);
  border-bottom: 2px solid var(--bd); }}
.data-table td {{ padding: 8px; border-bottom: 1px solid var(--bd);
  vertical-align: top; }}
.data-table tr:hover {{ background: #FAFAFB; }}
.empty {{ color: var(--tx); font-style: italic; padding: 8px 0; }}
.quote {{ background: #FFF8E1; border-left: 3px solid var(--gold);
  padding: 12px 16px; margin: 0; font-style: italic; }}
.caption {{ font-size: 11px; color: var(--tx); margin-top: 8px;
  text-transform: uppercase; letter-spacing: 0.04em; }}
.issues {{ list-style: none; padding: 0; margin: 0; }}
.issues li {{ padding: 6px 0; border-bottom: 1px solid var(--bd);
  font-family: "SF Mono", Menlo, Consolas, monospace; font-size: 12px; }}
.ok {{ color: var(--green); margin: 0; font-weight: 500; }}
.badge {{ display: inline-block; padding: 2px 8px; border-radius: 3px;
  font-size: 11px; font-weight: 600; letter-spacing: 0.04em; }}
.badge.mini {{ padding: 1px 5px; font-size: 9px; }}
.conf-high {{ background: #E8F5E9; color: var(--green); }}
.conf-med {{ background: #FFF8E1; color: var(--amber); }}
.conf-low {{ background: #FFEBEE; color: var(--rose); }}
.conf-unk {{ background: #ECEFF1; color: var(--tx); }}
details.contract {{ margin: 8px 0; padding: 8px 12px; background: #FAFAFB;
  border: 1px solid var(--bd); border-radius: 4px; }}
details.contract summary {{ cursor: pointer; font-weight: 500;
  font-family: "SF Mono", Menlo, Consolas, monospace; font-size: 13px; }}
details.contract[open] summary {{ margin-bottom: 12px; }}
.hash-full {{ font-family: "SF Mono", Menlo, Consolas, monospace;
  font-size: 11px; color: var(--tx); word-break: break-all; }}
pre.json {{ background: #1A1A1A; color: #E8E8E8; padding: 16px;
  border-radius: 4px; overflow-x: auto; font-size: 11px;
  font-family: "SF Mono", Menlo, Consolas, monospace;
  max-height: 400px; }}
a {{ color: var(--navy); }}
.ftr {{ max-width: 1400px; margin: 32px auto; padding: 0 40px 40px;
  font-size: 11px; color: var(--tx); border-top: 1px solid var(--bd);
  padding-top: 16px; }}
@media (max-width: 800px) {{
  main.grid {{ grid-template-columns: 1fr; padding: 0 16px; }}
  .hdr {{ padding: 16px; }}
  .hdr-row {{ flex-direction: column; gap: 12px; }}
  .hdr-meta {{ text-align: left; }}
}}
@media print {{
  .hdr {{ background: white; color: var(--navy);
    border-bottom: 3px solid var(--gold); }}
  .hdr-eyebrow, .hdr-sub, .hdr-meta {{ color: var(--tx); }}
  .card {{ box-shadow: none; page-break-inside: avoid; }}
  details.contract, details {{ page-break-inside: avoid; }}
  details {{ max-height: none !important; }}
  pre.json {{ max-height: none; background: white; color: #333;
    border: 1px solid var(--bd); }}
}}
"""


def write_detalle(data: DetalleData, output_dir: Path) -> Path:
    """Render the HTML and write it to ``output_dir/<process_id>.html``.

    Returns the path of the written file. Creates the directory if missing.
    Safe to call concurrently for different process_ids.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_name = data.process_id.replace("/", "_").replace("\\", "_")
    out = output_dir / f"{safe_name}.html"
    out.write_text(render_detalle(data), encoding="utf-8")
    return out


__all__ = ["DetalleData", "render_detalle", "write_detalle"]
