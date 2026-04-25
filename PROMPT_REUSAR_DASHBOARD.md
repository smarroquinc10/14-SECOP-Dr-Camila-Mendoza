# Prompt — Clonar el dashboard FEAB a un proyecto nuevo

Pegá este prompt completo en una nueva sesión de Claude Code dentro del
repo del proyecto NUEVO. La sesión va a construir un dashboard idéntico
adaptado al dominio que vos elijas.

---

## CONTEXTO

Estoy montando un dashboard web estático con la misma arquitectura que el
sistema de seguimiento de contratos del FEAB que ya tengo funcionando en
`https://github.com/smarroquinc10/14-SECOP-Dr-Camila-Mendoza` (URL pública:
`https://smarroquinc10.github.io/14-SECOP-Dr-Camila-Mendoza/`).

La idea es replicar **EL MISMO STACK Y FILOSOFÍA** para un nuevo dominio
(no contratos del FEAB; será [TU NUEVO DOMINIO ACÁ — describílo en 1-2
oraciones, ejemplo: "seguimiento de proyectos de inversión municipal" /
"inventario de bienes inmuebles de la Fiscalía" / "lo que sea"]).

## OBJETIVO

Una página web estática deployada en GitHub Pages que:

1. **Carga rápido** — abre en <2 segundos en cel o PC.
2. **Funciona offline** después del primer load (Service Worker).
3. **Sin login**, sin install, sin pop-ups.
4. **Updates instantáneos**: yo cambio código, hago `git push`, el dashboard
   se actualiza solo en ~3 minutos (GitHub Actions deploya a Pages).
5. **El usuario final es CERO-tech** (mi jefa, abogada, sabe abrir Word
   y nada más). Tiene que SOLO hacer click en un favorito y ver la info.

## STACK TÉCNICO (exactamente este, no negociable)

| Capa | Herramienta |
|---|---|
| Frontend | Next.js 16 con `output: "export"` (static export) |
| UI | Tailwind 3 + shadcn/ui + Radix primitives |
| Tablas | TanStack Table v8 |
| Data fetching | SWR para cache + revalidate |
| Estado local | IndexedDB con hash-chain SHA-256 (Web Crypto API) |
| Iconos | lucide-react |
| Excel export | SheetJS (`xlsx`) generando `.xlsx` 100% en browser |
| Hosting | GitHub Pages (gratis, repo público o Vercel free para privado) |
| CI/CD | GitHub Actions workflow `.github/workflows/deploy-pages.yml` |
| Tipos | TypeScript estricto, ESM |

## FILOSOFÍA CARDINAL (esto SI es no negociable)

1. **La verdad es la fuente externa**. Si el dato viene de un API público,
   ese gana siempre. Nunca inventes campos, nunca completes con
   "razonable" si no hay dato.
2. **Cada celda con su procedencia clara**. Badge en columna "Origen"
   que dice de qué fuente viene cada fila ("API 1", "API 2", "Cache",
   "Sin datos públicos").
3. **Honestidad sobre completitud**: si una fuente no tiene un campo,
   mostrá "—" (em-dash). Nunca un placeholder que parezca dato real.
4. **Audit log inmutable hash-chained**: cada operación de la usuaria
   (agregar URL, editar, borrar, marcar) genera una entry en el audit
   log con `prev_hash` + `hash` SHA-256. Si alguien modifica una entry
   vieja, el chain se rompe y la UI muestra "ALERTA INTEGRIDAD".
