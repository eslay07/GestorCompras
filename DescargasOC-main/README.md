# DescargasOC

Este proyecto es un piloto para una automatización de descarga de ordenes de
compra desde una aplicación web a un almacenamiento en la nube.

## Requisitos

- **Python ≥ 3.8.** Los scripts hacen uso de `f-strings` y bibliotecas como
  `tkinter`, `PyPDF2` y `selenium`.

## Configuración inicial

El archivo de configuración `config.json` se genera ejecutando:

```bash
python -m descargas_oc.configurador
```

Se abrirá una pequeña ventana donde se solicitan:

1. Usuario y contraseña del correo.
2. Carpeta destino donde se almacenarán los PDF detectados.
3. Carpeta a analizar (de donde se leerán los PDF descargados).
4. Correo para enviar el reporte final.

Al pulsar **Guardar configuración**, la información se guarda en
`data/config.json`. Este archivo es leído por el resto de scripts.

## Uso de los scripts

### Interfaz

La interfaz gráfica permite activar el escuchador, ejecutar un escaneo inmediato y abrir la
ventana de configuración. Un contador indica el tiempo restante para el siguiente ciclo de
escaneo. El campo *Intervalo* permite cambiar en caliente el valor `scan_interval` que
se almacena en `data/config.json`. Puede ejecutarse con:

```bash
python -m descargas_oc.ui
```

### descargas_oc.escuchador

Escanea cada 5 minutos la cuenta de correo configurada mediante POP3 en busca
de mensajes que notifiquen Órdenes de Compra. Cuenta cuántas hay en la bandeja
y extrae de cada una el **número** y las fechas de autorización y emisión. La
información se envía a `descargas_oc.selenium_modulo.descargar_oc()` para procesar todas las
órdenes encontradas.
Ejecutar con:

```bash
python -m descargas_oc.escuchador
```

### descargas_oc.mover_pdf

Revisa la carpeta configurada como origen en `config.json` y mueve al destino
los PDF que contengan la cadena "ORDEN DE COMPRA" en su texto. Puede ejecutarse
de forma independiente:

```bash
python -m descargas_oc.mover_pdf
```

### descargas_oc.selenium_modulo

Recibe el número y las fechas de la OC detectada por `descargas_oc.escuchador` y realiza
una automatización básica con Selenium. Al finalizar, ejecuta
`descargas_oc.mover_pdf.mover_oc()` para procesar los PDF. Se puede lanzar con:

```bash
python -m descargas_oc.selenium_modulo
```

### scripts/seadrive_autoresync.py

Antes de iniciar la automatización con Selenium, el módulo ejecuta
`scripts/seadrive_autoresync.py` para forzar la sincronización de SeaDrive en
Windows. El script también puede ejecutarse de forma independiente:

```bash
python scripts/seadrive_autoresync.py
```

---
Para todos los scripts se asume que `config.json` ya ha sido creado mediante el
`descargas_oc.configurador`.

## Configuración

El archivo de configuración (`config.json`) ahora incluye campos adicionales para permitir la subida de archivos a un servidor **Seafile** y el envío de reportes:

```
seafile_url           # URL base del servidor Seafile
seafile_repo_id       # ID de la biblioteca en Seafile
seafile_subfolder    # Carpeta dentro del repo donde se subirán los archivos
pop_server           # Servidor POP3 para leer los correos
pop_port             # Puerto del servidor POP3 (por defecto 995)
carpeta_destino_local # Ruta local donde Selenium guardará los archivos
correo_reporte        # Dirección donde se enviará el reporte
```

En la ventana de configuración hay un botón **Generar archivo de procesados**
que escanea todos los mensajes existentes en el servidor de correo y crea el
archivo `procesados.txt`. De esta forma los correos antiguos no se volverán a

analizar al iniciar el escuchador. Además, el escuchador guarda el identificador
UIDL del mensaje más reciente en `last_uidl.txt` y en las siguientes ejecuciones
detiene la búsqueda cuando encuentra ese UIDL, evitando recorrer todo el buzón
cada vez.


Al guardar la configuración se solicitará un archivo de prueba y se subirá a
Seafile para comprobar las credenciales. El cliente de Seafile inicia sesión con
el `usuario` y la `contraseña` para obtener un *auth-token* de sesión utilizado
en todas las peticiones.

`seafile_repo_id` se utiliza como identificador de la biblioteca en Seafile. Introduce únicamente el ID (por ejemplo `ede837d2-5de8-45f8-802d-aa513aaad8b2`), **no** una ruta local.

Al abrir `descargas_oc.configurador` los valores previamente guardados aparecerán en las cajas de texto, por lo que es posible revisar o corregir la configuración sin tener que introducirla de nuevo cada vez.
Antes de guardar, se solicitará seleccionar un archivo de prueba que se subirá a Seafile usando la información ingresada. Si la subida se realiza con éxito, la configuración se guarda.
Si vienes de una versión anterior donde solo existía `carpeta_destino`, ejecuta nuevamente `descargas_oc.configurador` para completar los nuevos campos `seafile_repo_id` y `carpeta_destino_local`.

### Ejemplo de valores

Para subir archivos a la plataforma Telcodrive, puedes usar la siguiente configuración de ejemplo:

```
seafile_url   = "https://telcodrive.telconet.net"
seafile_repo_id = "ede837d2-5de8-45f8-802d-aa513aaad8b2"
seafile_subfolder = "/OCS"
carpeta_destino_local = "C:/Descargas/OC"
```
## Credenciales por variables de entorno

`descargas_oc.escuchador` toma el usuario y la contraseña del servidor POP3 usando las variables de entorno `USUARIO_OC` y `PASSWORD_OC`. Estas variables también pueden cargarse desde un archivo `.env` en la raíz del proyecto. Asimismo se pueden definir `POP_SERVER` y `POP_PORT` para indicar el servidor y puerto del correo. Si no se definen, se utilizarán los valores almacenados en el archivo `data/config.json` creado mediante `descargas_oc.configurador`.
## Instalación de dependencias

Instala las bibliotecas de Python necesarias (incluyendo `requests` para la conexión con Seafile) con:

```bash
pip install -r requirements.txt
```



