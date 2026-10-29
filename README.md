# COMPRAS TN

Aplicación de escritorio para gestionar Compras Bienes y Compras Servicios desde una sola ventana. Integra correo, documentos, órdenes de compra, tareas y automatización de portales mediante una interfaz en Python y PySide6.

**Autor y mantenimiento:** Jimmy Toapanta · [eslay07](https://github.com/eslay07)

![Panel principal de COMPRAS TN](docs/capturas/01-inicio.png)

> Las capturas muestran la interfaz real con una base temporal y datos de demostración. Los proveedores, RUC, correos, responsables y rutas privadas están ocultos o sustituidos. No se conectó a buzones ni portales corporativos para generarlas. Las filas ilustrativas no representan transacciones ejecutadas.

## Módulos disponibles

| Área | Módulo | Función |
| --- | --- | --- |
| General | Acceso e inicio | Sesión corporativa, navegación y ubicación de datos |
| Bienes y Servicios | Correos masivos | Revisión de OC, PDF, destinatarios y plantillas antes del envío |
| Bienes | Organizador de archivos | Escaneo de adjuntos o selección local, identificación y guardado por tarea |
| Bienes | Carga de OC automática | Lectura de Google Sheets, agrupación, validación y carga controlada en NAF |
| Bienes | Seguimientos | Selección de OC y envío de seguimiento con plantilla |
| Bienes y Servicios | Reasignación | Búsqueda de tareas, validación de destino y reasignación en Telcos |
| Bienes y Servicios | Descargas OC | Descarga manual, escaneo de correo y modalidad Abastecimiento |
| Bienes y Servicios | Cola de subidas | Transferencias persistentes, estados y recuperación de pendientes |
| Bienes y Servicios | Orquestador Telcos | Bandeja de tareas, ejecución por lotes, editor visual y alias de archivos |
| Sistema | Configuración | Proveedores, asignaciones, plantillas e integraciones por módulo |

## Capturas y funcionamiento

### Acceso

El acceso inicia una sesión de trabajo. La contraseña permanece en memoria y se descarta al cerrar sesión.

![Acceso](docs/capturas/00-acceso.png)

### Correos masivos

Permite ingresar órdenes, revisar los documentos y confirmar los destinatarios antes del envío. Bienes y Servicios disponen de su propio acceso desde la barra lateral.

![Correos masivos de Bienes](docs/capturas/02-correos-bienes.png)

<details>
<summary>Ver Correos masivos de Servicios</summary>

![Correos masivos de Servicios](docs/capturas/09-correos-servicios.png)

</details>

### Organizador de archivos

Busca adjuntos por fechas o tareas y admite archivos locales. La revisión permite identificar el tipo de documento y su destino antes de guardar los seleccionados.

![Organizador de archivos](docs/capturas/03-organizador-archivos.png)

### Carga automática de OC

Lee la hoja configurada, consolida artículos y agrupa las órdenes por proveedor, departamento y solicitante. Las validaciones y la selección previa permiten revisar qué se enviará al portal. Incluye recuperación de operaciones pendientes para evitar repetir una creación incierta.

![Carga automática de OC](docs/capturas/04-carga-oc-automatica.png)

### Seguimientos

Organiza las órdenes que requieren seguimiento y permite preparar su comunicación mediante una plantilla.

![Seguimientos](docs/capturas/05-seguimientos.png)

### Reasignación de tareas

Presenta las tareas encontradas y los campos de destino antes de ejecutar la reasignación. Los flujos de Bienes y Servicios comparten controles de validación y reporte.

![Reasignación de Bienes](docs/capturas/06-reasignacion-bienes.png)

<details>
<summary>Ver Reasignación de Servicios</summary>

![Reasignación de Servicios](docs/capturas/10-reasignacion-servicios.png)

</details>

### Descargas OC y Abastecimiento

La modalidad normal acepta órdenes manuales o detectadas desde correo. Abastecimiento incorpora filtros por fechas y responsables. La cola de transferencias mantiene los pendientes de subida y sus estados.

![Descargas OC de Bienes](docs/capturas/07-descargas-bienes.png)

![Abastecimiento](docs/capturas/07-descargas-bienes-abastecimiento.png)

![Cola de subidas](docs/capturas/07-descargas-bienes-telcodrive-subidas.png)

<details>
<summary>Ver Descargas, Abastecimiento y Subidas de Servicios</summary>

![Descargas OC de Servicios](docs/capturas/11-descargas-servicios.png)

![Abastecimiento de Servicios](docs/capturas/11-descargas-servicios-abastecimiento.png)

![Subidas de Servicios](docs/capturas/11-descargas-servicios-telcodrive-subidas.png)

</details>

### Orquestador Telcos

Reúne las tareas de distintos orígenes, elimina duplicados y permite ejecutar un flujo guardado. El editor visual muestra cada acción y sus parámetros; los alias relacionan tipos de documento y archivos. La política del flujo controla cómo continuar ante fallos.

![Ejecución del orquestador](docs/capturas/08-orquestador-bienes.png)

![Editor visual](docs/capturas/08-orquestador-bienes-editor-visual.png)

![Alias de archivos](docs/capturas/08-orquestador-bienes-alias-de-archivos.png)

<details>
<summary>Ver el Orquestador de Servicios</summary>

![Ejecución de Servicios](docs/capturas/12-orquestador-servicios.png)

![Editor de Servicios](docs/capturas/12-orquestador-servicios-editor-visual.png)

![Alias de Servicios](docs/capturas/12-orquestador-servicios-alias-de-archivos.png)

</details>

### Configuración

Centraliza los catálogos de proveedores, asignaciones, plantillas HTML y opciones de los módulos. Cada instalación debe registrar sus propias credenciales, rutas e identificadores privados.

![Configuración y proveedores ocultos](docs/capturas/13-configuracion.png)

<details>
<summary>Ver asignaciones, plantillas y opciones por módulo</summary>

![Asignaciones](docs/capturas/13-configuracion-asignaciones.png)

![Plantillas](docs/capturas/13-configuracion-plantillas.png)

![Integraciones por módulo](docs/capturas/13-configuracion-opciones-por-modulo.png)

</details>

## Instalación desde el código

Se requiere **Windows de 64 bits y Python 3.12 o 3.13**. Use un entorno en una ruta corta para evitar el límite de longitud de rutas de Windows al instalar PySide6.

Desde la raíz del repositorio, en PowerShell:

```powershell
py -3.12 -m venv "$env:USERPROFILE\.venvs\compras-tn"
& "$env:USERPROFILE\.venvs\compras-tn\Scripts\python.exe" -m pip install -r requirements.txt
& "$env:USERPROFILE\.venvs\compras-tn\Scripts\python.exe" -m pip install -e ".\COMPRAS TN 2.0"
& "$env:USERPROFILE\.venvs\compras-tn\Scripts\python.exe" run.py
```

Para Python 3.13, cambie `py -3.12` por `py -3.13`. También puede usar `COMPRAS TN 2.0/COMPRAS 3.0.pyw`, que conserva su nombre por compatibilidad con el acceso por doble clic. La versión declarada del paquete es 2.0.0.

## Instalador sin conexión

El instalador selecciona las ruedas compatibles con Python 3.12 o 3.13 ya instalado, crea una carpeta de librerías aislada y verifica las dependencias directas y transitivas. Antes de activar una actualización comprueba el arranque completo de la interfaz y el navegador, respalda la base existente y conserva las configuraciones.

Use únicamente un paquete completo de [Releases](https://github.com/eslay07/GestorCompras/releases), extraiga todo su contenido y ejecute `instalar.py`. Las compilaciones públicas incluyen un perfil vacío: no distribuyen catálogos de proveedores ni datos corporativos. Consulte [las instrucciones del instalador](INSTALAR_PYTHON313.md).

## Configuración inicial

1. Abra **Configuración** y registre proveedores, asignaciones y plantillas.
2. Configure el correo y las rutas de documentos de su instalación.
3. Para Google Sheets, registre su propio ID de documento y archivo de credenciales; no los agregue al repositorio.
4. Configure el portal y el almacenamiento remoto autorizados por su organización.
5. Revise los datos y use las confirmaciones de cada módulo antes de ejecutar una operación real.

Los identificadores privados de documentos y repositorios de almacenamiento no forman parte de los valores predeterminados de esta edición pública.

## Datos y privacidad

- La base de trabajo se guarda fuera del código, en la carpeta local de COMPRAS TN; puede seleccionarse mediante `COMPRAS_TN_DATA_DIR`.
- El repositorio no incluye bases de producción, credenciales JSON, contraseñas, adjuntos, buzones ni perfiles privados del instalador.
- Las capturas de esta documentación se generaron con datos sintéticos. Las imágenes históricas y la base antigua se retiraron del historial publicable.
- La aplicación no descarga ni sustituye el Python aprobado de la organización y no modifica las políticas del equipo.
- Los errores de lanzamiento quedan registrados para facilitar la reparación del entorno.

## Desarrollo y pruebas

```powershell
cd "COMPRAS TN 2.0"
& "$env:USERPROFILE\.venvs\compras-tn\Scripts\python.exe" -m pytest -m "not live"
```

Las pruebas reales contra servicios corporativos se mantienen fuera de la ejecución predeterminada. Las pruebas automáticas no sustituyen la validación de accesos y permisos en cada organización.

## Estructura

```text
COMPRAS TN 2.0/
  src/compras_tn/
    application/       Casos de uso, validaciones y flujos
    domain/            Modelos y reglas
    infrastructure/    Persistencia, correo, documentos y automatización
    presentation/      Interfaz PySide6
  alembic/             Evolución del esquema
  tests/               Pruebas automáticas
  tools/installer/     Instalación, actualización y diagnóstico
  requirements.lock    Versiones de dependencias
  pyproject.toml       Configuración del paquete
  launch.py            Selección del entorno de ejecución
docs/capturas/         Capturas públicas de demostración
run.py                 Inicio desde la raíz
instalar.py            Entrada del instalador completo
```

Documentación técnica: [manual del proyecto](COMPRAS%20TN%202.0/README.md), [operación y portales](COMPRAS%20TN%202.0/OPERACION_Y_PORTALES.md) y [organización de documentos](COMPRAS%20TN%202.0/COTIZACIONES_Y_ADJUNTOS.md).

## Actualización publicada por tramos

Los commits de esta actualización separan la retirada de la versión original, la aplicación actual con sus nuevos módulos, la reparación del entorno e instalador y la documentación visual. La autoría de los commits nuevos corresponde a Jimmy Toapanta.

## Licencia

Consulte [LICENSE.txt](LICENSE.txt).
