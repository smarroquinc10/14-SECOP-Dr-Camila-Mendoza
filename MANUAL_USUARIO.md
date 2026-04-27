# Manual de Usuario — Dashboard FEAB · Dra Cami Contractual

> Sistema de seguimiento contractual del SECOP II para auditoría legal.
> Espejo automatizado de los 491 procesos del watch list de la Dra
> María Camila Mendoza Zubiría, Jefe de Gestión Contractual del FEAB,
> Fiscalía General de la Nación. NIT FEAB: 901148337.

---

## ¿Qué problema resuelve?

**Antes**: la Dra abría 491 links de community.secop uno por uno, manualmente,
para verificar estado, valor, modificatorios y documentos de cada contrato.

**Ahora**: todos los 491 procesos espejados en un solo tablero, con datos
extraídos automáticamente, sin abrir community.secop salvo para casos puntuales.

---

# 🎯 PARTE 1 — Para la Dra (Cliente final / Auditor)

## 1.1 Cómo entrar al dashboard

| | |
|---|---|
| **URL** | https://smarroquinc10.github.io/14-SECOP-Dr-Camila-Mendoza/ |
| **Passphrase** | `cami2026` |
| **Browser** | Chrome, Edge, Firefox, Safari (cualquiera moderno) |
| **Dispositivo** | PC, iPad, celular — funciona igual |
| **Conexión** | Internet (consume LIVE de datos.gov.co) |
| **Instalación** | **Ninguna** — solo abrir URL |

## 1.2 Qué ves al entrar (el Header)

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Auditoría · Gestión Contractual · SECOP                                 │
│ Bienvenida, Dra. María Camila Mendoza Zubiría                          │
│ [fecha de hoy en español]                                              │
│                                                                         │
│ [Refrescar desde SECOP] [Integrado (382)] [Leer del portal SECOP]     │
│                                                                         │
│ 288 contratos · 194 procesos · 491 en seguimiento                      │
│ │ Última actividad: 26/04 15:06                                        │
│ │ Cobertura automática: 480/491 · 98%   ← honesto, no maquillado       │
│ │ Última firma SECOP: 13/04 (hace 13 días)                             │
│ │ Último refresh portal: hace 3 días                                    │
│ │ [✓ 1 entradas · íntegro]    ← Hash chain del audit log              │
└─────────────────────────────────────────────────────────────────────────┘
```

**Cada indicador**:
- **Contratos / procesos / seguimiento**: contadores LIVE de Socrata
- **Cobertura automática**: cuántos procesos del watch list tienen datos
- **Última firma SECOP**: el contrato más reciente firmado del FEAB en API
- **Audit log íntegro**: chain hash SHA-256 — tampering detectable

## 1.3 La tabla principal (los 491 procesos)

7 columnas + checkbox de selección, sin scroll horizontal:

| Columna | Qué muestra |
|---|---|
| **☑** | Checkbox para seleccionar procesos individuales (ver § 1.7.5) |
| **Contrato** | ID del SECOP (CO1.NTC.X / CO1.PCCNTR.X) + número de contrato del Excel si la Dra lo escribió |
| **Objeto / Proveedor** | Objeto del contrato + proveedor adjudicado |
| **Valor / Firma** | Valor en pesos + fecha de firma |
| **Estado** | Borrador / En ejecución / Modificado / Cancelado / etc. |
| **Modificatorios** | Días adicionados + estado de liquidación |
| **Origen** | Fuente del dato: API · Integrado · Portal cache · No en API público. Para los del portal, segunda línea muestra fecha exacta `Actualizado: YYYY-MM-DD` |
| **Acciones** | [↗ Abrir] [✏ Editar] [🗑 Quitar] |

Click cualquier fila → **modal detalle**. El checkbox NO abre el modal (sirve solo para marcar).

## 1.4 Filtros disponibles (arriba de la tabla)

**Slicer pills** (click para filtrar):

```
VIGENCIA / AÑO DE FIRMA
[2026] [2025] [2024] [2023] [2022] [2021] [2020] [2019] [2018]

