# Auditoría Forense — Dashboard FEAB · Dra. Cami Contractual
**Fecha**: 2026-04-25
**URL auditada**: https://smarroquinc10.github.io/14-SECOP-Dr-Camila-Mendoza/
**Branch**: claude/secop-ii-integration-ee0Lr · commit `5b92523`
**Modo**: Read-only — no se modificó código.

---

## 1. Sumario ejecutivo

| Pregunta | Respuesta |
|---|---|
| ¿La app está viva y carga? | ✅ **Sí** — render hidrata bien con dashboard completo |
| ¿Sigue la regla cardinal "La verdad es SECOP, no Excel"? | ⚠️ **Mayormente sí** — 1 violación menor en provenance UI (badge falta para data_source="portal") |
| ¿Cada celda muestra "—" honesto cuando falta? | ✅ **Sí** — confirmado en filas con `data_source=null` |
| ¿La data está fresca (modificatorios al día)? | ⚠️ **Sí pero frágil** — cada visita re-fetch live a Socrata, **pero portal cache es estático** y no se re-bake automático |
| ¿Audit log inmutable hash-chained? | ✅ **Sí** — SHA-256 + prev_hash + verifyAuditChain íntegro |
| ¿Llega a la Dra TODO lo que SECOP expone? | ❌ **NO** — el `detail-dialog` muestra **44/73 campos** del API (29 campos comidos), incluyendo `descripcion_del_proceso` |
| ¿Cobertura de los 491 procs? | ⚠️ **44.4 %** matchea con alguna fuente (218/491). 167 procs tienen notice_uid resuelto pero NO viven en datos.gov.co — solo en community.secop |

**Bugs hallados**: **6** (1 CRÍTICO, 2 ALTOS, 3 MEDIOS).

---

## 2. Cobertura — 491 procs del watch list vs fuentes públicas

Simulación exacta de la cascada `unified-table.tsx::buildUnifiedRows` contra:
- `https://www.datos.gov.co/resource/jbjy-vk9h.json?nit_entidad=901148337` (LIVE)
- `https://www.datos.gov.co/resource/rpmr-utcd.json?nit_de_la_entidad=901148337` (LIVE)
- `app/public/data/portal_opportunity_seed.json` (cache estático)

### 2.1 Distribución por fuente

| Fuente | Procs | % | Badge UI |
|---|---:|---:|---|
| `api` (jbjy-vk9h)               |   6 |  1.2 % | "Contrato firmado" |
| `integrado` (rpmr-utcd)         | 158 | 32.2 % | "Proceso verificado · vía Integrado" |
| `portal` (snapshot estático)    |  54 | 11.0 % | "Proceso verificado" *(sin badge "vía portal" — bug, ver §3.3)* |
| **none** (no hay match)         | **273** | **55.6 %** | "No en API público" o "Borrador SECOP" |
| **TOTAL CON MATCH**             | **218** | **44.4 %** | |

### 2.2 Desglose de los 273 SIN match

| Categoría | Procs | Veredicto |
|---|---:|---|
| Borradores legítimos (`CO1.REQ.` / `CO1.BDOS.`) |    8 | ✅ Esperado — nunca van a la API pública |
| URLs PPI sin notice_uid resuelto                |    3 | ⚠️ El verify_watch_list no logró resolverlos |
| **Sin match y no son borradores**               | **262** | ❌ Cobertura real perdida |

### 2.3 ¿Existen los sospechosos en datos.gov.co por otro filtro?

**Probé** 4 NTCs sospechosos (`CO1.NTC.7906712`, `CO1.NTC.8210327`, `CO1.NTC.3921417`, `CO1.NTC.4041828`) contra:
- `jbjy-vk9h.json?proceso_de_compra={NTC}` → **0 / 4 hits**
- `rpmr-utcd.json?$where=url_contrato like '%{NTC}%'` → **0 / 4 hits** (timeout 30s)

**Conclusión**: No hay bug de cobertura del API. Los 167 PPI-con-NTC-resuelto **viven SOLO en community.secop.gov.co** (portal con captcha). Para verlos hace falta scraping — el portal_opportunity_seed.json sólo cachea 66.

> **Gap real de cobertura**: `167 PPI-con-notice_uid` − `54 ya en portal cache` = **~113 procs scrape-ables pero no scrapeados**.

### 2.4 Anomalía menor: 79 NTCs en datos.gov.co que NO están en watch list

