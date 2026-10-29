# Módulos, tiempos y capturas

[Volver a la presentación del proyecto](../README.md) · [Ver estimación mensual y supuestos](IMPACTO_OPERATIVO.md)

## El ahorro, módulo por módulo

| Módulo y volumen de referencia | Antes, de forma manual | Con GestorCompras | Tiempo recuperado |
| --- | ---: | ---: | ---: |
| Correos masivos · 10–20 destinatarios | 20–40 min para 10–20 correos | ≈10 s de envío por lote preparado | Se sustituye el armado y envío individual¹ |
| Organizador · 3–4 archivos | 6–7 min por lote | ≈2 min por lote | **4–5 min por lote** |
| Carga automática · 1 OC de 5 ítems | 4–5 min por orden | ≈2 min por orden | **2–3 min por orden** |
| Reasignación · 5 tareas | 10–15 min por lote | ≈3 min por lote | **7–12 min por lote** |
| Descargas OC · 6 órdenes | 7–8 min o más por lote | ≈3 min por lote | **4–5 min o más por lote** |
| Orquestador · 1 tarea | 4–6 min por tarea | ≈1 min por tarea | **3–5 min por tarea** |

¹ En Correos masivos, el tiempo automático corresponde al envío del lote ya preparado; la selección y revisión previas se contabilizan aparte.

*Tiempos aproximados reportados por el autor durante el uso del proyecto. Son referencias por módulo y volumen indicado; pueden variar según documentos, pasos del flujo, red y respuesta de los portales. No se suman como si correspondieran a una misma jornada.*

**El valor también está en la autonomía:** preparar un lote permite dejar al programa ejecutando el recorrido repetitivo y dedicar la atención a otra actividad. El tiempo de ejecución de una automatización no equivale necesariamente a tiempo de intervención humana. La revisión inicial, las confirmaciones y la atención a excepciones siguen formando parte del trabajo.

![Panel de navegación de GestorCompras](capturas/01-inicio.png)

> Las capturas son de la interfaz real con datos de demostración. Se ocultaron o sustituyeron correos, proveedores, RUC, responsables y rutas privadas. Las filas ilustrativas no representan transacciones realizadas al generar las imágenes.

## 1. Correos masivos · Solicitudes de despacho listas por lote

**Antes:** cada solicitud exigía redactar o adaptar un correo, colocar el asunto correcto, buscar la orden de compra y adjuntarla. La referencia manual es de **2 minutos por correo**.

**Ahora:** se utiliza una plantilla, se revisan las órdenes y sus documentos y se envía un lote de **10–20 correos**, cada uno dirigido al proveedor correspondiente. La preparación del mensaje, el asunto y el adjunto deja de repetirse manualmente para cada destinatario.

> **10–20 correos enviados en aproximadamente 10 segundos por lote**, con un proveedor distinto como destinatario de cada mensaje. El recorrido manual de ese volumen ocupaba **20–40 minutos**, a razón de 2 minutos por correo.

¹ Los 10 segundos corresponden al envío automático de un lote preparado. La selección de órdenes y la revisión inicial se realizan antes y deben contabilizarse al medir el ahorro total de una jornada.

![Correos masivos](capturas/02-correos-bienes.png)

## 2. Organizador de archivos · Del correo a la carpeta correcta

El módulo reconoce mensajes de solicitud de cotización cuyo asunto contiene la tarea. Compara el remitente con la base local para identificar al proveedor, extrae el PDF o la ficha y busca, dentro de las subcarpetas de la carpeta central configurada, la que corresponde al número de tarea.

El archivo se guarda en su destino con una etiqueta que identifica la **cotización y el proveedor**. Así se reduce el trabajo de abrir mensajes, identificar a quién pertenece un documento, renombrarlo y recorrer carpetas hasta encontrar su ubicación.

También permite seleccionar **varios archivos locales**. En esa modalidad se extrae el RUC para asociar el documento con el proveedor registrado y se revisan los datos antes de guardar.