ESTADO DEL CONTRATO
[Activo] [Aprobado] [Borrador] [Cancelado] [En aprobación]
[En ejecución] [Modificado] [Publicado]

MODALIDAD DE CONTRATACIÓN
[Contratación régimen especial] [Contratación régimen especial (con ofertas)]

HOJA EXCEL (donde la Dra registró el proceso)
[FEAB 2026] [FEAB 2025] [FEAB 2024] [FEAB 2023] [FEAB 2022] [FEAB 2018-2021]
```

**Búsqueda libre**: campo "Buscar" arriba — busca en process_id, notice_uid,
referencia_del_contrato, objeto, proveedor.

**Toggle**: "Solo contratos modificados" arriba (atajos).

**Botón** "Limpiar filtros" cuando hay filtros activos.

## 1.5 Click en una fila → modal detalle completo

Al clickear un proceso, se abre un modal con TODA la información del SECOP:

```
┌─────────────────────────────────────────────────────────────────────────┐
│ CO1.NTC.5405127 · Subasta de vehículos                          [✕]    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  IDENTIFICACIÓN                                                         │
│  - Process ID: CO1.NTC.5405127                                         │
│  - Notice UID: CO1.NTC.5405127                                         │
│  - Referencia: FEAB-X-2024                                             │
│  - Estado: En ejecución                                                │
│                                                                         │
│  VALORES                                                                │
│  - Valor del contrato: $12.000.000                                     │
│  - Valor adjudicado: $12.000.000                                       │
│  - SMMLV equivalentes: 11.5                                            │
│                                                                         │
│  CONTRATISTA                                                            │
│  - Proveedor: GERMAN DAVID BOTERO RODRIGUEZ                            │
│  - NIT: ...                                                            │
│                                                                         │
│  > Otros campos del API SECOP (28)            [▼ abierto por default]  │
│    Aquí TODOS los demás campos sin curar — descripcion_del_proceso,    │
│    condiciones_de_entrega, codigo_de_categoria_principal, etc.         │
│                                                                         │
│  > Otros contratos del mismo proceso (6)      [▼]                      │
│                                                                         │
│  DOCUMENTOS DEL PROCESO (33)                                            │
│  - MANIFESTACIÓN DE NECESIDAD.pdf      [Descargar]                     │
│  - FICHA TÉCNICA.pdf                   [Descargar]                     │
│  - MATRIZ DE RIESGOS.xlsx              [Descargar]                     │
│  - ... (30 más)                                                         │
│                                                                         │
│  NOTIFICACIONES (5)                                                     │
│  - SUBIR INFORME DE SUPERVISION No. 2 (1/12/2023)                      │
│  - ...                                                                  │
│                                                                         │
│  OBSERVACIONES DE LA DRA (lo que escribió en el Excel col 72)          │
│  > [editable inline]                                                   │
│                                                                         │
│  PROVENANCE                                                             │
│  - Fuente: vía Integrado                                               │
│  - secop_hash: SHA-256...                                              │
│  - code_version: 27dbd8a                                               │
└─────────────────────────────────────────────────────────────────────────┘
```

**Cada proceso muestra cantidad DISTINTA de campos** (depende del tipo):
- Contrato simple: ~60-70 campos
- Subasta de vehículos con 16 grupos: ~350 campos
- Borrador: ~30 campos

El sistema **se adapta** a cada proceso. **NO usa schema fijo**.

## 1.6 Exportar a Excel

Botón "Descargar Excel (X)" — el número refleja los procesos filtrados.

**El XLSX tiene 2 hojas**:

1. **Vista** (16 columnas curadas):
   - Para mandar por mail a Compliance / supervisores
   - Familiar, fácil de leer
   - Incluye Notas (modificatorios + observaciones internas)

2. **Datos completos crudos** (86 columnas):
   - 4 columnas ID (process_id, id_contrato, notice_uid, url)
   - 73 columnas con prefijo `api_` (de jbjy-vk9h)
   - 8 columnas con prefijo `integ_` (de rpmr-utcd)
   - 1 columna con prefijo `portal_` (del portal cache)
   - **Para auditoría forense** — cada fuente identificable, sin merging

## 1.7 Watch list — agregar / editar / quitar URLs

**Agregar URL nueva**: form arriba con input + botón "Agregar". Al agregar
te pregunta a qué hoja del Excel pertenece (selector con FEAB 2026/2025/2024/...).

**Editar URL existente**: lápiz inline en la fila. Enter para guardar, Esc cancela.

**Quitar**: trash en la fila.

**NO existe el botón "Importar del Excel"** — los 491 procesos ya están
importados de una vez. Si la Dra necesita re-importar, **avisa a Sergio**
(IT) y él lo corre por CLI.

## 1.7.5 Refrescar procesos selectivamente del portal SECOP

Hay 2 botones nuevos en el encabezado de la tabla (al lado de "Descargar Excel"):

### "Refrescar visibles (N)"
Click → modal con la lista de N procesos visibles tras los filtros activos
+ 3 caminos para disparar el refresh:

1. **Disparar GitHub Action** (preferido, requiere a Sergio o IT):
   - Modal copia los IDs al clipboard automáticamente
   - Botón abre la página del workflow `scrape-portal-mensual.yml`
   - Sergio click "Run workflow" → pega los IDs en el campo `uids` → click "Run workflow"
   - Toma ~30-45s por proceso (CapSolver resuelve los captchas solo)
   - Al terminar, el seed se actualiza solo y el dashboard muestra datos frescos

2. **mailto Sergio** (fallback): cuando Sergio no está al lado para clickear,
   el modal abre el cliente de mail con asunto y la lista de UIDs prellenados.

3. **Copiar IDs**: para casos donde la Dra/IT quieran usar otro flujo (ej.
   correr `scripts/scrape_portal.py --uids-file ...` localmente).

### "Refrescar seleccionados (N)"
Aparece SOLO cuando la Dra marcó al menos un checkbox en la tabla. Funciona
igual que "Refrescar visibles" pero solo procesa los marcados.

**Cuándo usarlo**:
- Quieren refrescar UN proceso específico que firmaron ayer.
- Quieren refrescar UN GRUPO (ej. todos los activos del FEAB 2025).
- NO quieren gastar CapSolver en los 386 procesos del portal cuando solo
  les interesa refrescar 5.

### Costo y tiempo (CapSolver)
El modal muestra al instante el costo estimado y ETA:
- Costo: ~$0.001 USD por proceso (CapSolver resuelve captchas automáticamente)
- Tiempo: ~30-45s por proceso (5 procesos = ~3 min · 50 = ~30 min · 386 = ~3 h)
- Crédito de $5 USD inicial cubre años de scrapes.

### Restricciones (espejo cardinal)
- Solo aparecen checkboxes en filas con `notice_uid` resuelto o `process_id`
  formato `CO1.NTC.*`. Los borradores REQ/BDOS y PCCNTR sin notice_uid no
  son scrapeables del portal community.secop, entonces no los muestra
  como seleccionables.
- El modal NUNCA dispara el scrape automáticamente — siempre requiere acción
  humana (Sergio click "Run workflow" o mandar el mail). Esto evita gastar
  CapSolver por accidente.

---

## 1.8 Botón "Refrescar desde SECOP"

Click → recarga LIVE jbjy-vk9h + rpmr-utcd → datos frescos al instante.

Útil cuando la Dra acaba de firmar un contrato y quiere ver si ya aparece
en datos.gov.co (típicamente lag de 1-2 semanas, pero a veces antes).

## 1.9 Garantías cardinales (qué puede confiar la Dra)

| Garantía | Verificación |
|---|---|
| **Cero alucinaciones** | El sistema NO usa IA generativa. Solo lee fuentes oficiales literales. |
| **Cero datos comidos** | Cada proceso muestra TODOS los campos disponibles. Si SECOP no expone un dato → `—` honesto |
| **Cero falsos positivos** | Auditoría diaria con 13 checks valida cada celda contra LIVE Socrata |
| **Cero falsos negativos** | Si la fuente tiene un dato y la UI lo descarta → la auditoría lo detecta |
| **Audit log inmutable** | SHA-256 hash chain · tampering detectable en 6 escenarios |
| **Provenance siempre clara** | Cada celda con badge "vía X" + secop_hash + code_version |

## 1.10 Lo que la Dra le dice a Compliance

> "Cada celda viene del SECOP en vivo o de un snapshot del portal con
> badge de procedencia. Las celdas vacías son `—` honestos cuando la
> fuente no expone el dato — no se inventan. Mis observaciones manuales
> viven solo en el modal, no en la data oficial. El audit log
> hash-chained certifica que nadie alteró el historial. Código fuente
> público en GitHub, seeds versionados, workflows registrados."

---

## 1.11 FAQ — Camila preguntando en lenguaje normal

> Sin tecnicismos. Esto es para vos, Camila, cuando dudes algo.

### "¿Tengo que instalar algo?"
**No.** Abre el navegador en cualquier dispositivo (PC, iPad, celular),
escribe la URL y la contraseña. Listo.

### "¿Tengo que actualizar el sistema cada cierto tiempo?"
**No.** El sistema se actualiza solo:
- **Cada día a la 1 AM**: refresca contratos firmados nuevos del SECOP
- **Cada mes el día 1**: refresca todos los procesos del portal
- **Vos** solo abrís y ves los datos al día

### "¿Cómo sé si los datos están al día?"
Mirá los **indicadores del header** arriba:
- 🟢 **"Última firma SECOP: hoy"** o "hace 2 días" = datos frescos
- 🟢 **"Último refresh portal: hoy"** o "hace 5 días" = todo bien
- 🟠 **Si dice "hace 35 días"** = el cron mensual falló, pasale a Sergio
- 🔴 **Si dice "hace 60+ días"** = urgente, pasale a Sergio

### "Hice click en una fila y veo muchos campos. ¿Eso es todo lo que tiene el SECOP?"
**Sí, literalmente todo.** El sistema lee TODOS los campos que el portal
de community.secop muestra para ese proceso. Si un proceso tiene 70
campos, ves los 70. Si tiene 350 (subastas grandes), ves los 350.
Nada se filtra ni se oculta.

### "Veo procesos con celdas vacías ('—'). ¿Es un error?"
**No.** Significa que el SECOP NO expone ese dato. El sistema es honesto
y te muestra `—` cuando la fuente no lo tiene. Si quisieras buscar más,
podés clickear "Abrir" y va al portal directamente — pero rara vez es
necesario porque el dashboard ya tiene casi todo.

### "¿Por qué algunos procesos dicen 'No en API público'?"
Significa que ese proceso **el SECOP NO lo expone** en sus APIs públicas.
Casos típicos:
- **Borradores en preparación** (`CO1.REQ.*`): el SECOP NO publica borradores
  hasta que pasan a `NTC` (publicado) o `PCCNTR` (firmado). Cuando suceda,
  el sistema los captura solos automáticamente — vos no hacés nada.
- **PPI sin notice_uid resuelto**: procesos en limbo SECOP (cancelados antes
  de publicarse o que nunca pasaron a NTC).

**Esto NO es error del dashboard, es honestidad cardinal**: te muestra `—`
en vez de inventar valores. Si la Dra ve uno y quiere consultarlo manualmente,
click `↗ Abrir` → va al portal community.secop directamente. Detalle forense
en `_CARDINAL_IMPOSIBLES_*.md` (commiteado al repo).

### "¿Cómo refresco un proceso específico que firmé ayer?"
Usá la nueva **Feature G** (ver § 1.7.5):
1. En la tabla, marcá el checkbox del proceso (primera columna, izquierda)
2. Click el botón "Refrescar seleccionados (1)" arriba de la tabla
3. Modal se abre con 3 caminos: GitHub Action / mailto Sergio / copiar IDs
4. Sergio dispara el refresh; en ~30-45s tu dashboard muestra datos frescos.

### "Quiero el contrato firmado de uno de los procesos. ¿Dónde está?"
1. Click en la fila → modal se abre
2. Bajá a la sección **"Documentos del proceso"**
3. Vas a ver una lista con los PDFs/Excel del proceso (puede haber 9, 30, 50)
4. Click en el documento que necesitás → se descarga directo

### "Quiero mandar a Compliance un Excel de los contratos modificados de 2026"
1. En el header, click el toggle "🔔 Requieren tu atención" o "Solo modificados"
2. Click en el slicer "Vigencia 2026"
3. Click "Descargar Excel (X)" — solo trae los filtrados
4. El Excel tiene 2 hojas: **Vista** (formato bonito para mail) y **Datos
   completos crudos** (86 columnas para auditoría forense)

### "Veo un proceso con datos raros. ¿Qué hago?"
1. **Anota el proceso ID** (ej. CO1.NTC.5405127)
2. **Mandale un mensaje a Sergio**: "Cami: en CO1.NTC.5405127 veo X pero
   en SECOP veo Y. Revisar."
3. Sergio investiga, documenta como `Error #N` en el sistema, lo arregla,
   te avisa.

