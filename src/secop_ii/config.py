"""Configuration constants: Socrata dataset IDs and field names."""

from __future__ import annotations

SOCRATA_BASE = "https://www.datos.gov.co/resource"

DATASET_PROCESOS = "p6dx-8zbt"
DATASET_CONTRATOS = "jbjy-vk9h"
DATASET_ADICIONES = "cb9c-h8sn"
# Richer sources discovered from the open-data catalog — capture what only
# OpportunityDetail showed before: dirección de ejecución + modificaciones
# con valor y fecha de aprobación reales.
DATASET_UBICACIONES = "wwhe-4sq8"  # Ubicaciones Adicionales (dirección por contrato)
DATASET_MOD_CONTRATOS = "u8cx-r425"  # Modificaciones a contratos (valor + días + descripción)
# Documentos publicados (PDFs, etc.) — keyed por id_del_portafolio (CO1.BDOS.*).
# 3 datasets cubren ventanas temporales distintas; consultamos los 3 y unimos.
# URLs en ``url_descarga_documento`` son descargables HTTP directo, sin captcha.
DATASETS_ARCHIVO = ("dmgg-8hin", "3skv-9na7", "kgcd-kt7i")
FIELD_ARCHIVO_PROCESO = "proceso"  # contiene CO1.BDOS.*
FIELD_ARCHIVO_NOMBRE = "nombre_archivo"
FIELD_ARCHIVO_EXT = "extensi_n"
FIELD_ARCHIVO_TAMANO = "tamanno_archivo"
FIELD_ARCHIVO_FECHA = "fecha_carga"
FIELD_ARCHIVO_URL = "url_descarga_documento"
FIELD_ARCHIVO_DESCRIPCION = "descripci_n"

FIELD_UBIC_CONTRATO = "id_contrato"
FIELD_UBIC_DIRECCION = "direcci_n"

FIELD_MODCTR_CONTRATO = "id_contrato"
FIELD_MODCTR_VALOR = "valor_modificacion"
FIELD_MODCTR_DIAS = "dias_extendidos"
FIELD_MODCTR_PROPOSITO = "proposito_modificacion"
FIELD_MODCTR_DESCRIPCION = "descripcion"
FIELD_MODCTR_FECHA_APROB = "fecha_de_aprobacion"
FIELD_MODCTR_ESTADO = "estado_modificacion"

FIELD_PROCESO_ID = "id_del_proceso"
FIELD_PROCESO_PORTAFOLIO = "id_del_portafolio"  # CO1.BDOS.* — links to jbjy-vk9h.proceso_de_compra
FIELD_PROCESO_URL = "urlproceso"
FIELD_PROCESO_FASE = "fase"
FIELD_PROCESO_ENTIDAD = "entidad"
FIELD_PROCESO_NIT = "nit_entidad"
FIELD_PROCESO_OBJETO = "descripci_n_del_procedimiento"
FIELD_PROCESO_VALOR = "precio_base"

FIELD_CONTRATO_ID = "id_contrato"
FIELD_CONTRATO_PROCESO = "proceso_de_compra"
FIELD_CONTRATO_URL = "urlproceso"
FIELD_CONTRATO_VALOR = "valor_del_contrato"
FIELD_CONTRATO_ADICIONES_DIAS = "dias_adicionados"

FIELD_ADICION_CONTRATO = "id_contrato"
FIELD_ADICION_TIPO = "tipo"
FIELD_ADICION_DESCRIPCION = "descripcion"
FIELD_ADICION_FECHA = "fecharegistro"

DEFAULT_TIMEOUT_S = 15
DEFAULT_PAGE_SIZE = 500
DEFAULT_RATE_NO_TOKEN = 2.0
DEFAULT_RATE_WITH_TOKEN = 5.0
