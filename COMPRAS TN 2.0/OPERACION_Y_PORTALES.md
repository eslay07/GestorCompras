# Operación y validación de Compras TN 2.0

## Mapa contrastado con las pantallas corporativas

| Sistema | Acceso y navegación | Condición de avance |
|---|---|---|
| Telcos | JOSSO en `idp.telconet.net` → Inicio → Tareas personales (`/soporte/tareas/`) | Campo `txtActividad`, consulta actual terminada y coincidencia en columna No. Tarea |
| Telcos | Fila → ejecución, seguimiento, archivos o reasignación | Acción disponible para el estado; formulario correcto y confirmación después de guardar |
| NAF | CAS en `cas.telconet.ec` → `/naf/compras/dashboard` → Consultas → Consulta de Órdenes de Compra | Puede redirigir a selección de compañía aunque Consultas sea visible |
| NAF | Selección de compañía → TELCONET S.A. (código observado 10) → Elegir → OK | Recarga y formulario `/naf/compras/movimientos/orden-compra` |
| NAF | N° Orden o filtros de abastecimiento → Aplicar filtros → descarga de la fila exacta | Respuesta actual, PDF terminado y legible; error de portal separado de fallo de red |
| Telcodrive | Correo completo → Archivos → Mi Biblioteca → BD_TN → mes → tarea | Biblioteca accesible con escritura y raíz válida |

Observaciones de la inspección: Telcos mantiene filas anteriores mientras consulta y duplica encabezados visuales. La tarea 153455125 estaba finalizada y ofrecía consultas de seguimiento y archivos. NAF contiene tablas secundarias dentro del listado; sus filas no son órdenes. Telcodrive contiene meses en mayúsculas y carpetas `número - descripción`, además de carpetas auxiliares sin número.

## Configuración de Telcodrive

En Configuración revise URL `https://telcodrive.telconet.net`, biblioteca `` y raíz `/BD_TN`. El UUID corresponde a Mi Biblioteca de la sesión inspeccionada; otra cuenta debe usar una biblioteca a la que tenga acceso. Guarde y use **Probar Seafile**: valida autenticación, biblioteca y listado de la raíz, sin subir archivos.

La aplicación conserva el PDF local. Busca la tarea en todos los meses. Si falta, crea la carpeta con **solo el número**, bajo el mes actual de Ecuador. No modifica carpetas ni cotizaciones existentes. Si hay varias coincidencias, requiere elegir un destino en **Descargas OC → Telcodrive · Subidas → Resolver tarea/destino**.

Estados: `pending` requiere reintento o revisión del detalle; `review` requiere corregir el número de tarea; `conflict` requiere seleccionar carpeta; `uploading` indica una operación iniciada; `uploaded` e `identical` indican contenido verificado. Una operación interrumpida se revisa antes de volver a subir. **Reintentar pendientes** no abre NAF ni descarga nuevamente.

Un archivo remoto de igual nombre y contenido distinto permanece intacto. Revíselo en Telcodrive antes de reintentar. Si el archivo local cambió después de prepararse, la cola bloquea su envío. Las credenciales no se guardan en la cola; el token se libera al terminar cada lote.

API usada: bibliotecas `/api2/repos/`, directorios `dir/`, enlace `upload-link/` y lectura `file/`. La carga usa `replace=0`, `ret-json=1` y verificación SHA-256 del contenido descargado. Referencia oficial: [File Upload](https://cloud.seafile.com/published/web-api/v2.1/file-upload.md). La compatibilidad exacta del servidor debe confirmarse en el piloto.

## Actualizar Tareas

1. En Editor visual elija un proceso y pulse **Crear con guía**.
2. Complete los parámetros, revise los pasos y guarde el flujo. Puede editarlo con el registro avanzado.
3. En Ejecutar seleccione tareas y el flujo. Revise el resumen de acciones antes de confirmar.
4. Observe el paso actual y el tiempo transcurrido. Cancelar interrumpe las esperas cooperativas; una petición ya enviada puede terminar antes de detenerse.
5. Revise resultados por tarea. No repita a ciegas un flujo que falló después de guardar, subir o reasignar.

Use rutas o alias explícitos cuando una tarea tenga varios PDFs. La aplicación ya no elige arbitrariamente el más reciente. La confirmación de lectura de una tarea no demuestra que todos sus cambios sean posibles: depende del estado y los permisos del usuario.

## Matriz de comparación y aceptación

| Módulo | Referencia conservada | Verificación requerida |
|---|---|---|
| Descargas normal y abastecimiento | infrastructure/automation/downloads.py | Selección de compañía, nombres, filtros, paginación, rechazo, interrupción y recuperación |
| Actualizar tareas | infrastructure/automation/telcos.py | Acciones, orden, parámetros, archivos, estados y resultados parciales |
| Reasignación Bienes/Servicios | infrastructure/automation/telcos.py | Departamento, empleado, observación y ausencia de repetición |
| Correos masivos y seguimientos | application/services.py | Destinatarios, CC independientes, plantillas, adjuntos y grupos por proveedor |
| Configuración y migración | Datos heredados en lectura | Proveedores, asignaciones, flujos y exclusión de secretos |
| Persistencia | Base 2.0 existente | Migración, respaldo SQLite incluyendo WAL y recuperación de subidas |

La matriz indica qué se debe comparar; no certifica por sí sola un piloto ni equivalencia total. Los tests de servicios, migración y contratos cubren comportamiento local sin enviar correos.

## Piloto y reversión

Antes de producción: elegir una OC descargable y una tarea activa de prueba, registrar estado y archivo iniciales, ejecutar por separado descarga, subida y una acción concreta de Telcos, comprobar resultado desde los portales, repetir la subida para confirmar que se omite el contenido idéntico y probar una interrupción controlada. Validar Bienes y Servicios. No usar tareas finalizadas para probar mutaciones.

Los tests `live` requieren credenciales y acceso corporativo. No ejecutarlos como parte de la suite local ni enviar reportes/correos de prueba sin destinatarios autorizados.

Antes de una migración pendiente, se crea `compras_tn.db.FECHA.bak` mediante la API de respaldo SQLite. No se genera copia en cada arranque si el esquema ya está actualizado. Para revertir: cerrar la aplicación y sus procesos; preservar la base fallida; restaurar el respaldo en una carpeta limpia junto con la versión de código correspondiente, evitando reutilizar archivos WAL/SHM de otra base.

**No declarar esta entrega lista para producción hasta completar el piloto corporativo.**
