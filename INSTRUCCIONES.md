# Instrucciones — CRM SECOP II

Esta herramienta revisa en SECOP II los procesos de tu Excel y lo **actualiza
automáticamente** con la información más reciente (por ahora: si hubo
modificatorio y cuántos).

---

## Antes de empezar

Asegúrate de que tu Excel tenga:

1. **Los encabezados en la primera fila.**
2. **Una columna con la URL** del proceso en SECOP II
   (algo tipo `https://community.secop.gov.co/...`).
   La columna puede llamarse **URL**, **Link**, **Enlace**, **SECOP**,
   **URL del proceso**… la herramienta la detecta sola.

Ejemplo mínimo:

| # | Entidad | URL del proceso | Objeto |
|---|---------|-----------------|--------|
| 1 | FEAB    | https://community.secop.gov.co/Public/Tendering/ContractNoticePhases/View?PPI=CO1.PPI.46305103 | FEAB-EB-0001-2026 |

No tienes que borrar ni mover nada: la herramienta agrega columnas nuevas al
final (y si ya están, las actualiza).

---

## Cómo usarlo

### Paso 1 — Abrir el programa

1. Descomprime el ZIP que te entregaron.
2. Entra a la carpeta `CRM SECOP II`.
3. **Doble clic** en `CRM SECOP II.exe`.

> Si Windows te muestra un aviso azul "Windows protegió tu PC" / SmartScreen:
> haz clic en **Más información** → **Ejecutar de todas formas**. Es porque
> el ejecutable no está firmado por una empresa grande; es seguro.

Se abrirá automáticamente tu navegador en una pestaña que dice
`http://127.0.0.1:...`. **Esa ventana es el programa.**

### Paso 2 — Cargar tu Excel

1. Arriba verás "**1. Tu Excel de procesos**".
2. Haz clic en **Selecciona tu archivo .xlsx** y escoge tu Excel.
3. Automáticamente aparecerá la tabla con tus procesos.

La próxima vez que abras el programa, recuerda el último archivo que usaste.

### Paso 3 — Explorar / filtrar

En la sección "**2. Vista previa**" puedes:

- **Buscar** por cualquier texto (entidad, objeto, nombre…).
- Filtrar **solo los que tienen modificatorio** (o los que no).
- Ordenar por cualquier columna haciendo clic en su encabezado.
- Abrir el panel "**Ver detalle de un proceso**" para ver toda la información
  de una fila.

### Paso 4 — Actualizar desde SECOP II

1. Baja a "**3. Actualizar desde SECOP II**".
2. Haz clic en **🔄 Actualizar todos los procesos ahora**.
3. Verás una barra de progreso y un log en vivo con cada proceso consultado.
4. Al terminar, aparecen 4 tarjetas:
   - **Total** — cuántos procesos se revisaron.
   - **Con modificatorio** — cuántos tuvieron al menos un modificatorio.
   - **Sin modificatorio** — cuántos están limpios.
   - **Errores** — URLs que no se pudieron leer (la herramienta te dice cuál).

**Tu Excel se actualiza directamente**. Las columnas que agrega o actualiza:

**Columnas de control (para saber qué pasó):**

- `Estado actualización` — `ok` / `no_encontrado` / `url_invalida` / `error`.
- `Última actualización` — fecha y hora exactas de la consulta.

**Columnas de auditoría (para verificar contra el portal):**

- `ID identificado` — el código que el programa leyó de la URL (p. ej.
  `CO1.PPI.46305103`). Si alguna fila se ve rara, esto te dice primero si
  fue por mala lectura del link.
- `Fase en SECOP` — `Presentación de oferta` / `Adjudicado` / `Celebrado` /
  etc. Es lo que dice SECOP, no lo que tú anotaste.
- `Entidad en SECOP` — nombre oficial de la entidad contratante. **Compáralo
  con lo que tienes anotado**; si no coincide, pudo haberse pegado una URL
  de otro proceso por error.
- `NIT entidad` — NIT de la entidad oficial.
- `Objeto en SECOP` — objeto del procedimiento según SECOP.
- `Valor estimado` — precio base publicado.
- `Link verificación API` — **enlace que abre el JSON crudo** que el programa
  usó como fuente. Cópialo al navegador y verás exactamente el mismo dato
  que la herramienta leyó. Es tu "prueba irrefutable".

**Columnas de modificatorios (lo que pediste):**