> **Lote de 3–4 archivos:** de **6–7 minutos** de organización manual a **aproximadamente 2 minutos**. Un ahorro de **4–5 minutos por lote**.

![Organizador de cotizaciones y archivos](capturas/03-organizador-archivos.png)

## 3. Carga automática de OC · De Google Sheets al portal

Toma de una hoja de Google Sheets los datos necesarios para preparar la orden: **artículos, cantidades, precios, proveedor y solicitante**. Valida la información y realiza la carga en el portal de órdenes de compra.

El número de OC y los datos de quienes deben autorizarla se registran en la hoja para facilitar los seguimientos. La información se mantiene vinculada a la tarea y a los artículos de origen.

> **Una OC con 5 ítems:** de **4–5 minutos** de captura manual a **aproximadamente 2 minutos** de ejecución automática. Entre **2 y 3 minutos menos por orden**.

Su mayor aporte es poder dejar **varias órdenes preparadas en un lote** y continuar con otra función mientras el programa las procesa. Se reducen tanto la transcripción entre sistemas como la necesidad de acompañar cada campo y cada clic.

![Carga automática de órdenes de compra](capturas/04-carga-oc-automatica.png)

## 4. Reasignación · Compras completas que avanzan sin repetir el recorrido

Detecta correos que informan que una tarea de compras está completa. A partir de ellos prepara la reasignación en el portal corporativo de gestión de tareas: completa **número de factura, número de ingreso y observaciones**, y utiliza el departamento y usuario configurados como destino.

El usuario revisa el lote y la automatización ejecuta el recorrido que antes debía repetirse para cada tarea.

> **Cinco tareas:** de **10–15 minutos** de reasignación manual a **aproximadamente 3 minutos por lote**. Entre **7 y 12 minutos recuperados**.

![Reasignación por lotes](capturas/06-reasignacion-bienes.png)

### Una automatización que se complementa con otra

