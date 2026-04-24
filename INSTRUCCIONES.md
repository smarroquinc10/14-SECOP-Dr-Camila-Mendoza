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

- `¿Hubo modificatorio?` — "Sí" o "No".
- `# modificatorios` — cuántos en total.
- `Tipos de modificatorio` — "Adición", "Prórroga", "Otrosí", "Adenda"…
- `Detalle modificatorios` — descripción resumida.
- `Fecha último modificatorio`.
- `Fuente modificatorio` — si vino del pliego (adenda) o del contrato.
- `Estado actualización` — "ok" / "no_encontrado" / "url_invalida".
- `Última actualización` — fecha y hora de la última corrida.

### Paso 5 — Seguridad: backups automáticos

Antes de tocar tu Excel, la herramienta crea una copia de respaldo al lado
del original, con el nombre:

```
TuArchivo.backup_2026-04-24_1530.xlsx
```

Si algo sale mal, simplemente abre el backup.

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