### "El sistema me pide la contraseña otra vez. ¿La cambio?"
La contraseña actual es `cami2026`. Solo Sergio puede cambiarla (es un
proceso técnico). Si querés cambiarla, pedíselo.

### "¿Quién más puede ver mis datos?"
Solo quien tenga la contraseña `cami2026`. El sistema NO está indexado
en Google. Si compartís la URL sin la contraseña, nadie ve nada.

### "Quiero agregar 30 contratos nuevos al watch list desde mi Excel"
**Eso sí necesita Sergio** (es un proceso de importación masiva, ~1 minuto
para él). Pero si querés agregar UN proceso, podés:
1. Buscar el botón "Agregar URL" arriba en el dashboard
2. Pegar la URL de community.secop
3. Te pregunta a qué hoja del Excel pertenece (FEAB 2026, 2025, etc.)
4. Click "Agregar"

### "El indicador 'Audit log íntegro' está rojo. ¿Qué pasa?"
Significa que alguien o algo modificó el log de auditoría. **Avisá a Sergio
inmediatamente** — es un evento crítico de seguridad. (Probablemente nunca
pase, está diseñado para detectar tampering).

---

# 🛠️ PARTE 2 — Para Sergio / IT (Mantenedor)

## 2.1 Lo que se actualiza solo (cero acción)

