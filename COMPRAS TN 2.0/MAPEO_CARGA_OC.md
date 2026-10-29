# Carga automática de órdenes de compra

La edición pública documenta los campos y las validaciones sin publicar registros operativos.

| Campo | Fuente |
| --- | --- |
| Proveedor y RUC | Catálogo local y sobrenombre de la hoja configurada |
| Solicitante | Nombre canónico de la hoja, validado en el portal |
| Departamento | Columna configurada de la hoja |
| Artículo, cantidad y precio | Líneas elegibles de la orden |
| Observación | Resumen de la tarea y sus artículos |
| Número de OC | Confirmación posterior al guardado |

Solo se cargan las órdenes seleccionadas. La aplicación vuelve a validar las filas antes de escribir el número de OC en la hoja, conserva los guardados pendientes y evita repetir una creación cuando el resultado es incierto.

Los nombres reales, documentos, tareas, importes y resultados de operaciones internas se mantienen fuera de la documentación pública. Configure las credenciales e identificadores de su organización desde la aplicación.