- `¿Hubo modificatorio?` — `Sí` o `No`.
- `# modificatorios` — cuántos en total.
- `Tipos de modificatorio` — `Adición`, `Prórroga`, `Otrosí`, `Adenda`…
- `Detalle modificatorios` — transcripción resumida (no interpretación) de
  cada modificatorio.
- `Fecha último modificatorio`.
- `Fuente modificatorio` — `pliego(N)` (adendas al pliego) + `contrato(M)`
  (adiciones al contrato firmado).

### Paso 5 — Seguridad: backups automáticos

Antes de tocar tu Excel, la herramienta crea una copia de respaldo al lado
del original, con el nombre:

```
TuArchivo.backup_2026-04-24_1530.xlsx
```

Si algo sale mal, simplemente abre el backup.

---

## ⚠️ Muy importante — Verificar que los datos coinciden con el portal

La herramienta **no reemplaza** revisar el portal; lo que hace es
**acelerar** la revisión. Antes de confiar a ciegas, te recomiendo hacer
esta validación la primera vez:

### Rutina de verificación recomendada

1. **Toma 5 procesos** de tu Excel que conozcas bien (algunos con
   modificatorio y algunos sin).
2. Para cada uno, **abre el link del portal** (columna `URL del proceso`)
   y anota lo que ves: fase, entidad, si hay modificatorios en la pestaña
   "Modificaciones" o adendas en la pestaña de documentos.
3. **Corre la herramienta**.
4. **Compara columna por columna**:
   - ¿La `Entidad en SECOP` coincide con la del portal? ✅
   - ¿La `Fase en SECOP` coincide con la fase que ves? ✅
   - ¿La marca `¿Hubo modificatorio?` coincide con lo que ves en la
     pestaña de Modificaciones/Adendas del portal? ✅
5. Si alguna fila **no coincide**: abre el `Link verificación API` de esa
   fila. Verás el JSON exacto que el programa leyó. Eso te dice si el
   problema es:
   - **Latencia** (ver siguiente sección), o
   - **URL del Excel apunta a un proceso distinto** (revisa tu Excel), o
   - **Problema real** (avísale al desarrollador con el link API y la URL).

### ⏱️ Latencia: `datos.gov.co` va con retraso vs. el portal

Los datos que usa la herramienta vienen de **`datos.gov.co`** (datos abiertos
oficiales de Colombia Compra Eficiente), que replica la información del
portal SECOP II **cada cierto tiempo** — típicamente entre **algunas horas
y ~1 día** después de que se publica.

Eso significa:

- ✅ Si el modificatorio se publicó hace **varios días**, la herramienta lo
  ve sin problema.
- ⚠️ Si el modificatorio se publicó **hoy o ayer**, puede que todavía no
  aparezca en la herramienta aunque sí esté en el portal. Vuelve a correr al
  día siguiente.
- La columna `Última actualización` te dice cuándo fue tu última consulta
  — útil para decidir si vale la pena volver a correr.

**Por eso `Link verificación API` es importante:** si alguna vez dudas,
ese link te muestra exactamente la versión de los datos con la que el
programa está trabajando, sin intermediarios.

---

## Preguntas frecuentes

### "Me dice que no encuentra el proceso"

Eso significa que el identificador de la URL aún no aparece en el dataset
público de `datos.gov.co`. Normalmente los datos se reflejan allí **entre
horas y 1 día** después de publicarse en el portal. Vuelve a intentar al día
siguiente.

### "La columna `¿Hubo modificatorio?` no aparece"

Verifica que en el log salga "ok" para esa fila. Si sale "url_invalida"
revisa que el link empiece con `https://community.secop.gov.co/`.

### "Quiero más velocidad / me dio errores 429"

Abre el menú lateral izquierdo:

1. Ve a <https://www.datos.gov.co/profile/edit/developer_settings> y crea un
   **App Token** gratuito.
2. Pégalo en el campo "App Token de datos.gov.co".
3. Haz clic en "Guardar configuración".

Con token puedes consultar ~1000 procesos por hora.

### "¿Qué hago con el archivo `.backup_…`?"

Guárdalo o bórralo si todo quedó bien. Es solo tu Excel como estaba antes.

### "¿Tengo que tener internet?"

Sí, la herramienta consulta en vivo a `datos.gov.co`. Si no hay internet
verás errores en el log.

### "¿Tengo que poner mi usuario del SECOP?"

No. La herramienta solo usa la **información pública** de datos abiertos
(no necesita tu cuenta del portal SECOP II).

---

## Cerrar el programa

- Cierra la pestaña del navegador.
- Si queda una ventanita pequeña abierta, ciérrala también.

No se queda nada corriendo en segundo plano.
