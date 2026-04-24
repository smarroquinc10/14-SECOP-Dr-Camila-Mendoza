"""Configuration constants: Socrata dataset IDs and field names."""

from __future__ import annotations

SOCRATA_BASE = "https://www.datos.gov.co/resource"

DATASET_PROCESOS = "p6dx-8zbt"
DATASET_CONTRATOS = "jbjy-vk9h"
DATASET_ADICIONES = "cb9c-h8sn"

FIELD_PROCESO_ID = "id_del_proceso"
FIELD_PROCESO_URL = "urlproceso"
FIELD_PROCESO_ADENDAS = "adendas"
FIELD_PROCESO_FASE = "fase"
FIELD_PROCESO_ENTIDAD = "nombre_entidad"
FIELD_PROCESO_NIT = "nit_entidad"
FIELD_PROCESO_OBJETO = "descripci_n_del_procedimiento"
FIELD_PROCESO_VALOR = "precio_base"

FIELD_CONTRATO_ID = "id_contrato"
FIELD_CONTRATO_PROCESO = "proceso_de_compra"
FIELD_CONTRATO_URL = "urlproceso"
FIELD_CONTRATO_VALOR = "valor_del_contrato"
FIELD_CONTRATO_ADICIONES_PESOS = "valor_pagado_adiciones"
FIELD_CONTRATO_ADICIONES_DIAS = "dias_adicionados"

FIELD_ADICION_CONTRATO = "id_contrato"
FIELD_ADICION_TIPO = "tipo_modificacion"
FIELD_ADICION_DESCRIPCION = "descripci_n"
FIELD_ADICION_FECHA = "fecha_registro"
FIELD_ADICION_VALOR = "valor_adicion"

DEFAULT_TIMEOUT_S = 15
DEFAULT_PAGE_SIZE = 500
DEFAULT_RATE_NO_TOKEN = 2.0
DEFAULT_RATE_WITH_TOKEN = 5.0
