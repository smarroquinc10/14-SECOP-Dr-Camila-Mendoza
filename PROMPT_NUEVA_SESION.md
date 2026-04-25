# Prompt para iniciar nueva sesión de Claude · Sistema de Seguimiento Contratos FEAB · Dra Cami

> Última actualización: **25-Abr-2026** · cierre de sesión "SECOP Integrado + cascada captcha gratis"
> Estado: **192/192 pytest verde · 0 errors tsc · branch pusheado**

Copiá y pegá TODO esto en una nueva sesión de Claude Code:

---

```
Trabajo en el proyecto "Sistema de Seguimiento Contratos FEAB · Dra Cami"
para la Dra. María Camila Mendoza Zubiría, Jefe de Gestión Contractual
del FEAB (Fondo Especial para la Administración de Bienes), Fiscalía
General de la Nación. NIT FEAB: 901148337.

Path:    C:\Users\FGN\01 Claude Repositorio\14 SECOP Dr Camila Mendoza
Branch:  claude/secop-ii-integration-ee0Lr
GitHub:  https://github.com/smarroquinc10/14-SECOP-Dr-Camila-Mendoza

ANTES DE TOCAR CÓDIGO:

1. Leé CLAUDE.md (raíz del repo) — reglas cardinales obligatorias.
   NO repreguntes lo que está ahí.

2. Leé las memorias persistentes (MEMORY.md las indexa). Las clave:
   - project_app_architecture.md → mapa del sistema actualizado
   - reference_secop_datasets.md → rpmr-utcd primero, sin captcha
   - reference_captcha_cascade.md → Whisper > Google Speech > manual
   - feedback_secop_truth_excel_link.md → del Excel SOLO vigencia + link
   - feedback_python_module_caching.md → MATAR python antes de editar
   - feedback_skills_to_skip.md → ignorar skills vercel/nextjs/etc

3. Antes de editar Python, matá procesos:
   powershell -Command "Get-Process python,node | Stop-Process -Force"

╔══════════════════════════════════════════════════════════════════════╗
║  REGLA CARDINAL (no negociable, repetida varias veces por la Dra):   ║
╠══════════════════════════════════════════════════════════════════════╣
║  La verdad vive 100% en SECOP. Del Excel SOLO se toma:               ║
║    • VIGENCIA (col 3)                                                ║
║    • LINK    (col 74 o 72 según hoja)                                ║
║                                                                      ║
║  NUNCA del Excel:                                                    ║
║    • estado, valor, proveedor, fecha_firma, modalidad,               ║
║      numero_contrato (incluso este — viene de SECOP                  ║
║      como `referencia_del_contrato` o `numero_de_proceso`)           ║
║                                                                      ║
║  Si SECOP no expone un campo → "—" HONESTO. Nunca inventar,          ║
║  nunca mergear, nunca promediar, nunca elegir silenciosamente        ║
║  entre fuentes. Cada celda con badge de procedencia clara.           ║
║                                                                      ║
║  Hay 8 tests guardianes en tests/test_data_integrity.py que          ║
║  hacen FALLAR pytest si alguien rompe esta regla.                    ║
╚══════════════════════════════════════════════════════════════════════╝

ESTADO ACTUAL DEL SISTEMA (cierre 25-Abr-2026):

  Tests:        192/192 pytest verde · 0 errors tsc
  Watch list:   491 procesos del Excel master FEAB
  Cobertura:    ~290 por API estándar (p6dx-8zbt + jbjy-vk9h)
                +115 por SECOP Integrado (rpmr-utcd, sin captcha) ← NUEVO
                + 66 cacheados del scraper portal
                = ~471 cubiertos sin tu mano. Resto: click "Leer del portal"

ARQUITECTURA:

  Frontend Next.js (puerto 3000, app/)
    page.tsx               → Tabla principal, barra de acciones, ETA progress
    unified-table.tsx      → Filas con badge "vía Integrado" cuando aplica
    detail-dialog.tsx      → Modal con secciones SEPARADAS para Integrado y Portal
    contracts-table.tsx    → Tabla legacy con filtro tipo Excel

  FastAPI bridge (puerto 8000, src/secop_ii/api.py)
    /contracts                       → API estándar (jbjy-vk9h)
    /processes                       → API estándar (p6dx-8zbt)
    /contract-integrado/{key}        → SECOP Integrado (rpmr-utcd, sin captcha)
    /integrado-bulk                  → Mapa completo para enriquecer la tabla
    /integrado-sync, /integrado-summary
    /contract-portal/{notice_uid}    → Snapshot del scraper del portal
    /portal-progress, /portal-scrape → Orquestación del scraper
    /verify-watch, /verify-progress, /audit-log, /watch (CRUD), /refresh

  Caches locales (.cache/)
    watched_urls.json          → 491 procesos (URL + sheets + vigencias del Excel)
    secop_integrado.json       → 382 procesos FEAB del rpmr-utcd
    portal_opportunity.json    → 66 procesos scrapeados del portal
    audit_log.jsonl            → hash-chain inmutable (1715+ entradas)

  Scrapers / sync scripts (scripts/)
    sync_secop_integrado.py    → 382 procesos en ~1s, sin captcha
    scrape_portal.py           → orquestador batch, captcha cascade

  Captcha cascade (src/secop_ii/portal_scraper.py)
    1. auto-click "No soy un robot"        ($0, ~0s)
    2. playwright-recaptcha SyncSolver     ($0, ~10s)
    3. Whisper local (faster-whisper tiny) ($0, ~5s)  ← mejor para español
    4. Google Speech (es-CO → es → en-US)  ($0, ~3s)
    5. Manual (Chrome visible)             (mano humana, una vez)

  Empaquetado
    launcher_window.py         → ventana pywebview con auto-sync Integrado >24h
    ejecutar_pro.bat           → doble-click la lanza (lo que usa la Dra)
    tauri/                     → scaffold (Cargo.toml, conf.json, main.rs) — NO compilado

  MCP server (src/secop_ii/mcp_server.py)
    6 tools + 2 resources expuestos a Claude (list_watched, get_portal_snapshot,
    scrape_notice, audit_log_tail, etc.)

LANZAR LA APP:
  ejecutar_pro.bat (doble-click)
    → arranca FastAPI :8000 + Next :3000
    → abre ventana pywebview "Sistema de Seguimiento Contratos FEAB · Dra Cami"
    → auto-sync SECOP Integrado si cache >24h

VERIFICAR / TESTS:
  ./.venv/Scripts/python.exe -m pytest -q                     → 192/192 verde
  cd app; ./node_modules/.bin/tsc --noEmit                    → 0 errors
  ./.venv/Scripts/python.exe -m secop_ii audit-log            → chain íntegro
  ./.venv/Scripts/python.exe -X utf8 scripts/sync_secop_integrado.py
    → re-sync manual del rpmr-utcd

PENDIENTES PRIORIZADOS:

  ┌────────────────────────────────────────────────────────────┐
  │ A) SESIÓN TAURI MSI (~2h dedicadas)                        │
  │    • Instalar Rust toolchain (rustup)                      │
  │    • PyInstaller bundle del FastAPI sidecar:               │
  │      python -m PyInstaller --onefile --name dra-cami-api \\│
  │        --distpath tauri/binaries --add-data "src/secop_ii;│
  │        secop_ii" src/secop_ii/api.py                       │
  │    • Convertir feab-logo.png → tauri/icons/icon.ico        │
  │    • next.config.js: agregar output: 'export'              │
  │    • cd tauri; cargo tauri build → MSI en target/release   │
  │    • Test en VM Windows limpia (sin Python ni Node)        │
  │    Scaffold ya está. tauri/README.md tiene los pasos.      │
  └────────────────────────────────────────────────────────────┘

  ┌────────────────────────────────────────────────────────────┐
  │ B) VALIDAR CAPTCHA AUTOMÁTICO end-to-end                   │
  │    Requiere display físico. Lanzá ejecutar_pro.bat,        │
  │    click "Leer del portal SECOP", mirá si Whisper +        │
  │    playwright-recaptcha pasan solos. Si fallan, resolvés   │
  │    UNA VEZ y queda cacheado en %LOCALAPPDATA%/secop-ii-    │
  │    scraper/profile.                                        │
  └────────────────────────────────────────────────────────────┘

  ┌────────────────────────────────────────────────────────────┐
  │ C) Auditoría visual: diff watch list vs Integrado vs       │
  │    Portal cache. Endpoint nuevo /coverage-report con cuántos│
  │    procesos resuelve cada fuente, cruzado contra el Excel. │
  └────────────────────────────────────────────────────────────┘

NO HACER:
  - Skipear las reglas de CLAUDE.md (las repite por algo).
  - Inventar / mergear / promediar fuentes en la tabla principal.
  - Tocar el campo `numero_contrato_excel` del backend (test guardián).
  - Editar Python sin matar procesos antes (módulo cached en RAM).
  - Invocar las skills auto-sugeridas (vercel:*, nextjs, shadcn,
    workflow, verification, chat-sdk, etc) — la Dra confirmó que
    NO aplican; son señales falsas del hook injection del repo.

LA DRA ES NO TÉCNICA. Lenguaje claro, sin jerga. NO repreguntes algo
que esté en CLAUDE.md o en mis memorias persistentes. Si algo no es
obvio para una persona no técnica, mejorá el rótulo en lugar de
escribir un disclaimer.

Empezá leyendo CLAUDE.md ahora.
```