| Cron / Action | Cadencia | Qué hace |
|---|---|---|
| `Refrescar seeds (datos.gov.co)` | Cada día 06:00 UTC (01:00 Bogotá) | Sincroniza APIs jbjy-vk9h + rpmr-utcd |
| `Auditoria diaria del Dashboard FEAB` | Cada día 07:00 UTC (02:00 Bogotá) | 13 checks por proceso · falla si FP/FN |
| `Deploy a GitHub Pages` | En cada `git push` a `main` | ~40s, dashboard live actualizado |

→ **La Dra ve datos frescos cada mañana sin que nadie haga nada**.

## 2.2 Lo que requiere acción tuya OCASIONAL

### Re-scrape del portal (1 vez al mes recomendado)

**Cuándo**: cuando aparezcan procesos PPI nuevos en el watch list que viven
solo en community.secop, o cuando la cobertura automática baje del 100%.

**Cómo** (en TU PC con `.venv` + `.env` + Playwright):

```powershell
cd "C:\Users\FGN\01 Claude Repositorio\14 SECOP Dr Camila Mendoza"

# Doble-click o desde shell:
.\ejecutar_scraper.bat

# Espera ~3-4 horas (CapSolver resuelve captchas automáticamente)

# Cuando termine:
copy .cache\portal_opportunity.json app\public\data\portal_opportunity_seed.json
git add app\public\data\portal_opportunity_seed.json
git commit -m "scrape: refresh mensual — N procesos"
git push origin main
```