5. **El usuario nunca ve errores técnicos**. Si algo falla, mostrar
   mensaje en español plano ("No pude conectarme a la fuente — chequeá
   tu internet").

## ESTRUCTURA DE DIRECTORIOS

```
app/
  ├── public/
  │   └── data/
  │       └── seed.json            # Tu data inicial (lista de items que el usuario sigue)
  ├── src/
  │   ├── app/
  │   │   ├── layout.tsx           # Metadata + fonts
  │   │   ├── page.tsx             # Dashboard principal
  │   │   └── globals.css          # Tailwind + tu paleta de colores
  │   ├── components/
  │   │   ├── unified-table.tsx    # TanStack Table con filtros tipo Excel
  │   │   ├── slicer-pills.tsx     # Filtros tipo Power BI (pills clickeables)
  │   │   ├── detail-dialog.tsx    # Modal Radix Dialog de detalle por fila
  │   │   └── ui/*                 # shadcn/ui primitivos (Button, Input, etc.)
  │   └── lib/
  │       ├── api.ts               # Capa de acceso: state-store + APIs externas
  │       ├── socrata.ts           # (o tu equivalente) — calls al API externo
  │       ├── state-store.ts       # IndexedDB schema + audit log
  │       ├── export-excel.ts      # SheetJS → .xlsx descargable
  │       └── utils.ts             # cn, money formatting, etc.
  ├── package.json
  ├── next.config.ts               # output: "export" + basePath condicional
  └── tsconfig.json

.github/workflows/deploy-pages.yml  # CI: build + push a Pages
update.bat                          # one-liner: git add + commit + push
scripts/update.ps1                  # lógica del update.bat
```

## API EXTERNA

[REEMPLAZÁ ACÁ POR TU API:
- URL: ej. `https://api.tudominio.gov.co/...`
- Datasets: dataset1 (descripción), dataset2 (descripción)
- Filtros típicos: ej. ?nit=X&año=Y
- Formato response: JSON
- CORS: ¿abierto público? (tiene que ser, sino no funciona desde browser)
]

Si **NO TENÉS un API externo** (datos viven en un Excel o PDF), pegalos
manualmente como `app/public/data/items.json` y los componentes leen ese
archivo estático. La interactividad se mantiene 1:1.

## REQUERIMIENTOS DE LA USUARIA

1. **Tabla principal** con columnas configurables (filtros tipo Excel
   encima del header de cada columna, ordenable, búsqueda).
2. **Filtros pill** arriba de la tabla por las dimensiones más comunes
   (año, estado, categoría, etc.).
3. **Click en fila → modal de detalle** con TODOS los campos disponibles
   organizados visualmente (no un dump JSON).
4. **Botón "Descargar Excel"** que exporta lo filtrado actual.
5. **Audit log** visible en algún lado (chip pequeño en el header con
   "N entradas · íntegro" o "ALERTA").
6. **Counter prominente**: "X de Y mostrados" arriba de la tabla.
7. **CRUD del watch list**: agregar URL/item, editar inline, borrar.
   Cada operación va al audit log.

## PASOS DE BOOTSTRAP

Hacé estos pasos en orden:

1. **Bootstrap del proyecto Next.js** (si no existe):
   ```bash
   npx create-next-app@latest app --typescript --tailwind --app --eslint --no-src-dir
   cd app
   npm install @tanstack/react-table swr lucide-react xlsx clsx tailwind-merge
   npm install @radix-ui/react-dialog @radix-ui/react-popover @radix-ui/react-select
   npm install class-variance-authority tailwindcss-animate
   ```

2. **Configurar Next.js para static export** (`app/next.config.ts`):
   ```ts
   const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "";
   export default {
     output: "export",
     trailingSlash: true,
     basePath: basePath || undefined,
     assetPrefix: basePath ? `${basePath}/` : undefined,
     images: { unoptimized: true },
   };
   ```

3. **Crear el state-store con IndexedDB** (`app/src/lib/state-store.ts`):
   Hacé el schema con stores: `watch_list`, `audit_log`, `observaciones`,
   `meta`. Implementá hash-chain SHA-256 con `crypto.subtle.digest`.
   Función `ensureSeed(version)` que copia `/data/seed.json` la primera
   vez. Funciones `addWatched`, `editWatched`, `removeWatched`,
   `appendAudit`, `verifyAuditChain`. Helper `withBasePath()` para
   resolver fetches.

4. **Crear el cliente del API externo** (`app/src/lib/socrata.ts` o
   equivalente). `fetchAll<T>(resource, filterParams)` con paginación.
   Tipos exhaustivos del response del API.

5. **Crear `app/src/lib/api.ts`** que compone state-store + cliente.
   Exporta el objeto `api` con métodos `health`, `feab` (o equivalente),
   `contracts` (o tu dataset principal), `auditLog`, `watchList`,
   `watchAdd`, `watchUpdate`, `watchRemove`, `refresh`, `verify`.

6. **`exportRowsToExcel(rows, filename)`** en `app/src/lib/export-excel.ts`:
   `import("xlsx")` dinámico (no infla el bundle), genera `.xlsx`
   con metadata + auto-width de columnas + rename del archivo a
   `{stem}-YYYY-MM-DD.xlsx`.

7. **GitHub Actions** en `.github/workflows/deploy-pages.yml`:
   trigger en push a main + branches feature, setup Node 20,
   `npm ci` en app/, `NEXT_PUBLIC_BASE_PATH=/<repo-name>` para el
   build, agregá `.nojekyll`, upload-pages-artifact + deploy-pages.

8. **`update.bat` + `scripts/update.ps1`** para el one-liner de deploy.
   Stage + commit + push, opcionalmente push a main si estás en otro
   branch.

## CHECKLIST DE QA

Antes de mandarle el link a la usuaria:

- [ ] Tabla carga los items en <2s
- [ ] Filtros pill funcionan
- [ ] Click en fila abre modal con TODA la data disponible
- [ ] Empty cells muestran "—" (no "null", no string vacío, no "0")
- [ ] Cada fuente de datos tiene su badge de provenance
- [ ] Botón "Descargar Excel" exporta lo filtrado, abre bien en Excel
- [ ] Audit log tiene chip "N entradas · íntegro" en header
- [ ] Funciona en Chrome (PC) + Safari iOS + Chrome Android
- [ ] HTTPS del deploy: ✓ en todos los browsers
- [ ] Refresh del browser → la data persiste (IndexedDB)
- [ ] Limpiar filtros vuelve al estado inicial
- [ ] Mobile: tabla scrollea horizontal sin cortar nada
- [ ] Image assets cargan (verificar con `curl -I` que dan 200, no 404
      por basePath mal configurado)
- [ ] Audit log: agregá una entry, refrescá, verificá que sigue ahí.

## ANTI-PATTERNS QUE DEBO EVITAR

- ❌ NO uses `next/image` con static export — usá `<img>` raw + `withBasePath()`
- ❌ NO mergees datos de fuentes diferentes "para llenar gaps" — cada
  celda viene de UNA fuente, badge dice cuál
- ❌ NO inventes valores razonables si el API no tiene el campo
- ❌ NO ignores errores silenciosamente (`catch (e) {}`) — log a consola
  + toast amigable a la usuaria
- ❌ NO uses localStorage para data sensible (5MB cap + sync); usá IndexedDB
- ❌ NO commitees secrets ni keys; las URLs del API son públicas pero
  cualquier auth_token va a `.env.local` (gitignored)
- ❌ NO escribas tests E2E con Playwright si la usaria es la única — el
  test es vos abriendo el browser una vez
- ❌ NO agregues login/auth si no es necesario — para "una sola usuaria
  con un solo dispositivo" el bookmark del browser ES la auth

## OUTPUT QUE QUIERO DE VOS (la sesión Claude Code)

1. Layout completo del proyecto siguiendo la estructura arriba
2. Componentes funcionales (no esqueletos vacíos)
3. CI/CD de Pages funcionando
4. README.md con: cómo correr local, cómo deployar, cómo agregar items,
   cómo cambiar la fuente de datos
5. Commit + push + (yo después habilito Pages en Settings y mandalink
   a la usuaria)

Empezá por:
1. Confirmar que entendiste el dominio nuevo (en 1 oración)
2. Listar archivos que vas a crear con líneas estimadas
3. Esperar mi OK antes de generar código
4. Cuando dé OK, generá todo en commits chicos, con tests (pytest si
   hay backend, vitest/jest si querés en el front).

---

**Notas del FEAB que quizás te sirvan**:

- **`output: "export"` rompe `next/image`**: usá `<img>` raw con un
  helper `withBasePath()`.
- **basePath en GitHub Pages**: el repo se llama `repo-name` y la URL
  es `username.github.io/repo-name/`. Setear `NEXT_PUBLIC_BASE_PATH=/repo-name`
  en CI antes del build.
- **Pages requiere repo público para free tier**. Para repo privado +
  free, usá Vercel o Cloudflare Pages.
- **CORS de tu API externa**: probá con `curl -H "Origin: https://anything.com"`
  si te devuelve `Access-Control-Allow-Origin: *`. Si no, vas a tener
  que proxy a través de un workers / serverless function.
- **Hash-chain en JS**: `crypto.subtle.digest("SHA-256", ...)`. Es nativo
  del browser, no hace falta lib.
- **PowerShell `update.bat` con paths con espacios**: invocá como
  `powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\update.ps1" %*`.
