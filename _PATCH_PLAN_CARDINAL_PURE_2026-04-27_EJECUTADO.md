# ✅ EJECUTADO 2026-04-27 — Plan de patch cardinal pura archivado

> Plan implementado en los commits `2b49925` (cascada pura), `b408344`
> (modificatorios), `3c1888e` (modal), `83cd4da` (barrido 9 inconsistencias),
> `6c07bf4` (header), `bedcaa6` (un link = una fila). Bugs detectados
> post-deploy fueron documentados y fixeados en commit posterior (smoke
> E2E + filtro Tipo de contratación + dias_adic residual).
> Archivado para referencia histórica del razonamiento previo a ejecución.

---

# Plan de patch · Cascada cardinal pura `portal > none`

**Branch**: `cardinal-pure-cascade-2026-04-27` (ya creada · NO pusheada)
**Objetivo**: que el dashboard sea espejo 100% de cada link del Excel de Camila
**Trigger filosófico**: 4 confirmaciones consecutivas de Sergio el 2026-04-27
**Zona quemada del CLAUDE.md**: `unified-table.tsx::buildUnifiedRows`
**Pre-requisito de deploy**: scrape `24976400522` debe terminar exitoso primero

---

## Estado HOY vs estado OBJETIVO

| Cobertura visual | HOY | OBJETIVO |
|---|---|---|
| Espejo del link (portal scraped) | 316 | **474** (post-scrape) |
| Datos derivados que NO son espejo (api jbjy + integrado rpmr) | 164 | **0** (eliminados) |
| "—" honesto (cardinal-imposibles) | 11 | **11** |
| "—" + "Solo con tu login" (link interno SECOP II) | 0 | **6** (PCCNTR) |
| **Total reflejo cardinal honesto** | 327/491 (66%) | **491/491 (100%)** |

---

## Cambios concretos en el código

### Archivo único: `app/src/components/unified-table.tsx`

#### Cambio 1 · `verifyStatus` type union (línea 106)
**Antes:**
```ts
verifyStatus: "verificado" | "contrato_firmado" | "borrador" | "no_en_api";
```
**Después:**
```ts
verifyStatus: "verificado" | "contrato_firmado" | "contrato_interno" | "borrador" | "no_en_api";
```

#### Cambio 2 · `classifyStatus` (líneas 197-220)
Agregar detección por URL pattern (NO depender de jbjy):
```ts
// 0. Si el link va al portal interno SECOP II (Contracts Management) → 
//    requiere login institucional, NO scrapeable públicamente
if (watch?.url?.includes("CO1ContractsManagement")) {
  return "contrato_interno";
}
```

#### Cambio 3 · Cascada `dataSource` (líneas 359-366)
**Antes:**
```ts
// Cascada: api > portal > integrado > none
const dataSource: UnifiedRow["data_source"] = contract
  ? "api"
  : portalSnap
  ? "portal"
  : integ
  ? "integrado"
  : null;
```
**Después:**
```ts
// CASCADA CARDINAL PURA (Sergio 2026-04-27): "verdad absoluta = links y punto"
// Solo el scrape del link community.secop cuenta. API jbjy y rpmr son fuentes
// derivadas que mienten (rpmr roto: 33 procs >50% drift; jbjy va a portal con
// login). Ver memoria: feedback_dashboard_es_scraper_de_links.md
const dataSource: UnifiedRow["data_source"] = portalSnap ? "portal" : null;
```

#### Cambio 4 · Cascada valor (líneas 384-396)
**Antes:** `contract → portalSnap → integ → null`
**Después:** `portalSnap → null` (solo)

#### Cambio 5 · Cascada todos los campos (líneas 423-458)
Para cada campo (`numero_contrato`, `objeto`, `proveedor`, `fecha_firma`, `estado`, `modalidad`):
**Antes:** `contract?.X ?? portalSnap?.fields?.X ?? integ?.X ?? null`
**Después:** `portalSnap?.fields?.X ?? null`

#### Cambio 6 · `StatusBadge` (líneas 543-589)
Agregar caso `"contrato_interno"`:
```ts
contrato_interno: {
  label: "Solo con tu login del SECOP II",
  cls: "bg-violet-50 text-violet-700 border-violet-200",
  title:
    "El link de este proceso va al portal interno SECOP II que requiere tu login institucional. " +
    "El sistema no puede leerlo automáticamente. Click 'Abrir' y verificá con tu sesión.",
},
```

#### Cambio 7 · Label de filtro popover (líneas 1245-1252)
Agregar entry:
```ts
case "contrato_interno": return "Solo con tu login";
```

---

## Lo que NO cambia (preservado por compatibilidad)

- **Tipo `data_source` mantiene** `"api" | "integrado" | "portal" | null` para no romper export-excel.ts ni page.tsx. Solo dejamos de ASIGNAR `"api"` y `"integrado"` desde buildUnifiedRows. Si después queremos limpiar el tipo, otro PR.
- **`_raw_api` y `_raw_integrado`** siguen poblándose (para export Excel completo · regla cardinal "ver todo"). NO se usan en la tabla principal.
- **Modal `detail-dialog.tsx`** sigue mostrando todos los campos de cada fuente (transparencia para auditoría · la Dra ve qué dice cada fuente aunque el sistema use solo el portal como autoritativo).
- **`discrepancias`** sigue calculándose y mostrándose (útil cuando portal vs rpmr difieren).
- **Cron diario refresh-seeds** sigue trayendo jbjy + rpmr (para `_raw_*` y para `discrepancias`).

