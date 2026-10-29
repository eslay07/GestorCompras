# Actualizar tareas: mapa verificado de Telcos

Fecha: 13 de octubre de 2026. Cuenta y permisos del navegador abierto por el usuario.
Se recorrió **Soporte → Tareas**, sin incluir números de tarea ni registros operativos en esta edición pública.
Este mapa corresponde al módulo Tareas y a los controles disponibles con esta cuenta; no afirma cubrir todos los módulos y permisos de Telcos.

## Uso sencillo

1. En el editor, elija un proceso y pulse **Crear con guía**. Complete los textos o el archivo solicitado.
2. Revise los pasos. Cada acción muestra una captura real; **Ver símbolo en Telcos** abre una ayuda ampliada. También aparece al pasar el mouse.
3. Guarde el flujo. En ejecución, active **Ingreso manual**, ingrese solamente el número de tarea y agréguelo al listado.
4. Ejecute y revise el resumen. Las OC, el proveedor y otros datos de importación son opcionales, salvo que el texto del flujo los utilice.

La guía incluye observación, seguimiento, archivo, reasignación, pausa de una tarea ya en ejecución, iniciar y pausar, consulta de datos, historial y archivos. Los flujos guiados leen los datos de la fila antes de los pasos operativos.
La búsqueda del registro y la ayuda funcionan con selección mediante teclado y clic. Los selectores CSS y las variables técnicas se ocultan hasta marcar **Mostrar opciones técnicas**.
Las acciones internas (definir variable, leer por selector, esperar, comprobar estado) no tienen icono en Telcos: se identifican como acciones del orquestador. Un campo sin icono muestra su captura de campo, no un símbolo inventado.

## Estados y botones observados

| Estado | Controles observados |
|---|---|
| Asignada | Ejecutar (play), Ingresar Seguimiento (list-alt), Ver Seguimiento (search), Cargar Archivo (open-file), Ver Archivos (eye-open), Anular |
| Aceptada | Pausar (pause), Reprogramar (retweet), Cancelar (remove-circle), Finalizar (stop), Reasignar (dashboard), Ingresar Seguimiento, Ver Seguimiento, Cargar Archivo, Ver Archivos, Crear Tarea (plus-sign) |
| Pausada | Reanudar (step-forward), Reprogramar, Reasignar, Ingresar Seguimiento, Ver Seguimiento, Ver Archivos |

El mapa visual del editor también permite reconocer Reprogramar, Cancelar, Finalizar y Crear Tarea. Estos cuatro controles se consultan y usan directamente en Telcos; no se anuncian como acciones ejecutables del registro.
Las operaciones de modificación no se ejecutan sobre una fila finalizada. La lectura de historial y archivos permite consultar una tarea finalizada si Telcos ofrece esos botones.

## Localizadores verificados

| Lugar / operación | Control |
|---|---|
| Búsqueda por número | `#txtActividad` |
| Filtrar tabla | `#gridTareas_wrapper input[type=search]` |
| Tabla y fila exacta | `#gridTareas tbody tr`, columna **No. Tarea** (no la tarea padre ni texto de la observación) |
| Ejecutar / Reanudar | Botón de la fila con `.glyphicon-play` / `.glyphicon-step-forward` |
| Observación de ejecución | `#txtObservacionTarea` |
| Guardar ejecución **y pausa** | `#modalEjecucionTarea #btnGrabarEjecucionTarea` |
| Motivo de pausa | `#cmbMotivoPausa`, opción con valor real del catálogo |
| Ingresar seguimiento | Botón de la fila con `.glyphicon-list-alt` |
| Texto / guardar seguimiento | `#txtSeguimientoTarea` / `#btnIngresoSeguimiento` |
| Historial | Botón de la fila con `.glyphicon-search`, ventana `#modalMostrarSeguimiento` |
| Cargar archivo | Botón de la fila con `.glyphicon-open-file`, ventana `#modalCagarArchivos` |
| Elegir archivos | `input[name="archivos[]"]`, alternativa `input[type=file]` |
| Ver documentos | Botón de la fila con `.glyphicon-eye-open`, ventana `#modalVerArchivos` |
| Reasignar | Botón de la fila con `.glyphicon-dashboard`, ventana `#modalReasignarTarea` |
| Departamento / empleado | `#txtDepartment` / `#txtEmpleado`, selección exacta del autocompletado |
| Observación / guardar reasignación | `#txtaObsTareaFinalReasigna` / `#btnGrabarReasignaTarea` |
| Reprogramación, solo inspeccionada | `#modalReprogramarTarea`, `#txtDatetimepickerEjecReprogramar`, `#cmbHourEjecReprogramar`, `#txtaObsReprogramar`, `#btnGrabarReprogramarTarea` |
| Confirmaciones | `#btnSmsCustomOk`, `#btnMensajeFinTarea` |