Los correos de tareas completas se complementan con [Notificacion-automatica-tareas](https://github.com/eslay07/Notificacion-automatica-tareas), un proyecto del mismo autor en Google Apps Script. Ese sistema revisa las entregas registradas en Google Sheets, detecta tareas completas y envía su notificación. GestorCompras utiliza ese aviso como entrada para el proceso de reasignación.

```mermaid
flowchart LR
    A[Entregas registradas en Google Sheets] --> B[Notificación de tarea completa]
    B --> C[Escaneo y revisión en GestorCompras]
    C --> D[Reasignación por lote en el portal]
```

## 5. Descargas OC · Descargar, identificar y organizar en un mismo flujo

El escaneo de correo detecta las confirmaciones de órdenes aprobadas y extrae los datos necesarios para descargarlas. El programa abre el portal de órdenes de compra, descarga los documentos uno a uno dentro del lote y los organiza en la carpeta o subcarpeta configurada, utilizando la **tarea y el proveedor** para identificar el archivo y su destino.

También puede ejecutarse **sin escaneo de correo**: basta ingresar un lote de números de OC y revisar la selección.

> **Seis órdenes:** de **7–8 minutos o más** —incluyendo descarga, cambio de nombre y ubicación— a **aproximadamente 3 minutos por lote**. Al menos **4–5 minutos menos** en el rango de referencia.

![Descargas de órdenes](capturas/07-descargas-bienes.png)

### El volumen mensual le da valor a cada lote

El autor sitúa la carga de trabajo en unas **80 órdenes mensuales de Bienes** y unas **300 de Servicios**. Son volúmenes de referencia de la actividad, no una afirmación de que ambos flujos estén automatizados en esta versión.

Aplicando proporcionalmente los tiempos anteriores a **80 órdenes de Bienes**, la descarga y organización pasan de **aproximadamente 93–107 minutos a 40 minutos al mes**: **unos 53–67 minutos recuperados solo en este módulo**. Este cálculo no suma los ahorros de correos, cotizaciones, carga de OC ni tareas. El volumen de Servicios representa una oportunidad futura mientras ese módulo continúa en desarrollo.

<details>
<summary>Abastecimiento y cola de subidas</summary>

La modalidad Abastecimiento incorpora filtros para preparar la descarga. La cola de subidas permite revisar estados y recuperar transferencias pendientes.

![Abastecimiento](capturas/07-descargas-bienes-abastecimiento.png)

![Cola de subidas](capturas/07-descargas-bienes-telcodrive-subidas.png)

</details>

## 6. Orquestador · Un constructor de flujos para el portal de tareas

Su idea se parece a la de un constructor de automatizaciones como **n8n**, enfocada al portal corporativo de tareas: combinar pasos para registrar seguimientos, escribir observaciones, subir archivos y mantener el historial de una compra.

El editor visual permite preparar y guardar una secuencia para reutilizarla. Después se aplica a un lote de tareas, en segundo plano, con revisión de resultados por elemento.

> **Una tarea:** de **4–6 minutos** de acciones manuales a **aproximadamente 1 minuto** de ejecución del flujo. Entre **3 y 5 minutos menos por tarea**, con ejecución por lotes y en segundo plano.

El beneficio crece cuando el mismo procedimiento debe repetirse muchas veces: se configura el recorrido y se reutiliza, en lugar de reproducir manualmente cada acción en cada tarea.

![Ejecución de flujos por lote](capturas/08-orquestador-bienes.png)

![Constructor visual de flujos](capturas/08-orquestador-bienes-editor-visual.png)

![Alias para localizar archivos](capturas/08-orquestador-bienes-alias-de-archivos.png)

## Herramientas que completan el recorrido

### Seguimientos

Prepara la comunicación de seguimiento de las órdenes mediante selección y plantillas. Complementa la información registrada durante la carga y el control de las compras.

![Seguimientos](capturas/05-seguimientos.png)

### Configuración centralizada

Reúne el catálogo de proveedores, sus datos de identificación, las asignaciones, las plantillas y las opciones de integración. Esta base permite asociar correctamente los correos y documentos con cada proveedor, sin publicar el catálogo real en el repositorio.

![Configuración con datos ocultos](capturas/13-configuracion.png)

<details>
<summary>Ver asignaciones, plantillas y opciones por módulo</summary>

![Asignaciones](capturas/13-configuracion-asignaciones.png)

![Plantillas](capturas/13-configuracion-plantillas.png)

![Opciones e integraciones](capturas/13-configuracion-opciones-por-modulo.png)

</details>

### Acceso y trabajo en segundo plano

Tras preparar la selección y confirmar la operación, los procesos pueden trabajar en segundo plano para reducir la atención paso a paso. El usuario conserva la revisión de los resultados y puede atender otras actividades mientras se ejecuta el lote.

![Acceso](capturas/00-acceso.png)

## Estado de Servicios · Interfaz en desarrollo

**Servicios todavía no es funcional como un flujo completo.** Sus pantallas son una copia de la estructura de Bienes y se conservan como base para la implementación. Los tiempos y resultados operativos descritos arriba no deben interpretarse como una validación de Servicios.

<details>
<summary>Ver las pantallas preliminares de Servicios</summary>

Estas capturas muestran la estructura de la interfaz, no módulos terminados.

![Correos de Servicios — preliminar](capturas/09-correos-servicios.png)

![Reasignación de Servicios — preliminar](capturas/10-reasignacion-servicios.png)

![Descargas de Servicios — preliminar](capturas/11-descargas-servicios.png)

![Abastecimiento de Servicios — preliminar](capturas/11-descargas-servicios-abastecimiento.png)

![Subidas de Servicios — preliminar](capturas/11-descargas-servicios-telcodrive-subidas.png)

![Orquestador de Servicios — preliminar](capturas/12-orquestador-servicios.png)

![Editor de Servicios — preliminar](capturas/12-orquestador-servicios-editor-visual.png)

![Alias de Servicios — preliminar](capturas/12-orquestador-servicios-alias-de-archivos.png)

</details>

