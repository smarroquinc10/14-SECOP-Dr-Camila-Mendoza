"""Streamlit CRM view for SECOP II processes.

Flow:

1. The person uploads their ``.xlsx`` (or a saved path is re-used).
2. The app shows the current contents in a filterable table.
3. Clicking "Actualizar desde SECOP II" streams progress in real time and
   writes the updated values back to the same file (with timestamped
   backup). A run report is shown at the end.
4. Optional App Token for datos.gov.co is stored in
   ``%APPDATA%\\SecopII\\config.json``.

The module is designed to also work when launched as the Streamlit entry
point of a PyInstaller-built ``.exe`` (see :mod:`secop_ii.launcher`).
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from secop_ii.excel_io import load_workbook, preview_as_dicts
from secop_ii.extractors.modificatorios import COL_CANTIDAD, COL_TIENE, COL_TIPOS
from secop_ii.orchestrator import LAST_UPDATE_COLUMN, STATUS_COLUMN, process_workbook

APP_TITLE = "CRM SECOP II — Seguimiento de procesos"
APP_ICON = ":mag:"


def _config_dir() -> Path:
    base = os.environ.get("APPDATA") or os.environ.get("HOME") or tempfile.gettempdir()
    path = Path(base) / "SecopII"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _load_config() -> dict:
    cfg_path = _config_dir() / "config.json"
    if cfg_path.is_file():
        try:
            return json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_config(cfg: dict) -> None:
    cfg_path = _config_dir() / "config.json"
    cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def _open_file_in_explorer(path: Path) -> None:
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            os.system(f'open "{path}"')
        else:
            os.system(f'xdg-open "{path}"')
    except Exception:
        pass


def _persist_upload(uploaded_file, dest_dir: Path) -> Path:
    """Save a Streamlit uploaded file to disk and return the path."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / uploaded_file.name
    dest.write_bytes(uploaded_file.getbuffer())
    return dest


def _render_sidebar(cfg: dict) -> dict:
    with st.sidebar:
        st.header("Configuración")
        token = st.text_input(
            "App Token de datos.gov.co (opcional)",
            value=cfg.get("app_token", ""),
            type="password",
            help=(
                "Obtén uno gratis en datos.gov.co → Perfil → Developer Settings. "
                "Sin token SECOP limita rápido las consultas."
            ),
        )
        rate = st.number_input(
            "Consultas por segundo",
            min_value=1.0,
            max_value=10.0,
            value=float(cfg.get("rate", 2.0)),
            step=0.5,
        )
        url_column = st.text_input(
            "Nombre de la columna con la URL (opcional, autodetecta)",
            value=cfg.get("url_column", ""),
        )
        if st.button("Guardar configuración"):
            _save_config({
                "app_token": token,
                "rate": rate,
                "url_column": url_column,
            })
            st.success("Configuración guardada.")
        st.divider()
        st.caption(
            "Esta app consulta la API pública de datos abiertos "
            "(datos.gov.co → SECOP II). No usa tu usuario del portal."
        )
    return {
        "app_token": token.strip() or None,
        "rate": rate,
        "url_column": url_column.strip() or None,
    }


def _load_preview(path: Path) -> pd.DataFrame:
    wb, ws = load_workbook(path)
    rows = preview_as_dicts(ws)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    if "__row__" in df.columns:
        df = df.drop(columns=["__row__"])
    return df


def _apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    with st.expander("Filtros", expanded=False):
        search = st.text_input("Buscar (texto en cualquier columna)", "")
        mod_filter = st.selectbox(
            "Filtro por modificatorio",
            ["Todos", "Solo con modificatorio (Sí)", "Solo sin modificatorio (No)"],
        )

    filtered = df
    if search:
        mask = filtered.apply(
            lambda row: row.astype(str).str.contains(search, case=False, na=False).any(),
            axis=1,
        )
        filtered = filtered[mask]

    if COL_TIENE in filtered.columns:
        if mod_filter == "Solo con modificatorio (Sí)":
            filtered = filtered[filtered[COL_TIENE] == "Sí"]
        elif mod_filter == "Solo sin modificatorio (No)":
            filtered = filtered[filtered[COL_TIENE] == "No"]
    return filtered