Una consulta sin número de tarea exige seleccionar un rango de Fecha Solicitada o Fecha Estado. La búsqueda por número utilizada por el ingreso manual no pidió ese rango.

En la tarea examinada, pausa y ejecución comparten el botón Aceptar. Se conserva el localizador antiguo de pausa como alternativa para compatibilidad, pero se exige que el catálogo de pausa esté visible antes de guardar.
Todos los botones de fila operan sobre el número ya consultado; se bloquea una operación sin una tarea concreta. Los botones de cierre buscan exclusivamente Cerrar / Cancelar en ventanas conocidas.

## Datos que se pueden reutilizar

**Guardar datos de la tarea** lee la fila exacta sin pedir un selector técnico. No exige que los campos opcionales estén llenos y no modifica Telcos.

| Variable | Dato |
|---|---|
| `{numero_tarea}` | Número ingresado o importado |
| `{telcos_numero_tarea}` | Número leído en la fila |
| `{telcos_tarea}` | Nombre de tarea |
| `{telcos_estado}` | Estado al momento de la lectura |
| `{telcos_observacion}` | Observación de la fila |
| `{telcos_responsable}` | Responsable asignado |
| `{telcos_proceso}` | Nombre del proceso |
| `{telcos_cliente}` | Punto cliente |
| `{telcos_caso}` / `{telcos_tarea_padre}` | Referencias relacionadas |
| `{telcos_fecha_ejecucion}` / `{telcos_fecha_estado}` | Fechas de la fila |
| `{telcos_actualizado_por}` | Último actualizador |
| `{telcos_contacto}` / `{telcos_telefono}` | Contacto de la fila, si existe |
| `{telcos_se_factura}` / `{telcos_es_agendado}` / `{telcos_atender_antes}` | Indicadores de la fila |
| `{telcos_tiempo_transcurrido}` | Tiempo mostrado |
| `{proveedor}` / `{orden_compra}` | Datos recibidos de otro módulo, si existen |

El editor de texto permite insertar los datos más comunes mediante un desplegable. Ejemplo: `Se revisa {telcos_tarea}. Responsable: {telcos_responsable}.`
Para leer un estado actualizado tras un cambio, agregue de nuevo Guardar datos de la tarea o use Comprobar estado de la tarea. Los datos capturados quedan en el contexto y resultado del flujo. Si un texto solicita un dato vacío, la ejecución informa cuál falta; no inventa información.

## Prueba real autorizada

- Se ejecutó la tarea asignada y se registró una observación identificada como prueba.
- Se pausó con motivo **1641 — SE SOLICITA COTIZACION AL PROVEEDOR** y se verificó Pausada.
- Se reanudó con otra observación de prueba y se verificó **Aceptada**.
- Se guardó un seguimiento de prueba, confirmado por Telcos.
- Se subió `prueba_orquestador.txt` y se verificó su presencia como `prueba_orquestador_6fe817.txt` en Documentos Cargados.
- Se abrió y cerró Reasignar sin guardar ni elegir otro responsable. Se inspeccionó Reprogramar sin guardar.
- No se canceló, anuló ni finalizó la tarea. El responsable sigue siendo Jimmy Omar Toapanta Guayanay.

Fuentes visuales originales: `.test-results/telcos/`. Recortes del producto: `src/compras_tn/presentation/assets/telcos/`. No se reutilizan cookies ni credenciales del navegador en la aplicación.

## Validación local

Python 3.12.14: **41 pruebas aprobadas** en validación de flujos, UI, referencias visuales, resiliencia y controles Selenium. Incluye selección exacta entre dos tareas, Ejecutar y Reanudar, Aceptar compartido de pausa, rechazo de catálogo oculto, variables capturadas y lectura diferida en preflight.
Ruff sin errores en los archivos modificados; compilación correcta. Informe: `.test-results/actualizar-tareas.xml`. Las pruebas Selenium adicionales usan páginas sintéticas; la prueba corporativa descrita arriba se realizó aparte en el navegador del usuario.
