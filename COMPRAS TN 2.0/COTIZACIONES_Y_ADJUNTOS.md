# Cotizaciones y adjuntos por tipo

## Adjuntar documentos en Orquestador Telcos

1. Abra un flujo y edite el paso **Seleccionar archivo**.
2. Elija **Buscar documentos por tipo en la carpeta de la tarea**.
3. Seleccione la carpeta general; se incluyen sus subcarpetas y todos los meses.
4. Marque uno o varios tipos. Puede añadir tipos con nombre y palabras identificadoras separadas por comas.
5. Al ejecutar, se buscan las carpetas con el número exacto de cada tarea. Si hay varias, elija una explícitamente.
6. Revise la lista de archivos y los pasos antes de confirmar.

Se incluyen todos los archivos y todas las versiones de cada tipo elegido. Los nombres se comparan sin distinguir mayúsculas ni tildes; las abreviaturas como OC son palabras completas. Cada archivo se selecciona una sola vez, incluso si coincide con varios tipos. Las subcarpetas correspondientes a otras tareas quedan excluidas.

**Si no hay archivos de ninguno de los tipos seleccionados o algún archivo elegido no existe, está vacío, incompleto, ilegible o cambió desde la validación, esa tarea no inicia ningún paso.** Las tareas válidas pueden continuar. La validación se realiza en segundo plano y vuelve a comprobarse antes de iniciar cada tarea y antes de subir sus archivos.

Las cargas son individuales, con resultado por archivo. Ante una carga sin confirmación, se informa el avance y no se repite automáticamente el flujo completo. Los flujos existentes con una ruta o alias conservan su comportamiento.

## Organizador de archivos

El módulo aparece una sola vez en la sección Bienes.

- Configure la carpeta general, inicialmente `E:\Seadrive\jotoapan_1\My Libraries\Mi Biblioteca\BD_TN`.
- **Escanear correo ahora** usa el rango de fechas mostrado, inicialmente los últimos siete días.
- Para buscar una o varias tareas concretas, ingréselas una por línea y pulse **Buscar estas tareas**. Esta búsqueda revisa todo el correo disponible y recupera los registros históricos de esas tareas, aunque ya se hayan procesado.
- Revise cada adjunto. Puede corregir el proveedor/remitente, cambiar el tipo y elegir entre varias tareas o carpetas candidatas.
- Marque los archivos deseados y pulse **Guardar seleccionados**. Se vuelve a validar GENERAL y se muestra el nombre y destino antes de confirmar.
- **Exportar reporte CSV** conserva el listado y las correcciones visibles.

El escaneo descarga los adjuntos a una caché de la aplicación para revisión; **no crea carpetas de tareas ni guarda documentos en BD_TN**. Solo la confirmación de guardado publica los archivos seleccionados. No se envían ni eliminan correos ni se modifica Google Sheets o Telcos desde este módulo.

### Validación y clasificación

El organizador lee los bloques de la pestaña GENERAL configurada, desde su comienzo: número en C, ítems del bloque y proyecto en L. La presencia de una OC ya generada no excluye la tarea. Una tarea ausente, un asunto con varias tareas o una descripción contradictoria queda pendiente de revisión.

El remitente se compara con los correos principal y secundario de proveedores. Los remitentes sin coincidencia se excluyen. Las imágenes incrustadas de firmas se excluyen. Cotizaciones, fichas técnicas y otros adjuntos se conservan en su formato original; los no reconocidos aparecen como Otros.

### Carpetas y versiones

Se utiliza el mes actual de **America/Guayaquil**, no el mes del correo. Se reutiliza `Octubre` o cualquier variante de mayúsculas; si no existe el mes, se crea al confirmar el guardado.

Dentro del mes se reutiliza la carpeta exacta de la tarea. Si falta, se crea `NÚMERO - PROYECTO DE COLUMNA L`. Ante varias carpetas se requiere elegir una.

Ejemplos:

- `COTIZACION - CEFEIND.pdf`
- `FICHA TECNICA - CEFEIND.xlsx`
- `COTIZACION - CEFEIND - 2026-10-13 115900 - 01.pdf`

El proveedor/remitente del nombre se limita a dos palabras. Se conserva la extensión, se sanea el nombre para Windows y nunca se sobrescribe un documento existente. Contenido idéntico figura como **Ya guardado**; si desaparece un archivo previamente guardado, puede restaurarse desde el adjunto en caché o correo disponible.

## Historial y compatibilidad

La migración `0006_quotation_attachments` añade un historial separado por cuenta, correo y adjunto. Guarda origen, huella, tipo y destino, sin credenciales. El mecanismo de actualización existente respalda automáticamente la base antes de migrarla.

Los tipos viven en Configuración interna bajo `documents/types`, con identificadores estables. La carpeta general del flujo usa `automation/actua_tareas_carpeta_base` o la ruta elegida en el paso; el organizador usa `quotations/root`.

