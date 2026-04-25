# Aprendizajes en vivo — Dashboard FEAB

**Iniciado**: 2026-04-25 (post-refactor CLAUDE.md estructura RUNT)
**Análogo a**: `_APRENDIZAJES_LOTE_16647_v918.md` del bot RUNT Pro
**Objetivo**: cada error / discrepancia / incidente que aparezca en producción
del dashboard FEAB → handler permanente en código + lección persistida acá.

> **Filosofía** (heredada del RUNT, sección 3 de
> `_APRENDIZAJES_LOTE_16647_v918.md`): si un campo del dashboard no coincide
> con community.secop en vivo, **es FP / FN / dato comido** — no entregar
> Excel ni declarar deploy listo. Fixear el parser / cascada / modal con un
> handler que regresione el caso, y deployar con el smoke test canónico
> (4 procesos del CLAUDE.md sección "Smoke test canónico") verificado.

---

## Formato por error (estricto)

```
### Error #N — NOMBRE_CORTO
**Proceso (si aplica)**: CO1.X.X (process_id o notice_uid)
**Fecha / hora**: YYYY-MM-DD HH:MM (TZ Bogotá)
**Reportado por**: Dra Cami / Sergio / IT / Claude session / GitHub Action / browser
**Síntoma exacto**:
  - Lo que la Dra ve en pantalla (texto exacto, screenshot path si existe)
  - O el error de console (mensaje completo)
  - O el response 4xx/5xx de Socrata
  - O el discrepancy entre dashboard y community.secop
**Causa**: diagnóstico técnico (1-3 párrafos)
**Fix propuesto**: archivo:línea + cambio específico (snippet de código si aplica)
**Impacto**:
  - tabla / modal / Excel / audit log / passphrase / 0 si cosmético
  - cuántos procesos afectados (1, N, todos)
  - si afecta Telegram también (no aplica al dashboard, dejar "n/a")
**Test que regresione**: ruta del test + assertion
**Smoke test canónico**: cuál de los 4 procesos del CLAUDE.md valida el fix
**Status**: PENDIENTE_DIAGNÓSTICO / PENDIENTE_DEPLOY / DEPLOYED / INVALIDATED
```

**Reglas del formato**:
1. Un error por sección. No fusionar (regla "1 fix por deploy" del RUNT).
2. **Status INVALIDATED** si tras investigación resulta no ser bug (ej. la
   Dra interpretó mal una celda). Dejarlo igual con la explicación —
   sirve como antecedente para futuros falsos reportes.
3. **NO borrar** entradas. Si un fix se rolledback, agregar **Error #N+1**
   con causa "rollback de #N" y explicación.
4. Si la causa es zona prohibida del CLAUDE.md → marcarlo explícitamente
   ("Zona quemada, requirió sesión dedicada").

---

## Histórico — incidentes pre-formato (referencia)

Los siguientes 6 bugs fueron capturados en `AUDIT-REPORT-2026-04-25.md`
ANTES de adoptar este formato. Quedan como antecedente histórico — todos
ya están **DEPLOYED** y verificados en `VERIFICATION-REPORT-2026-04-25.md`
(18/18 PASS) y `COMPLIANCE-REPORT-2026-04-25.md` (5+6 PASS):

| # legacy | Severidad | Resumen | Archivo:línea fix | Verificado en |
|---|---|---|---|---|
| BUG-001 | 🔴 CRÍTICO | Detail-dialog comía 29/73 campos del API jbjy-vk9h | `app/src/components/detail-dialog.tsx` (sección "Otros campos del API SECOP" expandida por default) | VERIFICATION §5.1 |
| BUG-002 | 🟠 ALTO | Favicon 404 (path sin basePath) | `app/src/app/layout.tsx` con `withBasePath` | VERIFICATION §2 (favicon 200) |
| BUG-003 | 🟠 ALTO | Portal cache sin `scraped_at` por entry | re-bake + GitHub Action diaria | VERIFICATION §5.3 (badge "vía portal cache · hoy") |
| BUG-004 | 🟡 MEDIO | `data_source="portal"` sin badge "vía portal" | `app/src/components/unified-table.tsx` branch portal | VERIFICATION §5.3 |
| BUG-005 | 🟡 MEDIO | Columna `notas` no exportada a Excel | `app/src/lib/export-excel.ts::COLUMNS` | VERIFICATION §7 (hoja Vista incluye Notas) |
| BUG-006 | 🟡 MEDIO | datos.gov.co fetched 2-3× por carga (waterfall) | Promise singleton en `app/src/lib/api.ts` | VERIFICATION §3 (fetch 1× cada uno) |

**Cardinal violation extra** (encontrada durante COMPLIANCE-REPORT, fix `4e029f2`):
- `unified-table.tsx::buildUnifiedRows` mezclaba `obs_brief` en columna
  `notas` con prefijo `(Excel)` — viola regla cardinal "observaciones
  manuales SÓLO en modal". Fix: `notas = null` en buildUnifiedRows.

---

## Errores en vivo — formato `Error #N`

> Slot vacío. Cuando aparezca el primer incidente real, llenar acá usando
> el formato estricto de arriba. NO modificar el histórico.

<!--
### Error #1 — NOMBRE_CORTO
**Proceso (si aplica)**: ...
**Fecha / hora**: ...
**Reportado por**: ...
**Síntoma exacto**: ...
**Causa**: ...
**Fix propuesto**: ...
**Impacto**: ...
**Test que regresione**: ...
**Smoke test canónico**: ...
**Status**: PENDIENTE_DIAGNÓSTICO
-->

---

## Cierre de cada incidente — checklist

Antes de marcar un Error como **DEPLOYED**:

1. ✅ Test que regresione el caso agregado a `tests/` o test suite TS
2. ✅ Pre-deploy 5 CHECKS pasan (CLAUDE.md sección "5 CHECKS")
3. ✅ Smoke test canónico de los 4 procesos verificado en producción
4. ✅ Si la fix tocó zona prohibida del CLAUDE.md → sample manual de la
   Dra completado (3-5 procesos validados vs community.secop)
5. ✅ Commit con scope claro (1 fix por deploy del RUNT)
6. ✅ Status actualizado en este archivo

Si cualquier paso ❌ → no se declara DEPLOYED, queda PENDIENTE_DEPLOY
hasta cerrar todos los pasos.
