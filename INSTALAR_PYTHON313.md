# InstalaciÃ³n con Python de Microsoft Store

1. Use **Python 3.12 o 3.13 de 64 bits**. En equipos corporativos, instale el Python aprobado de Microsoft Store.
2. Copie `Instalador_Python313.zip` a la nueva computadora y **extraiga todo**. No ejecute el archivo dentro del ZIP.
3. Abra `instalar.py` con Python 3.12 o 3.13. TambiÃ©n puede abrir una terminal en la carpeta extraÃ­da y escribir `python instalar.py`.
4. Cierre COMPRAS TN y pulse **Instalar / actualizar**. Si tiene una versiÃ³n muy antigua, seleccione su carpeta en el campo opcional.
5. Espere **INSTALADO CORRECTAMENTE**. La ventana permanece abierta y muestra el paso y el error exacto si falla. Puede volver a intentar.

`instalar.py` necesita la carpeta `instalar_datos` que viene en el ZIP: no copie Ãºnicamente el script. Incluye las librerÃ­as para Python 3.13, la aplicaciÃ³n y el perfil de proveedores/configuraciones. No necesita descargar librerÃ­as ni instalar otro Python, modificar PATH o pedir administrador.

El instalador conserva los proveedores y configuraciones del equipo, agrega los faltantes y crea un respaldo antes de actualizar. El perfil de migraciÃ³n conserva los correos de proveedores, pero excluye contraseÃ±as, credenciales de Google, mensajes e historial del buzÃ³n. En un equipo nuevo debe ingresar sus claves y revisar las rutas.

Para llevar mejoras a una PC que ya tiene el programa, copie el **ZIP completo mÃ¡s reciente**, extrÃ¡igalo en una carpeta nueva, cierre el programa y ejecute `instalar.py` otra vez. El mismo botÃ³n **Instalar / actualizar** aplica la versiÃ³n incluida en ese paquete sin reemplazar los ajustes ni proveedores locales. No basta copiar solo el archivo `.py`. Este instalador transporta la versiÃ³n empaquetada; no descarga automÃ¡ticamente cambios futuros.

DespuÃ©s de instalar, abra **COMPRAS TN** desde el acceso directo. Si no pudo crearse, ejecute `abrir.py` en la carpeta del programa indicada en el registro.

Esta variante ejecuta el Python 3.12 o 3.13 ya instalado y aprobado en el equipo; no utiliza `instalador.exe` ni un Python descargado. La automatizaciÃ³n de Telcos necesita ejecutar Chrome y ChromeDriver. Si las polÃ­ticas del equipo tambiÃ©n bloquean esos componentes, la comprobaciÃ³n mostrarÃ¡ el error; el script no elude las polÃ­ticas de la empresa.

El instalador verifica todas las dependencias transitivas, abre la ventana principal con datos temporales y comprueba Chrome y ChromeDriver antes de activar la actualización. Los errores de lanzamiento se registran en `startup.log` dentro de la carpeta del programa. El lanzador `COMPRAS 3.0.pyw` también detecta el entorno de la instalación.