→ GitHub Action `Deploy a Pages` corre solo. La Dra ve datos nuevos al refrescar.

### Re-importar desde Excel (raro, solo si la Dra te lo pide)

Cuando la Dra agregue/quite URLs masivamente en su Excel:

```powershell
.\ejecutar_pro.bat                                    # arranca FastAPI :8000
curl -X POST http://localhost:8000/watch/import-from-excel -d "{}"
```

Solo IT corre esto.

## 2.3 Diagnosticar problemas

### Si la Dra reporta "celda mal" / "modificatorio que no llega"

1. Abrir `_APRENDIZAJES_DASHBOARD_<fecha>.md`
2. Documentar como `Error #N` con formato fijo (proceso, síntoma, causa, fix, status)
3. Verificar contra LIVE: `curl https://www.datos.gov.co/resource/jbjy-vk9h.json?...`
4. Si la fuente tiene el dato pero el dashboard no → bug real, fixear código
5. Si la fuente no lo tiene → es limitación de la API, comunicar a la Dra

### Reportes de auditoría diaria

GitHub Actions → run de `Auditoria diaria del Dashboard FEAB` →
ver el output. Si dice `0 FP, 0 FN cardinales` → todo bien. Si dice errores
→ revisar `_AUDITORIA_DASHBOARD_<fecha>.md` con detalle por proceso.

