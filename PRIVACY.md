# Privacidad

GestorCompras es una demostración de portafolio que utiliza exclusivamente datos sintéticos incluidos en el repositorio. La aplicación no necesita ni solicita información personal, credenciales, sesiones de usuario o registros de producción.

## Datos incluidos

Los nombres, correos, identificadores, órdenes, tareas y documentos visibles son ficticios. Los correos pertenecen únicamente a `example.com`, los identificadores numéricos usan `0000000000000` y la ruta `C:\Demo\GestorCompras\pdfs` es una representación visual que no se crea en el equipo.

## Aislamiento

- El modo demostración es obligatorio.
- Los adaptadores de correo, tareas y almacenamiento operan en memoria.
- No se realizan conexiones de red ni automatizaciones de navegador.
- No se incluye una base de datos y no se persisten operaciones.
- Las descargas y entregas de correo son simulaciones visibles en la interfaz.

## Control preventivo

`scripts\privacy_check.py` revisa nombres, rutas y archivos de texto. El control rechaza artefactos de datos, rutas locales no sintéticas, correos fuera de `example.com`, URLs no revisadas, identificadores numéricos no permitidos y posibles secretos. Debe ejecutarse antes de publicar cualquier cambio.
