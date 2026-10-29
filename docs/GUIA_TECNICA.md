# Instalación y referencia técnica

[Volver a la presentación del proyecto](../README.md)

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

Use únicamente un paquete completo de [Releases](https://github.com/eslay07/GestorCompras/releases), extraiga todo su contenido y ejecute `instalar.py`. Las compilaciones públicas incluyen un perfil vacío: no distribuyen catálogos de proveedores ni datos corporativos. Consulte [las instrucciones del instalador](../INSTALAR_PYTHON313.md).

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

Documentación técnica: [manual del proyecto](../COMPRAS%20TN%202.0/README.md), [operación y portales](../COMPRAS%20TN%202.0/OPERACION_Y_PORTALES.md) y [organización de documentos](../COMPRAS%20TN%202.0/COTIZACIONES_Y_ADJUNTOS.md).

