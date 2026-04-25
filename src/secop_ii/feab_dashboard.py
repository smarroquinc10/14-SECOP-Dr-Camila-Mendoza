"""Pull every FEAB process/contract directly from SECOP II.

The CRM mode (Excel-driven) is for the ~86 contracts the Dra. actively
tracks with her own notes. But as head of contratación del FEAB she also
needs a live view of **every** contract published by the entity — not
only those in her spreadsheet. This module provides that second lens:

* ``fetch_feab_processes(client)`` — every row in ``p6dx-8zbt`` with
  ``nit_entidad='901148337'``.
* ``fetch_feab_contracts(client)`` — every row in ``jbjy-vk9h`` with
  ``nit_entidad='901148337'``.

Each returns a pandas ``DataFrame`` with a curated column subset ready
for display in the Streamlit dashboard. The full dicts remain accessible
for drill-down.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from secop_ii.config import (
    DATASET_CONTRATOS,
    DATASET_PROCESOS,
    FIELD_PROCESO_ID,
    FIELD_PROCESO_URL,
)
from secop_ii.secop_client import SecopClient

log = logging.getLogger(__name__)

# FEAB — Fondo Especial para la Administración de Bienes de la FGN
FEAB_NIT = "901148337"

# Max rows to pull in one query. Socrata caps at 50000 per request; 1000
# is more than enough for FEAB (~500 contracts/year).
_MAX_ROWS = 1000


@dataclass
class FeabSnapshot:
    """A point-in-time snapshot of FEAB's SECOP II footprint."""

    processes: pd.DataFrame
    contracts: pd.DataFrame
    fetched_at: str = ""
    counts: dict[str, int] = field(default_factory=dict)


def fetch_feab_snapshot(client: SecopClient) -> FeabSnapshot:
    """Fetch processes + contracts in parallel-friendly order, return a snapshot."""
    from datetime import datetime

    processes = fetch_feab_processes(client)
    contracts = fetch_feab_contracts(client)
    counts = {
        "procesos": len(processes),
        "adjudicados": int((processes.get("adjudicado") == "Si").sum()) if "adjudicado" in processes else 0,
        "contratos": len(contracts),
        "en_ejecucion": int((contracts.get("estado_contrato") == "En ejecución").sum())
        if "estado_contrato" in contracts else 0,
    }
    return FeabSnapshot(
        processes=processes,
        contracts=contracts,
        fetched_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        counts=counts,
    )


def fetch_feab_processes(client: SecopClient, *, limit: int = _MAX_ROWS) -> pd.DataFrame:
    """Return a DataFrame of every FEAB process in ``p6dx-8zbt``."""
    rows = client.query(
        DATASET_PROCESOS,
        where=f"nit_entidad='{FEAB_NIT}'",
        limit=limit,
    )
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df = _flatten_url_columns(df, [FIELD_PROCESO_URL])

    curated_cols = [
        "id_del_proceso",
        "referencia_del_proceso",
        "modalidad_de_contratacion",
        "tipo_de_contrato",
        "nombre_del_procedimiento",
        "fase",
        "estado_del_procedimiento",
        "adjudicado",
        "precio_base",
        "valor_total_adjudicacion",
        "nombre_del_proveedor",
        "nit_del_proveedor_adjudicado",
        "fecha_de_publicacion_del",
        "fecha_de_ultima_publicaci",
        "nombre_del_adjudicador",
        "nombre_de_la_unidad_de",
        "urlproceso",
        "id_del_portafolio",
    ]
    existing = [c for c in curated_cols if c in df.columns]
    other = [c for c in df.columns if c not in existing]
    return df[existing + other]


def fetch_feab_contracts(client: SecopClient, *, limit: int = _MAX_ROWS) -> pd.DataFrame:
    """Return a DataFrame of every FEAB contract in ``jbjy-vk9h``."""
    rows = client.query(
        DATASET_CONTRATOS,
        where=f"nit_entidad='{FEAB_NIT}'",
        limit=limit,
    )
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df = _flatten_url_columns(df, ["urlproceso"])

    curated_cols = [
        "id_contrato",
        "referencia_del_contrato",
        "proveedor_adjudicado",
        "documento_proveedor",
        "objeto_del_contrato",
        "estado_contrato",
        "modalidad_de_contratacion",
        "tipo_de_contrato",
        "valor_del_contrato",
        "valor_pagado",
        "valor_pendiente_de_pago",
        "fecha_de_firma",
        "fecha_de_inicio_del_contrato",
        "fecha_de_fin_del_contrato",
        "liquidaci_n",
        "dias_adicionados",
        "duraci_n_del_contrato",
        "nombre_supervisor",
        "proceso_de_compra",
        "urlproceso",
        "ultima_actualizacion",
    ]
    existing = [c for c in curated_cols if c in df.columns]
    other = [c for c in df.columns if c not in existing]
    return df[existing + other]


def _flatten_url_columns(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Socrata URL-typed columns arrive as ``{"url": "..."}``. Flatten to string."""
    for col in cols:
        if col not in df.columns:
            continue
        df[col] = df[col].apply(
            lambda v: (v.get("url") if isinstance(v, dict) else v) or ""
        )
    return df


__all__ = [
    "FEAB_NIT",
    "FeabSnapshot",
    "fetch_feab_processes",
    "fetch_feab_contracts",
    "fetch_feab_snapshot",
]
