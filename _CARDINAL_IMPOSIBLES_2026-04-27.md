# Procesos cardinal-imposibles — 11/491 (Camino A · Espejo cardinal)

**Generado**: 2026-04-27
**Auditoría base**: `_AUDITORIA_DASHBOARD_2026-04-26.json`
**Verificación LIVE**: 11/11 confirmados sin cobertura en datos.gov.co (jbjy-vk9h + rpmr-utcd)

> Este documento registra forenseamente los **11 procesos del watch list de
> la Dra que NO se pueden cubrir vía APIs públicas** del SECOP. NO son fallo
> del dashboard — son la **realidad cardinal del SECOP** que el sistema
> refleja honestamente.

---

## Filosofía cardinal aplicada

CLAUDE.md Regla Suprema #3: _"Honesto cuando no sabe. Badge `'No en API público'` para los procs que datos.gov.co no expone. Modal muestra `—` por celda faltante. **NUNCA inventar metadata de relleno.**"_

**Camino A elegido (2026-04-27)**: aceptar 480/491 (98%) como cobertura honesta. NO maquillar el % separando borradores en categorías aparte. El espejo del SECOP incluye la honestidad sobre lo que SECOP no publica.

→ Decisión persistida en `memory/feedback_espejo_no_cosmetica.md`.

---

## Verificación LIVE (2026-04-27)

Para cada uno de los 11, queries directas a Socrata:

```python
# 1. jbjy-vk9h por proceso_de_compra
GET https://www.datos.gov.co/resource/jbjy-vk9h.json?proceso_de_compra={pid}

# 2. rpmr-utcd por url_contrato LIKE
GET https://www.datos.gov.co/resource/rpmr-utcd.json?$where=url_contrato LIKE '%{pid}%' AND nit_de_la_entidad='901148337'

# 3. rpmr-utcd por numero_de_proceso
GET https://www.datos.gov.co/resource/rpmr-utcd.json?numero_de_proceso={pid}
```

**Resultado**: 11/11 con **0 hits** en las 3 búsquedas. Confirmado cardinal-imposible.

---

## Detalle de los 11

### Categoría 1 · Borradores SECOP (REQ) — 8 procesos

URLs apuntan a `secop.gov.co/CO1BusinessLine/Tendering/ProcedureEdit/View?...` —
**portal interno del SECOP, requiere autenticación**. El SECOP no publica
borradores en sus APIs públicas hasta que pasan a estado `NTC` (publicado)
o `PCCNTR` (contrato firmado).

| # | Process ID | Hoja Excel | Vigencia | Pronóstico |
|---|---|---|---|---|
| 1 | `CO1.REQ.9988313` | FEAB 2026 | 2026 | 🟢 ACTIVO — pasará a NTC pronto |
| 2 | `CO1.REQ.9969563` | FEAB 2026 | 2026 | 🟢 ACTIVO |
| 3 | `CO1.REQ.9987321` | FEAB 2026 | 2026 | 🟢 ACTIVO |
| 4 | `CO1.REQ.9989415` | FEAB 2026 | 2026 | 🟢 ACTIVO |
| 5 | `CO1.REQ.10060243` | FEAB 2026 | 2026 | 🟢 ACTIVO |
| 6 | `CO1.REQ.10057635` | FEAB 2026 | 2026 | 🟢 ACTIVO |
| 7 | `CO1.REQ.10059507` | FEAB 2026 | 2026 | 🟢 ACTIVO |
| 8 | `CO1.REQ.804076` | FEAB 2018-2021 | 2019 | 🟡 LIMBO HISTÓRICO — borrador viejo, probable cancelado o sin pasar a NTC |

**Comportamiento esperado**: cuando el SECOP publique los 7 REQ FEAB 2026
(días/semanas/meses), el cron diario `Refrescar seeds` los detecta solos
y suben a coverage cubierto **automáticamente, sin acción humana**. El #8
(REQ 804076 viejo) probablemente queda permanentemente en este estado.

### Categoría 2 · PPI sin notice_uid resuelto — 3 procesos

URLs varían entre portal interno SECOP y community.secop. El proceso
existe en algún flujo del SECOP pero `verify_watch_list.py` no resolvió
un `notice_uid` (formato `CO1.NTC.X`) para él. Estados posibles:
cancelado antes de publicar, en limbo permanente, o transición que no
completó.

| # | Process ID | Hoja Excel | Vigencia | URL pattern | Estado |
|---|---|---|---|---|---|
| 9 | `CO1.PPI.36786565` | FEAB 2025 | 2025 | portal interno | limbo SECOP |
| 10 | `CO1.PPI.39464215` | FEAB 2025 | 2025 | portal interno | limbo SECOP |
| 11 | `CO1.PPI.11758446` | FEAB 2018-2021 | 2021 | community.secop público | **smoke test #4 del CLAUDE.md** — limitación documentada |

**Importante**: el #11 (`CO1.PPI.11758446`) es el caso canónico que el
`CLAUDE.md` ya documenta como "limitación documentada de las 167 PPIs sin
exposición en datos.gov.co". La Dra ya validó este patrón previamente.
Los #9 y #10 caen en la misma familia.

---

## Cómo se ven en el dashboard (espejo cardinal honesto)

Cada uno de los 11 muestra:

- **Badge** rosa: `"No en API público"` (color rose-50/rose-700)
- **Celdas** Objeto, Valor, Estado, Modificatorios: `—` honesto (no inventado)
- **Modal detalle**: vacío con sección "Limitación: este proceso no aparece
  en las APIs públicas del SECOP. Click 'Abrir en SECOP II' para verlo
  manualmente en community.secop"
- **Botón** `↗ Abrir`: la Dra puede ir al portal directamente cuando
  necesite consultarlo

---

## Lo que la Dra le dice a Compliance

> "Trackeo 491 procesos del FEAB. 480 tienen datos públicos extraídos
> automáticamente del SECOP (api/integrado/portal cache). 11 corresponden
> a borradores en preparación (CO1.REQ.*) y procesos que SECOP no publica
> en sus APIs públicas (CO1.PPI.* sin notice_uid). Para esos 11 muestro
> celdas vacías honestas — no invento datos para llenarlos. Cuando el SECOP
> los publique (estados que evolucionan naturalmente), el cron diario los
> captura y migran a cobertura automática sin acción humana."

→ **480/491 = 98%** es la cobertura cardinal honesta del SECOP que el FEAB tiene **HOY 2026-04-27**.

---

## Auditabilidad

- Lista detallada machine-readable: `.cache/_11_imposibles.json`
- Auditoría que generó el set: `_AUDITORIA_DASHBOARD_2026-04-26.json`
- Verificación LIVE: query Python en línea (queries reproducibles arriba)
- Memory persistida: `memory/feedback_espejo_no_cosmetica.md`

**Reproducibilidad**: cualquier sesión futura puede re-correr las queries
LIVE para re-confirmar el set de cardinal-imposibles. Si alguno aparece
publicado en una corrida posterior, el cron diario lo capturará.