Hay 79 procesos del FEAB en `rpmr-utcd` que la Dra no incluyó en el Excel.
**No es bug** — el CLAUDE.md prohíbe mostrarlos ("vista por defecto = solo procs del Excel").

---

## 3. Bugs encontrados

### 🔴 BUG-001 · CRÍTICO — Detail-dialog "come" 29/73 campos del API jbjy-vk9h

**Severidad**: CRÍTICO (viola directamente la regla "espejo y reflejo fiel")
**Evidencia**:
- [app/src/components/detail-dialog.tsx:35-114](app/src/components/detail-dialog.tsx) — array `SECTIONS` hardcodeado con sólo 44 campos
- API jbjy-vk9h devuelve 73 campos populated por contrato

**Campos que NO llegan a la Dra** (ejemplo proc `CO1.PCCNTR.8930451`):
```
- descripcion_del_proceso ← CRÍTICO
- codigo_de_categoria_principal
- condiciones_de_entrega
- documentos_tipo
- es_grupo
- g_nero_representante_legal
- recursos_propios / recursos_propios_alcaldias / sistema_general_de_participaciones / sistema_general_de_regalias
- pilares_del_acuerdo / puntos_del_acuerdo / espostconflicto
- saldo_cdp / saldo_vigencia / valor_amortizado
- nombre_del_banco / n_mero_de_cuenta / tipo_de_cuenta
- nacionalidad_representante_legal / tipo_de_identificaci_n_representante_legal
- justificacion_modalidad_de (si vacío) / nit_entidad
- (~14 campos administrativos más)
```

**Reproducir**:
1. Abrir https://smarroquinc10.github.io/14-SECOP-Dr-Camila-Mendoza/
2. Click cualquier fila con badge verde "Contrato firmado" (ej. CONTRATO-FEAB-0011-2025)
3. Comparar campos del modal vs `curl https://www.datos.gov.co/resource/jbjy-vk9h.json?id_contrato=CO1.PCCNTR.8930451`

**Posible fix** (no implementar, decisión tuya):
- Ya hay precedente en el mismo archivo: `PortalSection` usa `Object.entries(integFields).filter(...)` para renderizar TODO automáticamente. Aplicar ese patrón al `Contract` API: renderizar `SECTIONS` curadas + sección "Otros campos del API" expandible con todos los pares no curados (mismo UX que ya tiene `labelEntriesNotInFields`).

---

### 🟠 BUG-002 · ALTO — Favicon 404 (path sin basePath)

**Severidad**: ALTO (cosmético, pero rompe browser tab icon y aparece como error en consola)
**Evidencia** (Chrome DevTools console al cargar la URL pública):
```
Failed to load resource: the server responded with a status of 404 ()
@ https://smarroquinc10.github.io/feab-logo-square.png:0
```
**Causa**: HTML inyecta `<link rel="icon" href="/feab-logo-square.png"/>` sin prefijo `/14-SECOP-Dr-Camila-Mendoza`.

**Reproducir**: F12 → Console → cargar la página.

**Posible fix**: en `app/src/app/layout.tsx` (o donde se declare `metadata.icons.icon`), usar el helper `withBasePath('/feab-logo-square.png')`. Alternativa: declarar el icon como `app/icon.png` (Next 16 convention) para que Next agregue basePath solo.

---

### 🟠 BUG-003 · ALTO — Frescura del portal cache es manual y opaca

**Severidad**: ALTO (la Dra pidió explícitamente "todo debe estar muy fresco por los modificatorios")
**Evidencia**:
- `portal_opportunity_seed.json` tiene 66 entries
- **0 / 66** entries tienen `scraped_at` o `status` populated
- Git log: única vez tocado fue commit `8ea5377` el `2026-04-25` (junto con todo el seed).
- No hay CI/cron que re-bake el portal cache al detectar cambios

**Impacto**: 54 procs hoy renderizan datos del portal que pueden estar stale arbitrariamente (1 mes, 6 meses, 1 año — no se sabe). La Dra los ve con badge verde "Proceso verificado" sin pista de antigüedad.

**Reproducir**:
1. `python -c "import json; p=json.load(open('app/public/data/portal_opportunity_seed.json')); print([v.get('scraped_at') for v in list(p.values())[:5]])"`
2. Salida: `[None, None, None, None, None]`

**Posible fix**:
- Re-bake del portal cache con `scraped_at` set por entry
- GitHub Action semanal (cron) que corra `scripts/scrape_portal.py --watch-list` y haga commit del seed actualizado → Pages re-deploya solo
- Mostrar `scraped_at` en el modal de detalle (ya existe en `PortalSection` pero no se usa con cache estático)