### Logs locales

```
.cache/scrape_full.log              ← último scrape masivo
.cache/portal_progress.jsonl        ← progreso del scrape en JSON
.cache/portal_opportunity.json      ← cache de procesos scrapeados
.cache/audit_log.jsonl              ← chain SHA-256 inmutable (NUNCA editar)
.cache/feab_headers.json            ← cache HTTP headers
```

## 2.4 Costos operacionales

| Servicio | Costo | Frecuencia |
|---|---|---|
| GitHub Pages | $0 | siempre |
| GitHub Actions (cron diario) | $0 (free tier sobra) | siempre |
| datos.gov.co (Socrata) | $0 | siempre |
| **CapSolver** (re-scrape captchas) | **$0.27 USD/scrape** (~$3/año a cadencia mensual) | depende cadencia |

**$6 USD inicial = ~5,000 captchas resueltos = ~18 scrapes completos = años de cobertura**.

## 2.5 Zonas PROHIBIDAS de tocar (sin sesión dedicada)

Si vas a tocar uno de estos archivos, **abrí una sesión Claude dedicada**
y leé `CLAUDE.md` primero. Cada uno tiene auditorías cardinales detrás:

```
app/src/lib/state-store.ts::verifyAuditChain
app/src/lib/state-store.ts::appendAuditLog
app/src/components/unified-table.tsx::buildUnifiedRows
app/src/lib/api.ts::getContracts / getIntegrado (Promise singleton)
app/src/lib/security/passphrase.ts (PBKDF2 200k iter)
app/src/lib/security/url.ts::assertSafeUrl
CSP meta tag en app/src/app/layout.tsx
next.config.mjs::basePath
app/src/lib/export-excel.ts::COLUMNS
src/secop_ii/portal_scraper.py::_try_solve_with_capsolver_direct
```

## 2.6 Pre-deploy 5 CHECKS (antes de cada `git push`)

Estilo RUNT — mostrar los 5 con ✅/❌. Si alguno ❌ → no push:

