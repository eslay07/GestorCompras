# OC agrupadas, reportes y origen de tareas

## Cambios implementados

- Una OC por RUC + departamento + solicitante exactos. Se quitan solo espacios exteriores de los dos últimos campos.
- Se suman cantidades por código, manteniendo cada contribución original. Precios unitarios distintos para el mismo código bloquean la OC entera con evidencia de tareas y filas.
- La tabla muestra todas las tareas y el departamento. Doble clic abre artículos consolidados, filas originales y observaciones por tarea.
- Las observaciones conservan el detalle original de cada tarea y se separan por salto de línea. Un límite declarado por NAF bloquea, sin truncar; la verificación del valor escrito permanece obligatoria antes de Guardar.
- El número confirmado se escribe y verifica en todas las filas originales. Se mantienen Guardar sin visto, registro persistente y bloqueo de regeneración ante resultados ambiguos.
- Se corrigió la verificación posterior de gspread: la librería puede convertir `G7449` en `'GENERAL'!G7449` dentro del lote; el programa conserva una copia A1 sin calificar para no producir `'GENERAL'!'GENERAL'!G7449`.
- Descargas OC y los demás accesos NAF reconocen «No se pudo validar la sesión / ¿Volver a intentar?» y pulsan Sí hasta dos veces. Descargas ocultas reintentan el acceso una vez adicional; un rechazo explícito de credenciales no se repite.
- Los reportes de procesos van como tablas HTML/texto en el correo sin Excel adjunto. Descargas OC y correos comerciales mantienen su comportamiento; la auditoría Excel permanece local.
- Actualizar tareas incorpora el origen Carga de OC automática y el botón Actualizar origen OC. Cada tarea espera todos sus artículos completos, de todos sus proveedores, y la sincronización de sus OC. Las tareas de una OC compartida se evalúan individualmente.
- El panel Ingreso manual admite una tarea por renglón, comas o punto y coma; conserva ceros iniciales, elimina duplicados y rechaza entradas inválidas sin agregar parcialmente.

## Persistencia y compatibilidad

`PurchaseOrderDraft.sources` conserva los borradores originales; `articles` contiene las líneas para NAF. Un registro antiguo sin `sources` se interpreta como una única tarea. No se modifican las filas originales al consolidar cantidades.

El repositorio existente guarda los registros de OC y sus candidatos de tareas en una transacción de ajustes. El nuevo espacio `oc_task_candidates` se llena únicamente cuando esta versión completa una sincronización: no importa registros antiguos ya finalizados. Las tareas bloqueadas utilizan el estado `waiting_oc` en la bandeja existente; no se necesita migración de esquema. Las consumidas o descartadas no se reabren al reconciliar.

La recuperación revisa también OC pendientes aunque G ya haya quedado escrita en todas sus filas. La columna G es la única autoridad para la detección: G llena excluye la fila y G vacía la mantiene elegible, sin bloquearla por registros locales antiguos.

## Verificación

Suite completa: 148 pruebas aprobadas y 4 integraciones corporativas omitidas. Ruff sin incidencias y mypy sin incidencias en 48 archivos según la configuración del proyecto. Se incluyeron pruebas de agrupación, precio conflictivo, observaciones, origen por tarea, lectura fallida, recuperación, revalidación antes de Telcos, correo sin Excel y panel manual.

Pruebas realizadas con datos aislados y correo simulado, Python 3.12.14 y PySide6 6.11.2. No se guardaron OC ni reasignaciones reales para esta implementación. Cerrar y volver a abrir la aplicación para cargar los cambios; usar el entorno Python 3.12 documentado en README. No operar cargas simultáneas desde distintos equipos: los registros de seguridad son locales, no bloqueos distribuidos.