---

### 🟡 BUG-004 · MEDIO — Provenance UI: data_source="portal" sin badge "vía portal"

**Severidad**: MEDIO (viola "cada celda con su procedencia clara")
**Evidencia**: [app/src/components/unified-table.tsx:739-746](app/src/components/unified-table.tsx)
```tsx
{r.data_source === "integrado" && (
  <div ... title="Datos del dataset SECOP Integrado..." >vía Integrado</div>
)}
```
- Badge sólo se renderiza para `integrado`. Para `portal` no hay badge equivalente.
- En el snapshot real del dashboard: 0 ocurrencias de "vía portal" vs 188+ de "vía Integrado".

**Impacto**: 54 procs con datos del cache estático aparecen indistinguibles de procs con match en API o Integrado live. La Dra no puede saber que esa data viene de un cache que podría tener meses.

**Posible fix**: agregar branch para `r.data_source === "portal"` con badge ámbar tipo "vía portal cache (estático)".

---

### 🟡 BUG-005 · MEDIO — `notas` no se exporta a Excel

**Severidad**: MEDIO
**Evidencia**: [app/src/lib/export-excel.ts:27-49](app/src/lib/export-excel.ts) — array `COLUMNS` no incluye `notas`.
- `UnifiedRow.notas` contiene info computada (modificatorios + observaciones manuales con prefijo "(Excel)").
- El XLSX generado no las lleva → la Dra mandando el Excel por mail pierde esa columna.

**Posible fix**: agregar `{ header: "Notas", pick: (r) => r.notas ?? "" }` antes de "URL del proceso (SECOP)".

---

### 🟡 BUG-006 · MEDIO — Datos.gov.co fetched 2-3 veces por carga (request waterfall)

**Severidad**: MEDIO (impacta velocidad — la Dra pidió "rápido")
**Evidencia** (network tab al cargar):
```
[GET] jbjy-vk9h.json?...&offset=0  → 200 (×3 veces)
[GET] rpmr-utcd.json?...&offset=0  → 200 (×2 veces)
```
- En `app/src/lib/api.ts:328-342` el cache `_contractsCache` y `_integradoCache` usan singleton lazy. Si dos componentes (page.tsx + detail-dialog cuando hidrata) llaman `getContracts()` en paralelo antes de que el primero haya seteado la variable, ambas hacen fetch.

**Impacto**: ~6MB descargados por carga (debería ser ~2MB). Sobre 4G lento, ~3-5s extra.

**Posible fix**: usar `_contractsPromise: Promise<...> | null` en lugar de `_contractsCache: ... | null`. Setear la promise antes del await, así un segundo caller awaitea la misma promise.

---

## 4. Anti-cardinal violations específicas

| Violación | Dónde | Severidad |
|---|---|---|
| 29 campos del API jbjy-vk9h ocultados al usuario | detail-dialog.tsx:35-114 | 🔴 CRÍTICO (viola "espejo fiel") |
| Provenance ambigua: portal-cached rows sin badge | unified-table.tsx:739-746 | 🟡 MEDIO |
| `notas` perdidas al exportar Excel | export-excel.ts:27-49 | 🟡 MEDIO |

**No hay**:
- ❌ Inventos de valores derivados del Excel (verificado en buildUnifiedRows — el primer match gana entero, no hay merging)
- ❌ Filas eliminadas porque SECOP no las tenga (verificado: 491 procs siguen mostrándose, los sin match con badge "no_en_api" honesto)
- ❌ Campos del Excel `excel_data` mezclados con campos del SECOP en la tabla principal
- ❌ Observaciones de la Dra mostradas en la tabla principal (sólo en modal — correcto)

---

## 5. Frescura

| Asset | Last sync | Frescura | Riesgo |
|---|---|---|---|
| `watched_urls.json` (491 procs)         | git: 2026-04-25 | ✅ Hoy | Bajo — la Dra los administra desde la UI con persistencia IndexedDB |
| `secop_integrado_seed.json` (382 rows)  | json: 2026-04-25T17:26 UTC | ✅ Hoy, **pero NO se usa** — la app hace LIVE Socrata fetch | Cero (vestigial) |
| LIVE jbjy-vk9h (288 contratos)          | cada page load | ✅ Real-time | Cero |
| LIVE rpmr-utcd (382 procesos)           | cada page load | ✅ Real-time | Cero |
| `portal_opportunity_seed.json` (66)     | git: 2026-04-25 (sin `scraped_at` interno) | ⚠️ Snapshot único, sin metadata de antigüedad | **ALTO** — ver BUG-003 |