```powershell
# 1. Tests Python
.\.venv\Scripts\python.exe -X utf8 -m pytest -q
# debe dar: 192/192 passed

# 2. TypeScript
cd app
.\node_modules\.bin\tsc --noEmit
# debe dar: 0 errors

# 3. Audit log integrity
cd ..
.\.venv\Scripts\python.exe -m secop_ii audit-log
# debe decir: íntegro

# 4. Auditoría completa
.\.venv\Scripts\python.exe -X utf8 scripts\audit_dashboard_full.py
# debe dar: 0 FP, 0 FN cardinales

# 5. Smoke test canónico (manual con la Dra)
# Abrir https://smarroquinc10.github.io/14-SECOP-Dr-Camila-Mendoza/
# Verificar 4 procesos canónicos vs community.secop
```

---

# 🚦 PARTE 3 — Capacidades vs Limitaciones (transparencia)

## ✅ Lo que SÍ puede hacer

- Espejo de los 491 links del watch list de la Dra
- Cada proceso con TODOS sus campos (61-354 según tipo)
- Cada proceso con TODOS sus documentos (PDFs descargables)
- Cada proceso con TODAS sus notificaciones
- Filtros (vigencia, estado, modalidad, hoja, búsqueda libre)
- Exportar Excel filtrado o completo (86 cols crudas)
- Audit log inmutable verificable
- Detección automática de drift / FP / FN
- Refresh diario sin acción humana
- Re-scrape mensual con captcha solver automático
- Funcionar en cualquier dispositivo con browser

## ❌ Lo que NO puede hacer

- **Operar el SECOP** (firmar contratos, presentar ofertas, subir docs)
  → eso sigue siendo en community.secop directo
- **Tiempo real instantáneo** — hay lag inherente:
  - APIs Socrata: 1-2 semanas
  - Scrape portal: cuando se ejecuta (mensual o on-demand)
- **Procesos de OTRAS entidades** que no son del FEAB
  → solo NIT 901148337
- **Datos de períodos sin watch list** (la Dra debe agregar URL si quiere seguimiento)

## ⚠️ Limitaciones aceptadas

- **Lag de Socrata vs portal**: si la Dra firmó un contrato hace 2 días,
  posiblemente aún no aparezca en API. Solución: scrape manual on-demand
  para ese proceso específico.
- **Cookies de sesión expiran** ~30-60 días en el scraper. CapSolver maneja
  los captchas que aparezcan después de eso.
- **Cambios estructurales del portal SECOP**: si Vortal cambia el HTML,
  el scraper puede romper temporalmente. La auditoría diaria lo detecta
  como `error_red` y reporta.

---

# 📋 Resumen — quién hace qué

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  DRA CAMILA  →  abre URL · audita · filtra · exporta Excel    │
│                 sample manual ocasional vs community.secop    │
│                                                                 │
│  SERGIO/IT   →  re-scrape mensual (1 click .bat + 3h)          │
│                 fix de bugs cuando aparezcan                   │
│                 mantenimiento del repo                         │
│                                                                 │
│  GITHUB      →  cron diario refresh + audit + deploy           │
│  ACTIONS        sin intervención humana                        │
│                                                                 │
│  CAPSOLVER   →  resuelve captchas del portal automáticamente   │
│                 ~$0.001/captcha · $6 dura años                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

# 🆘 Si algo se rompe

1. **La Dra reporta** → Sergio escucha
2. **Sergio abre Claude Code** en el repo del proyecto
3. **Claude lee** `CLAUDE.md` + `_APRENDIZAJES_DASHBOARD_*.md` + reportes
4. **Documenta** como `Error #N` con formato fijo
5. **Fix** + commit + push → auto-deploy
6. **Smoke test** con la Dra → confirma resolución

Cada error documentado **construye memoria operacional permanente** — el
próximo Claude que entre al repo lee la lección y NO repite el bug.

---

**Filosofía cardinal** (heredada del bot RUNT Pro de Sergio en producción):

> "La verdad es SECOP. NO inventar. NO comer datos. Honesto cuando no sabe.
> Audit log inmutable. Cada celda con su procedencia clara. **Sample manual
> humano es la validación final** — ningún sistema automático reemplaza la
> firma de la Dra diciendo 'verifiqué estos 5 procesos manualmente vs
> community.secop, todos coinciden'."
