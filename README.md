# Secop-II — CRM local de procesos del SECOP II

Herramienta para consultar procesos del SECOP II (Sistema Electrónico para la
Contratación Pública de Colombia) y mantener actualizado un Excel de
seguimiento. Su primer foco es detectar **modificatorios**: adendas al pliego
antes de la firma y adiciones/prórrogas/otrosíes después.

La V1 funciona como **CLI** para validación. La siguiente iteración añadirá
lectura/actualización de Excel y una interfaz web local (Streamlit) empaquetada
como `.exe` para Windows.

---

## ¿Qué hace hoy?

Dado un link público del portal SECOP II (`community.secop.gov.co`), el
programa:

1. **Extrae el identificador** del proceso (`CO1.NTC.…`, `CO1.PPI.…`,
   `CO1.PCCNTR.…`, etc.) de la URL.
2. **Consulta los datasets abiertos** de `datos.gov.co` (Socrata):
   - `p6dx-8zbt` — procesos (incluye `adendas` al pliego).
   - `jbjy-vk9h` — contratos (incluye agregados `valor_pagado_adiciones` y
     `dias_adicionados`).
   - `cb9c-h8sn` — adiciones / modificaciones a contrato (incluye tipo:
     Adición, Prórroga, Otrosí, Suspensión, Cesión).
3. **Reporta** por proceso: ¿hubo modificatorio?, cantidad, tipos, detalle,
   fecha del último y fuente (adenda al pliego vs. modificación al contrato).

No usa scraping del portal porque la web pública tiene reCAPTCHA de Google
que bloquearía cualquier bot. La API de datos abiertos no tiene esa barrera.

---

## Instalación

Requiere Python 3.10+.

```bash
git clone <repo>
cd Secop-II
pip install -r requirements.txt
```

Opcional pero **muy recomendado**: registra un App Token gratuito en
<https://www.datos.gov.co/profile/edit/developer_settings>. Sin token
Socrata aplica `HTTP 429` rápido; con token permite ~1000 req/hora.

```bash
cp .env.example .env
# Edita .env y pega tu token
```

---

## Uso (CLI)

### Extraer el identificador de un link

```bash
PYTHONPATH=src python -m secop_ii parse-url \
  "https://community.secop.gov.co/Public/Tendering/ContractNoticePhases/View?PPI=CO1.PPI.46305103&isFromPublicArea=True&isModal=False"
```

Salida:

```
ID:         CO1.PPI.46305103
Tipo:       PPI
Normalizada: https://community.secop.gov.co/Public/Tendering/ContractNoticePhases/View?PPI=CO1.PPI.46305103
```

### Ver qué queries haría contra `datos.gov.co`

```bash
PYTHONPATH=src python -m secop_ii show-queries "<url-del-proceso>"
```

Imprime las URLs exactas a Socrata. Útil cuando la máquina que corre el CLI no
puede alcanzar `datos.gov.co` (p. ej. sandbox): copia el URL a un navegador
con red abierta y obtén el JSON.

### Consultar SECOP II en vivo

```bash
PYTHONPATH=src python -m secop_ii check-url "<url-del-proceso>" \
  --app-token $SOCRATA_APP_TOKEN
```

Salida esperada:

```
Proceso: CO1.NTC.9999001 (NTC)
  ¿Hubo modificatorio?: Sí
  # modificatorios: 4
  Tipos de modificatorio: Adición; Prórroga
  Detalle modificatorios: 2 adenda(s) al pliego | Adición ($8,000,000) — ... | Prórroga — ...
  Fecha último modificatorio: 2026-03-05T00:00:00.000
  Fuente modificatorio: contrato(2)+pliego(2)
```

### Demo offline con fixtures

Si el equipo no tiene red abierta a `datos.gov.co`, puedes bajar el JSON de
Socrata desde un navegador y pasarlo al programa:

```bash
PYTHONPATH=src python -m secop_ii check-json "<url>" \
  --proceso tests/fixtures/con_modificatorios_proceso.json \
  --contratos tests/fixtures/con_modificatorios_contratos.json \
  --adiciones tests/fixtures/con_modificatorios_adiciones.json
```

Útil también para tests y para documentación.

---

## Tests

```bash
PYTHONPATH=src python -m pytest tests/ -v
```

19 tests cubren el parser de URLs (6 variantes reales del portal) y el
extractor de modificatorios (proceso sin contrato, proceso con adendas +
adiciones, proceso no encontrado, y flags agregados del contrato).

---

## Arquitectura

```
src/secop_ii/
├── url_parser.py           # Extrae CO1.X.NNN de la URL del portal
├── secop_client.py         # HTTP contra Socrata: retries + rate limit + cache
├── config.py               # Dataset IDs y nombres de campo
├── extractors/
│   ├── base.py             # Protocol FieldExtractor + ProcessContext (lazy)
│   └── modificatorios.py   # V1: combina adendas + adiciones en un "Sí/No"
├── cli.py                  # Typer: parse-url, show-queries, check-url, check-json
└── __main__.py             # `python -m secop_ii …`
```

### Extender a más campos

Cada campo nuevo (estado, cuantía, adjudicatario, fechas, …) es:

1. Un módulo nuevo en `extractors/` con una clase que implementa
   `FieldExtractor` (atributos `name`, `output_columns` y método `extract`).
2. Un registro en `extractors/__init__.py::REGISTRY`.

El orquestador y el Excel I/O (próxima iteración) leen ese registro y
componen el resultado. No hay refactor global.

---

## Hoja de ruta (próximas iteraciones)

- [ ] `excel_io.py`: leer/escribir Excel in-place con `openpyxl` preservando
      formato; backup automático antes de escribir.
- [ ] `orchestrator.py`: recorrer filas, invocar extractores, reportar
      progreso.
- [ ] `ui/streamlit_app.py`: tabla CRM con filtros, detalle por fila y botón
      "Actualizar desde SECOP II".
- [ ] `launcher.py` + `build/build_exe.ps1`: empaquetar como `.exe` Windows
      (PyInstaller `--onedir`).
- [ ] Más extractores: estado/fase, cuantía, entidad, adjudicatario, fechas.

---

## Notas sobre el portal SECOP II

El portal público (`https://community.secop.gov.co/...`) tiene **reCAPTCHA de
Google** en la entrada: no es viable hacer scraping automatizado. Por eso la
herramienta consulta exclusivamente la **API abierta de `datos.gov.co`**
(Socrata), que refleja los mismos datos sin CAPTCHA. Latencia típica entre
publicación en el portal y reflejo en Socrata: horas a ~1 día.