def _render_detail(df: pd.DataFrame) -> None:
    if df.empty:
        return
    with st.expander("Ver detalle de un proceso", expanded=False):
        labels = []
        for i, row in df.reset_index(drop=True).iterrows():
            # Prefer a readable label — first non-empty textual column.
            label_parts = []
            for col in df.columns[:4]:
                val = row.get(col)
                if val is not None and str(val).strip():
                    label_parts.append(str(val)[:40])
                if len(label_parts) >= 2:
                    break
            labels.append(f"{i + 1}. " + " — ".join(label_parts))
        choice = st.selectbox("Proceso", options=range(len(labels)), format_func=lambda i: labels[i])
        row = df.reset_index(drop=True).iloc[choice]
        st.write({col: _to_display(row[col]) for col in df.columns})


def _to_display(value):
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    return value


def _run_update(path: Path, settings: dict) -> None:
    placeholder_summary = st.empty()
    placeholder_progress = st.empty()
    log_area = st.empty()
    log_lines: list[str] = []

    progress_bar = placeholder_progress.progress(0.0, text="Iniciando…")

    def on_progress(done: int, total: int, row) -> None:
        pct = done / max(total, 1)
        progress_bar.progress(
            min(pct, 1.0),
            text=f"{done} de {total} — procesando fila {row.row}",
        )
        mark = "✅" if row.ok else "⚠️"
        detail = f"{row.process_id or row.url[:50]} → {row.status}"
        log_lines.append(f"{mark} fila {row.row}: {detail}")
        log_area.code("\n".join(log_lines[-25:]))

    try:
        report = process_workbook(
            path,
            url_column=settings.get("url_column"),
            app_token=settings.get("app_token"),
            rate_per_second=settings.get("rate"),
            do_backup=True,
            progress=on_progress,
        )
    except Exception as exc:
        placeholder_progress.empty()
        st.error(f"Error durante la actualización: {exc}")
        return

    progress_bar.progress(1.0, text="Completado.")
    st.session_state["last_report"] = report.as_dict()
    st.session_state["last_backup"] = str(report.backup_path) if report.backup_path else None

    with placeholder_summary.container():
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total", report.total)
        c2.metric("Con modificatorio", report.with_modificatorio)
        c3.metric("Sin modificatorio", report.without_modificatorio)
        c4.metric("Errores", report.errors)
    st.success(
        f"Excel actualizado ({path.name}). "
        f"Backup: {report.backup_path.name if report.backup_path else 'no creado'}."
    )


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, page_icon=APP_ICON, layout="wide")
    st.title(APP_TITLE)

    cfg = _load_config()
    settings = _render_sidebar(cfg)

    st.subheader("1. Tu Excel de procesos")
    uploaded = st.file_uploader(
        "Selecciona tu archivo .xlsx",
        type=["xlsx"],
        accept_multiple_files=False,
    )
    existing_path = cfg.get("last_file")
    col_a, col_b = st.columns([3, 1])

    current_path: Path | None = None
    if uploaded is not None:
        work_dir = _config_dir() / "workbooks"
        current_path = _persist_upload(uploaded, work_dir)
        cfg["last_file"] = str(current_path)
        _save_config(cfg)
    elif existing_path and Path(existing_path).is_file():
        current_path = Path(existing_path)
        col_a.info(f"Último archivo usado: `{existing_path}`")
        if col_b.button("Olvidar"):
            cfg.pop("last_file", None)
            _save_config(cfg)
            st.rerun()

    if current_path is None:
        st.info("Sube tu archivo .xlsx para empezar.")
        return

    st.subheader("2. Vista previa")
    try:
        df = _load_preview(current_path)
    except Exception as exc:
        st.error(f"No pude leer el Excel: {exc}")
        return

    if df.empty:
        st.warning("El Excel está vacío o no tiene datos en la hoja activa.")
        return

    filtered = _apply_filters(df)
    st.caption(f"{len(filtered)} filas mostradas de {len(df)} totales.")
    st.dataframe(filtered, use_container_width=True, hide_index=True)
    _render_detail(filtered)

    st.subheader("3. Actualizar desde SECOP II")
    st.caption(
        "Consulta datos.gov.co para cada fila y actualiza las columnas de "
        "modificatorio, estado y fecha. Crea automáticamente un backup."
    )
    if st.button("🔄 Actualizar todos los procesos ahora", type="primary"):
        _run_update(current_path, settings)
        st.rerun()

    last_report = st.session_state.get("last_report")
    if last_report:
        with st.expander("Último reporte", expanded=False):
            st.json(last_report)
        if st.button("📂 Abrir carpeta del Excel"):
            _open_file_in_explorer(current_path.parent)


if __name__ == "__main__":  # pragma: no cover
    main()
