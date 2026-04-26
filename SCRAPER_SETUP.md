# Scraper del portal SECOP — setup para 100% espejo

> Este documento explica cómo activar el scrape masivo de los 265 procesos
> del watch list que viven SOLO en `community.secop.gov.co` (con captcha)
> y NO están expuestos en las APIs públicas (jbjy-vk9h / rpmr-utcd).
>
> Cuando el scrape esté activo, el dashboard pasa de **218/491 cubierto
> automáticamente (44%)** a **491/491 cubierto = 100% espejo del SECOP**.

---

## Arquitectura del scraper (4 niveles cascada)

El código (`src/secop_ii/portal_scraper.py`) ya implementa una cascada de
solvers de captcha, de gratis a paga, en orden de costo:

| Nivel | Solver | Costo | Velocidad | Robustez |
|---|---|---|---|---|
| 1 | Auto-click "No soy un robot" (cookies persistentes) | $0 | <1s | 95% si la sesión es reciente |
| 2 | `playwright-recaptcha` lib SyncSolver | $0 | 30-60s | 30% (busca botón "Skip" no siempre presente) |
| 3 | Solver manual interno (audio + Whisper local) | $0 | 30-90s | 70% (depende del audio) |
| 4 | Manual humano (ventana Chrome visible) | trabajo Dra/IT | 60-180s | 100% si humano clickea |
| **5** | **CapSolver / 2Captcha (PAGO)** | **~$0.001/captcha** | **30s** | **99.9%** |

**Para llegar a 100% espejo robusto sin trabajo humano**, hay 2 opciones:

---

## Opción A — Cookies persistentes (gratis, requiere humano UNA VEZ)

**Setup**:
1. La Dra/IT hace doble-click en `ejecutar_scraper.bat`
2. Chrome se abre visible
3. Resuelve manualmente los primeros 5-10 captchas (~10-15 min total)
4. Después de eso, `community.secop.gov.co` "confía" en la sesión y deja
   de pedir captchas durante ~30-60 días
5. Las cookies se guardan en `.cache/playwright_profile/` (no se commitea)
6. Las siguientes corridas del scrape son automáticas — solo nivel 1 funciona

**Trabajo recurrente**: cada 30-60 días, repetir paso 3 cuando las cookies
expiren (~10 min de captchas humanos).

**Limitación**: solo funciona en la máquina donde está el profile. NO
funciona en GitHub Action (cookies son secretos por máquina).

**Costo total año 1**: $0 USD + ~30 min humanos al año.

---

## Opción B — CapSolver pago (100% automatizado, también en GitHub Action)

**Setup**:
1. Registrarse en [capsolver.com](https://capsolver.com)
2. Depositar mínimo $5 USD (cubre ~5,000+ captchas, dura años con scrape mensual)
3. Copiar la API key del dashboard de CapSolver
4. Crear archivo `.env` en la raíz del repo (NO commitear, está en `.gitignore`):
   ```
   CAPSOLVER_API_KEY=tu_api_key_aqui
   ```
5. El código lo detecta automáticamente (línea 566 de `portal_scraper.py`):
   ```python
   capsolver_key = os.environ.get("CAPSOLVER_API_KEY") or None
   ```
6. Cuando el solver gratuito falle, el lib pasa el captcha a CapSolver y
   recibe el token resuelto. ~$0.001 por captcha resuelto vía CapSolver.

**Trabajo recurrente**: ninguno. Cuando los créditos bajen, recargar
$5 USD desde el dashboard de CapSolver.

**Funciona en**: máquina local + GitHub Action self-hosted (con secret
`CAPSOLVER_API_KEY` configurado en repo settings).

**Costo total año 1**: $5 USD inicial + ~$1-3/mes según frecuencia de scrape.

---

## Opción C — Híbrido (recomendado)

**Activar ambas**:
1. Agregar `CAPSOLVER_API_KEY` al `.env` (Opción B)
2. La Dra/IT ejecuta `ejecutar_scraper.bat` una vez para generar cookies
   persistentes (Opción A)

**Resultado**:
- Scrape diario/semanal usa cookies → casi todo gratis (nivel 1)
- Cuando aparece un captcha que las cookies no resuelven, CapSolver
  toma el token (~5% de las veces, costo despreciable)
- **100% espejo, ~$0.10 USD/mes, sin trabajo humano**

---

## Ejecutar el scrape

### Local (después de setup):

```powershell
# Una vez (lanza Chrome visible, scrape masivo de los 265 procs sin cobertura)
.\ejecutar_scraper.bat

# O programáticamente:
.\.venv\Scripts\python.exe -X utf8 scripts\scrape_portal.py --progress-file .cache\portal_progress.jsonl

# Solo un proceso específico:
.\.venv\Scripts\python.exe -X utf8 scripts\scrape_portal.py --uid CO1.NTC.5405127
```

### Verificar resultado:

```powershell
# Auditoría completa post-scrape — debe dar scrape: 0
.\.venv\Scripts\python.exe -X utf8 scripts\audit_dashboard_full.py
```

### Subir el seed actualizado al dashboard:

```powershell
# Copiar cache → seed bakeado al deploy
copy .cache\portal_opportunity.json app\public\data\portal_opportunity_seed.json

# Commit + push (GitHub Action Deploy a Pages corre solo en ~40s)
git add app\public\data\portal_opportunity_seed.json _AUDITORIA_DASHBOARD_*.json _AUDITORIA_DASHBOARD_*.md
git commit -m "feat(scrape): cierre gap cardinal — N procesos del portal"
git push
```

---

## Hardening del script

El script tiene timeout duro de **5 min per-item** (Errores #7-#8 en
`_APRENDIZAJES_DASHBOARD_*.md`). Si un proceso supera 5 min en cualquier
solver, se cancela y el batch sigue con el siguiente. **Garantía: el
batch nunca cuelga silenciosamente, en el peor caso da `timeout_hard`
honesto y la auditoría lo detecta.**

---

## Smoke test post-scrape

Después de cualquier corrida del scrape, ejecutar el smoke test canónico
(ver `CLAUDE.md` sección "Smoke test canónico"):

1. Abrir https://smarroquinc10.github.io/14-SECOP-Dr-Camila-Mendoza/ con `cami2026`
2. Verificar los 4 procesos canónicos (api / integrado / portal / none)
3. Si CUALQUIER campo discrepa con community.secop en vivo →
   registrar `Error #N` en `_APRENDIZAJES_DASHBOARD_*.md` + rollback

---

## Estado actual (2026-04-26)

- ✅ Sistema de auditoría operativo (13 checks por proceso, 0 FP/FN cardinales)
- ✅ Scraper con timeout duro per-item (NO cuelga silenciosamente)
- ✅ GitHub Action diaria de auditoría
- ✅ Indicador de cobertura prominente en el dashboard
- ⏳ Cobertura actual: **218/491 (44%)** automático vía APIs
- ⏳ Para 100% espejo: la Dra/IT activa Opción A, B o C arriba

---

**Filosofía cardinal** (heredada del RUNT): la verdad es SECOP. El
dashboard NO debe inventar datos para llenar huecos. Si el captcha
no se resuelve, el proceso queda con badge "No en API público" + `—`
honesto. La Dra hace click "Abrir" y va al portal manualmente — eso
es **el peor caso aceptable**, no el caso esperado.