La caché reside en `quotation-cache` dentro de la carpeta de datos de la aplicación. Se guarda primero en temporal y se verifica el contenido; la publicación del documento final es atómica y no reemplaza archivos. Una interrupción puede reintentarse sin duplicar contenido ya publicado.

## Verificación

Las pruebas usan correo simulado, hojas de ejemplo, carpetas temporales y páginas Selenium sintéticas. No se realizaron guardados de cotizaciones reales ni nuevas cargas a Telcos durante esta implementación.

Resultado: 260 pruebas automatizadas aprobadas, sin fallos; comprobación de Ruff aprobada. Se revisaron visualmente la selección de tipos y el reporte del organizador con datos de ejemplo.

Informes y capturas visuales están en `.test-results/`: `cotizaciones-y-adjuntos.xml`, `adjuntos-por-tipo.png` y `organizador-cotizaciones.png`.


## Ajustes de octubre de 2026

El Organizador de archivos está en Bienes. Configuración → Opciones por módulo separa opciones por módulo; General concentra SMTP, IMAP, POP y las conexiones compartidas. Se conservan las claves y los valores existentes.

Se aceptan únicamente remitentes que coincidan exactamente con un correo principal o secundario de un proveedor registrado y asuntos de SOLICITUD DE COTIZACION con número de tarea. Se normalizan tildes y mayúsculas y se toleran errores leves en solicitud/cotización. Esta restricción también rige para búsquedas manuales y resultados históricos: los remitentes internos o desconocidos quedan excluidos.

La búsqueda rápida usa IMAP en modo lectura para filtrar proveedores y fechas en el servidor; para tareas manuales busca sus números sin restringir fechas. Si IMAP no está disponible, se informa el respaldo por POP. POP debe revisar las cabeceras inicialmente, pero las conserva por UID y cuenta; los siguientes escaneos reutilizan cabeceras y adjuntos disponibles. No se borran correos ni se marcan como leídos.

En el editor del Orquestador Telcos, **Agregar flujo existente como paso** incluye una copia de los pasos del flujo elegido. Puede moverla o quitarla como un solo paso. Para actualizar esa copia, quite el paso y agréguelo nuevamente. Al ejecutar se expanden y validan todos los pasos, incluidos los archivos encontrados de los tipos seleccionados, antes de iniciar la tarea.

Verificación de estos ajustes: suite de regresión de 268 pruebas aprobada; las pruebas adicionales de búsqueda IMAP, filtros, caché, configuración y flujos incluidos se ejecutaron de nuevo en `filtros-y-flujos.xml`. No se probó el rendimiento con el buzón corporativo real.


## Listados y confirmaciones

La confirmación de guardado y de envío a Telcos usa una ventana redimensionable con tabla desplazable y botones permanentes. El registro de operaciones comienza plegado; **Mostrar detalles** permite consultarlo sin perder el listado. El editor de flujos se puede desplazar en ventanas pequeñas.

El organizador incluye **Seleccionar todos** y **Quitar selección** para las casillas de archivos. Las tareas ausentes de GENERAL se excluyen tanto del escaneo como del historial recuperado manualmente. Si falta la carpeta del mes actual de America/Guayaquil o la carpeta de la tarea, se crea únicamente después de confirmar el guardado. La revisión no crea estas carpetas.

Al seleccionar varios tipos basta con que exista uno de ellos. Se envían todos los archivos disponibles de los tipos elegidos; la falta de los otros tipos no bloquea la tarea.


El orquestador inicia cada flujo con nombre y modalidad una sola vez por tarea en esta PC. Se deduplican los números del lote, se consultan los éxitos previos y se registra el inicio antes de ejecutar. No se repite automáticamente el flujo completo, aunque falle. Un intento incompleto queda bloqueado para evitar reenviar observaciones o archivos; revise el resultado antes de diseñar otro flujo. El registro `workflow-starts.db` permanece junto a la base y se conserva al actualizar.

Las guías de modificación ahora comienzan con consultar, ejecutar/reanudar, escribir y aceptar la observación. Seleccionar la tarea y capturar datos no forman parte de ese inicio habitual; se conservan para consultas explícitas y variables reutilizables. Los flujos existentes se conservan: para usar la guía nueva, cree un flujo nuevo con **Crear con guía**.
# Ejecución por tarea y archivos

El flujo se ejecuta una sola vez por tarea. Los pasos de consulta, ejecución/reanudación y observación no se repiten por archivo. Dentro de «Subir archivo» se repite solamente la selección y carga de cada documento validado de la carpeta de esa tarea, incluidos todos los archivos y versiones de los tipos elegidos. La siguiente tarea usa su propia carpeta y su propio listado.

Cada selección reemplaza la anterior. Los documentos confirmados no se vuelven a enviar aunque se repita un paso de subida dentro del flujo. Si una carga queda sin confirmar, no se reenvía automáticamente ni se reinicia el flujo completo; el resultado conserva el avance por archivo.

