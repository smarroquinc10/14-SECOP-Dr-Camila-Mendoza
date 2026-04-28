# Plan · Relacionar consecutivo FEAB en el dashboard

**Fecha**: 2026-04-28
**Operador**: Sergio Marroquín Cabrera (Profesional FEAB)
**Motivo**: la Dra María Camila Mendoza Zubiría habla de "el contrato 0001 de 2024", no de "CO1.NTC.5405127". Sin el consecutivo `CONTRATO-FEAB-NNNN-VIGENCIA` el dashboard la fuerza a mapear mentalmente con su Excel al lado · violación implícita de la regla cardinal "lenguaje cero-tech para Cami abogada".

---

## Hallazgos del relevamiento (2026-04-28 14:30 UTC)

| Métrica | Valor |
|---|---|
| Filas con dato en el Excel | 680 |
| URLs únicas en el Excel | 570 |
| Pares (consecutivo, link) extraídos | 467 |
| URLs en watch list ∩ Excel | 425 |
| URLs en watch CON consecutivo en Excel | **285 / 491 (58 %)** |
| URLs en watch SIN consecutivo en Excel | 206 / 491 (42 %) |
| Modelo 1 ↔ N de contratos por proceso | confirmado · max 13 contratos en `CO1.PPI.32760277` |
| `numero_contrato` poblado en `watched_urls.json` actual | **0 / 491** |

Las 206 sin consecutivo son procesos sin contrato firmado aún (PPI 112 + NTC 94) o data incompleta del Excel. Para esos el dashboard mostrará `—` honesto en la columna del consecutivo (igual que para cualquier celda sin dato cardinal).

---

## Decisiones cardinales

1. **Prioridad Excel sobre portal**. La columna primaria `numero_contrato` en la tabla usa el del Excel cuando existe; cae al `portalSnap.fields.numero_contrato` solo si el Excel no lo trae. Razón: el Excel es la verdad interna del FEAB; el portal puede tener texto libre distinto.
2. **Modelo 1 ↔ N como lista**. El campo persistido es `numero_contrato_excel: string[]` (NO scalar). Una URL puede tener hasta 13 contratos. Si lo modelo como string, miento.
3. **Tabla muestra el primero + contador**. Cuando hay múltiples, la celda de la tabla muestra `CONTRATO-FEAB-0001-2024 (+12)` con tooltip listando todos. Modal muestra la lista completa.
4. **Honestidad para los 206 sin consecutivo**. La celda del consecutivo muestra `—` honesto, igual que cualquier otro campo cardinal sin dato. NO inventar.
5. **Excepción legítima al cardinal Excel**. CLAUDE.md ya autoriza tomar `numero_contrato` del Excel como excepción legítima junto con vigencia + link (regla 3.1). Esta extracción está permitida.

---

## Zonas tocadas (todas son zonas quemadas del CLAUDE.md → sesión dedicada con plan)

| Archivo | Cambio | Cobertura test |
|---|---|---|
| `src/secop_ii/api.py::_import_workbook_urls` | extraer col 1 (header row 1) o col 2 (header row 4) → `numero_contrato_excel: list[str]` | nuevo test pytest |
| `src/secop_ii/api.py` | helpers `_find_consecutivo_column`, `_extract_consecutivo` | tests directos |
| `app/public/data/watched_urls.json` | regenerado por re-import; +1 campo opcional | smoke E2E |
| `app/src/lib/state-store.ts::WatchedItemRow` | +`numero_contrato_excel?: string[]` | tsc |
| `app/src/lib/api.ts::WatchedItem` + `rowToWatchedItem` | propagar el campo | tsc |
| `app/src/lib/api.ts::SEED_VERSION` | bumpear de `2026-04-25` → `2026-04-28` para forzar re-seed | comentario |
| `app/src/components/unified-table.tsx::UnifiedRow` | +`numero_contratos_excel: string[]` para modal | tsc |
| `app/src/components/unified-table.tsx::buildUnifiedRows` | cascada Excel → portal en `numero_contrato`, populate de la lista | tests existentes deben pasar |
| `app/src/components/detail-dialog.tsx` | sección "Contratos FEAB asociados" cuando hay 1 o más | smoke E2E |

---

## Reglas que esto NO rompe

- ✅ Cardinal puro `portal > —`: no se introduce nueva fuente. El consecutivo sale del Excel, que ya es input legítimo.
- ✅ 0 FP / 0 FN / 0 datos comidos: el campo nuevo solo agrega información que ya existe en el Excel; nada se inventa.
- ✅ Audit log append-only: ningún cambio en la chain.
- ✅ Observaciones de la Dra solo en modal: la nueva sección en el modal NO contiene observaciones, solo identificadores.
- ✅ Lenguaje cero-tech: la columna se llama "Contrato FEAB", el modal "Contratos FEAB asociados".

## Rollback plan

Si en producción aparece UN error que afecta veracidad o usabilidad:

1. `git revert HEAD` sobre el commit de la sesión.
2. Push a main → Pages re-deploya en ~40 s.
3. La SEED_VERSION del rollback es la anterior; Cami al refrescar conserva su IndexedDB pero recibe el bundle viejo.

## Pasos ejecutables

1. ✅ Plan escrito (este archivo).
2. ⬜ Backend Python: extracción.
3. ⬜ Re-importar `watched_urls.json`.
4. ⬜ Frontend: schema + UI tabla + UI modal.
5. ⬜ 5 checks pre-deploy verde.
6. ⬜ Commit + push + deploy.
7. ⬜ Smoke producción con Playwright + sample manual de Cami.