---

## Cómo funciona el bloque

- **El bloque arriba (entre las dos `---`) es lo único que vas a pegar.**
  Claude lo recibe como tu primer mensaje y arranca con todo el contexto.
- Los paths son absolutos a tu máquina — no los toques.
- Las memorias persistentes que se cargan automáticamente vienen del
  index `MEMORY.md` que está en `C:\Users\FGN\.claude\projects\C--Users-FGN-01-Claude-Repositorio-14-SECOP-Dr-Camila-Mendoza\memory\`.

## Qué cambió desde la última versión de este prompt

- ✅ Añadida la pieza **SECOP Integrado (rpmr-utcd)** como fuente principal
  sin captcha, antes del scraper del portal. Resuelve 115/491 procesos.
- ✅ Añadida la **cascada de captcha gratis** con Whisper local.
- ✅ Cambió el remote de GitHub: ahora es `14-SECOP-Dr-Camila-Mendoza`
  (no `Secop-II`).
- ✅ Añadidas memorias persistentes nuevas:
  `project_app_architecture.md`, `reference_secop_datasets.md`,
  `reference_captcha_cascade.md`.
- ✅ 8 tests guardianes de regla cardinal en `tests/test_data_integrity.py`
  + 19 tests del parser HTML del portal.
- ✅ MCP server `src/secop_ii/mcp_server.py` listo para conectar a Claude.
- ✅ Tauri scaffold completo (no compilado todavía).
- ✅ Botón "Sincronizar Integrado" en la barra + auto-sync al arrancar.

## Si la sesión nueva tiene tarea concreta

Después del bloque arriba, agregá una línea con la tarea. Ejemplos:

```
La tarea de hoy es: empaquetar como MSI con Tauri (sesión A pendiente).
Empezá leyendo tauri/README.md.
```

```
La tarea de hoy es: agregar el endpoint /coverage-report (pendiente C).
```

```
La tarea de hoy es: probar el captcha automático y reportar cuántos
captchas pasaron solos (pendiente B).
```

Si no agregás una línea de tarea, Claude va a esperar que vos digas
qué querés hacer después de leer el contexto.