---

## Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Si mergeamos AHORA, los 158 procesos `integrado` pasan a "—" hasta que termine el scrape | **NO mergear hasta que el scrape termine y el seed tenga los 158** |
| Cambio en zona quemada → posible regresión silenciosa | **5 CHECKS pre-deploy + sample manual con Sergio antes de declarar deploy** |
| Tipo `data_source` desalineado entre buildUnifiedRows y export-excel | Mantener tipo wider · solo cambiar valores asignados |
| Sergio quiere distinguir "Foto del SECOP" para los 6 PCCNTR | NO aplica · su badge es `"Solo con tu login"`, no `"Foto del SECOP"` |
| El test suite actual asume cascada `api > portal > integrado` | Re-correr `pytest -q` después del cambio · si fallan, agregar a Errors #N |

---

## Checklist pre-deploy (NO ejecutar antes de scrape success)

- [ ] Scrape `24976400522` terminó exitoso
- [ ] Seed nuevo tiene los 158 procesos `coverage=integrado` ahora como `coverage=portal`
- [ ] `git fetch origin && git pull origin main` (cron auto-commit del seed)
- [ ] Aplicar el patch en branch local
- [ ] `cd app && tsc --noEmit` → 0 errors
- [ ] `pytest -q` → 192/192 PASS
- [ ] `audit_dashboard_full.py` → 6 api → 0, 158 integrado → 0, 474 portal, 11+6 = 17 none
- [ ] `cross_check_fuentes.py` → discrepancias drásticamente reducidas (los 158 ya en portal)
- [ ] `verify_multilayer.py` → 12/12 capas PASS
- [ ] Build local + servir con basePath:
  ```
  cd app && MSYS_NO_PATHCONV=1 NEXT_PUBLIC_BASE_PATH=/14-SECOP-Dr-Camila-Mendoza npm run build
  mkdir -p out_test/14-SECOP-Dr-Camila-Mendoza && cp -r out/* out_test/14-SECOP-Dr-Camila-Mendoza/
  python -m http.server 8770 --directory out_test --bind 127.0.0.1
  ```
- [ ] Sample manual con Sergio: 5 procesos en preview vs link directo del Excel
- [ ] Update CLAUDE.md smoke test #1 (CO1.PCCNTR.8930451 ya no es "Contrato firmado")
- [ ] Update _APRENDIZAJES_DASHBOARD_2026-04-25.md con Error #16 (rationale del cambio)
- [ ] Merge a main + push + deploy GitHub Pages
- [ ] Smoke test canónico en producción con Camila

---

## Mensaje del commit propuesto

```
feat(cardinal): cascada pura portal > none · espejo 100% del link

Sergio + Camila 2026-04-27: el dashboard ahora es espejo cardinal
absoluto del link community.secop. Eliminada toda dependencia de
APIs derivadas (jbjy-vk9h, rpmr-utcd) como fuente autoritativa de
las celdas visibles.

Por qué:
- rpmr-utcd está demostradamente roto: 33 procs con >50% drift de
  valor (caso máximo: rpmr=$361 cuando real es $345.242.994).
- jbjy-vk9h cubre 6 PCCNTR cuyos links van a portal interno SECOP II
  con login institucional (no scrapeable públicamente).
- El workflow real de la Dra es link → portal → Excel. Mostrar datos
  que ella nunca consultó destruye su confianza.

Cambios:
- buildUnifiedRows: cascada api > portal > integrado > none → portal > none
- classifyStatus: nuevo status "contrato_interno" para URLs SECOP II
- StatusBadge: nuevo caso "Solo con tu login del SECOP II"
- _raw_api y _raw_integrado preservados para export Excel + audit log

Cobertura cardinal post-scrape:
- 474 espejo del link (portal scraped)
- 6 honesto · solo verificable con login
- 11 honesto · cardinal-imposibles
- 491/491 (100%) reflejo cardinal honesto

Memorias relacionadas:
- project_porque_fundador.md (la Dra debe confiar)
- feedback_dashboard_es_scraper_de_links.md (workflow operacional)
- feedback_links_unica_verdad_cardinal.md (rpmr está roto)
- feedback_verificaciones_perfectas.md (auditorías 0 FP/FN)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

---

## Pregunta para Sergio antes de ejecutar

¿Apruebas este plan tal cual o querés ajustes?

1. ¿Te parece bien el label `"Solo con tu login del SECOP II"` para los 6 PCCNTR? (alternativas: "Solo con tu sesión", "Abre con tu login", etc.)
2. ¿Querés que mantengamos `_raw_api` y `_raw_integrado` poblados (modal sigue mostrando lo que dicen las fuentes derivadas para auditoría) o cardinal pura total (eliminar también del modal)?
3. ¿Querés que ejecute YA el patch en la branch (sin mergear) y te muestre el diff, o esperás más feedback antes?