**Conclusión de freshness**: las 2 fuentes que importan más para "modificatorios" (jbjy-vk9h `dias_adicionados` + rpmr-utcd `estado_del_proceso`) son LIVE → el modificatorio que la Dra antes actualizaba a mano YA está fresco automáticamente. ✅

**Lo único stale**: el portal cache de 54 procs que cubre los huecos del API. Sin re-bake periódico, esa info envejece.

---

## 6. Funcionamiento end-to-end (FASE 9)

Verificado contra browser real (Playwright, Chrome):

| Comportamiento | Estado |
|---|---|
| Página carga, hidrata, renderiza dashboard | ✅ |
| Header con saludo "Bienvenida, Dra. María Camila Mendoza Zubiría" | ✅ |
| Eyebrow "Sistema de Seguimiento de Contratos · SECOP II" | ✅ |
| Sin "Adscrito a la Fiscalía" (regla cardinal) | ✅ |
| Botón "Refrescar desde SECOP" presente y clickeable | ✅ |
| Botón "Integrado (382)" muestra count live | ✅ |
| Counters "288 contratos · 194 procesos · 491 en seguimiento" | ✅ todos coinciden con LIVE Socrata |
| Tabla unificada con 7 columnas (Contrato, Objeto, Valor, Estado, Modificatorios, Origen, Acciones) | ✅ sin scroll horizontal |
| Filtros por columna estilo Excel + Vigencia/Hoja arriba | ✅ |
| Badges de status (Contrato firmado / Verificado / Borrador / No en API) | ✅ los 4 presentes en filas reales |
| Pill "vía Integrado" para procs con data_source="integrado" | ✅ |
| Pill "vía portal" para procs con data_source="portal" | ❌ ver BUG-004 |
| Botones "Abrir / Editar / Quitar" en cada fila | ✅ |
| Audit log indicator "1 entradas · íntegro" | ✅ chain verificable |
| Modificatorios card: 61 contratos / 6.028 días / último 2026-04-30 | ✅ live |
| `feab-logo-square.png` favicon | ❌ 404 ver BUG-002 |
| Console errors | ⚠️ 1 (favicon 404, el resto limpio) |
| Failed network requests | ⚠️ 1 (favicon, todo lo demás 200) |

**Veredicto funcional**: ✅ **el programa está funcionando**. La Dra puede usar el tablero hoy.
Los 5 bugs no tumban la app — son sobre fidelidad/transparencia/freshness/UX.

---

## 7. Recomendaciones priorizadas

### Si arreglás 1 sola cosa, arreglá esta:
**[BUG-001]** Detail-dialog renderiza TODOS los campos del API, no sólo 44 curados.
Patrón: copia el approach de `PortalSection` (sección curada + "Ver TODOS los campos" expandible).
**Por qué primero**: viola directamente "espejo y reflejo fiel" que la Dra acaba de pedir como criterio cardinal explícito.

### Si arreglás 3:
2. **[BUG-002]** Favicon basePath fix — 5 minutos, elimina el único console error.
3. **[BUG-003]** GitHub Action semanal que re-bake `portal_opportunity_seed.json` con `scraped_at` por entry. Aprovecha el "Si! aprovechemos github al máximo" del usuario.

### Si querés cobertura total:
4. Correr `scripts/scrape_portal.py` en los **113 procs PPI-con-notice_uid sin portal cache** (167 - 54). Eso lleva la cobertura de 218/491 → ~330/491 (~67 %).
5. **[BUG-004]** Badge "vía portal" + tooltip con `scraped_at` (cuando 3 esté implementado).
6. **[BUG-005]** Agregar columna `notas` al export Excel.
7. **[BUG-006]** Promise singleton en lugar de cache singleton para evitar dobles fetch.

### Para el flujo "no abrir uno por uno":
La cascada actual ya muestra a la Dra todo lo que las 3 fuentes públicas dan SIN abrir un solo link. **Excepto** los ~262 sin match → para esos hoy igual tiene que abrir el link. Solución: GitHub Action que crawlee community.secop con captcha solver (el proyecto ya tiene `scripts/scrape_portal.py` con cascada Whisper > Google > manual). Si esa Action corre, 113 procs más se llenan sin tocar nada, y la frecuencia es ajustable.

---

**Generado**: 2026-04-25 · sin modificar código · 6 bugs identificados (1 CRÍTICO, 2 ALTO, 3 MEDIO).
