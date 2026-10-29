# COMPRAS TN 2.0

Aplicación de escritorio para automatizar los procesos de Compras Bienes. El área de Servicios conserva una copia de la interfaz de Bienes y todavía no es funcional como flujo completo. Guarda su información en `%LOCALAPPDATA%\ComprasTN\2.0`.

## Estado y valor del proyecto

El flujo operativo actual es **Bienes**. Se ejecutan lotes en segundo plano para reducir búsquedas, transcripción y recorridos repetidos por correo, documentos y portales.

Referencias aproximadas reportadas por el autor: 3–4 cotizaciones organizadas en 2 minutos frente a 6–7 manuales; una OC de 5 ítems en 2 minutos frente a 4–5; cinco tareas reasignadas en 3 minutos frente a 10–15; seis OC descargadas y organizadas en 3 minutos frente a 7–8 o más; un flujo del Orquestador en 1 minuto frente a 4–6. El envío de un lote ya preparado de 10–20 correos se sitúa en unos 10 segundos; la revisión previa se mide por separado.

Consulte la [presentación por módulos y las capturas](../README.md) para conocer el recorrido, los tiempos y el proyecto complementario de notificaciones. **Servicios continúa en desarrollo** y sus pantallas no acreditan un flujo operativo terminado.

## Inicio rápido

```powershell
py -3.12 -m venv "$env:USERPROFILE\.venvs\compras-tn"
& "$env:USERPROFILE\.venvs\compras-tn\Scripts\python.exe" -m pip install -r requirements.lock
& "$env:USERPROFILE\.venvs\compras-tn\Scripts\python.exe" -m pip install -e .
& "$env:USERPROFILE\.venvs\compras-tn\Scripts\python.exe" run.py
```

También puede abrirse `COMPRAS 3.0.pyw` con ese entorno para iniciar sin consola. Las contraseñas se
mantienen únicamente en memoria hasta cerrar sesión.

## Desarrollo

```powershell
python -m pip install -e ".[dev]"
pytest
ruff check .
mypy src/compras_tn
```

La aplicación utiliza únicamente su base de datos de COMPRAS TN 2.0.

## Datos y seguridad

- Base activa: `%LOCALAPPDATA%\ComprasTN\2.0\compras_tn.db`.
- Reportes y diagnósticos: subcarpetas `reports` y `diagnostics` del mismo directorio.
- El perfil del instalador excluye contraseñas, secretos, credenciales y mensajes del buzón.
- La contraseña corporativa solo vive en el objeto de sesión y se descarta al cerrar sesión.

## Automatizaciones tolerantes a portales lentos

- **Descargas OC** espera de forma explícita el inicio de sesión, “Lista de accesos”, menús,
  tablas AJAX y el archivo terminado; reintenta cada OC y verifica el número esperado antes de
  descargar. Normal y Abastecimiento comparten una sola sesión por lote.
- Si una OC contiene varias tareas, se descarga una sola vez y se copia/sube de forma independiente
  a la carpeta de cada tarea. El reporte mantiene una fila por OC y muestra las tareas junto al mes.
- **Correos masivos** valida primero PDF, tareas, proveedor y destinatarios. El usuario confirma un
  resumen antes del envío; las órdenes con error se omiten sin bloquear las válidas y, si existen
  PDF duplicados, se usa el modificado más recientemente.
- **Actualizar Tareas** espera el resultado específico de cada número, incluso cuando la tabla se
  actualiza sin cambiar su texto, y nunca selecciona una fila distinta como alternativa. Una OC
  pendiente o temporalmente no verificable se registra como advertencia, pero no bloquea el flujo.
- No se usan pausas fijas para sincronizar páginas. Los tiempos y reintentos pueden ajustarse en
  **Configuración > Descargas/Telcos** si la red corporativa necesita un margen mayor.
- Si NAF muestra «No se pudo validar la sesión / ¿Volver a intentar?» —caso observado especialmente
  con navegador oculto— la automatización pulsa Sí hasta dos veces y vuelve a esperar el portal.
- Ante un fallo se crea evidencia saneada en `diagnostics`; las URL no incluyen parámetros y las
  contraseñas se sustituyen antes de escribir metadatos.
- Al cancelar, los elementos todavía no iniciados quedan registrados como omitidos, por lo que el
  resumen conserva un resultado para cada OC o tarea del lote.

## Carga automática de OC de Bienes

- **Bienes > Carga de OC automática** lee la pestaña GENERAL mediante acceso autenticado y
  presenta las órdenes agrupadas por RUC, departamento y solicitante exactos antes de ejecutar.
- Configure **Credenciales Google (JSON)** con una cuenta de servicio y comparta la hoja como
  **editor** con el correo indicado en el JSON. Conserve el ID del documento y `GENERAL` como
  pestaña. No se usa CSV público para decidir elegibilidad: se comprueba también si G tiene fórmula.
- En **Configuración > Proveedores**, registre los proveedores y edite el
  nombre oficial y hasta tres **Sobrenombres** usados en la columna E de GENERAL. La comparación no
  distingue mayúsculas y minúsculas y exige una coincidencia exacta; de ahí se obtiene el RUC para
  NAF. El catálogo permite buscar por proveedor, cualquiera de los sobrenombres, RUC o correo.
- La columna K debe contener el nombre completo y canónico de NAF. La precarga lo usa directamente,
  sin alias ni coincidencias aproximadas, y bloquea la orden si NAF no encuentra ese nombre exacto.
- La detección comienza en la fila 7346. Una tarea solo aparece si contiene al menos un artículo
  nuevo con código en B, cantidad positiva en D, proveedor o sobrenombre en E y precio válido en F;
  las filas incompletas, con código por crear o con número de OC en G se omiten.
- La tabla permite marcar individualmente las órdenes válidas; únicamente las seleccionadas se
  envían a NAF. La casilla **Navegador visible** permite observar el ingreso y la precarga.
- Cada orden puede reunir varias tareas. Un código repetido se carga una sola vez sumando sus
  cantidades; si tiene precios distintos se bloquea la OC completa y se muestran las filas para
  corregirlas. Departamento y solicitante solo pierden espacios exteriores: se distingue mayúscula,
  minúscula y espacios interiores. Los alias del proveedor conservan su comparación sin distinción
  de mayúsculas y se resuelven al RUC.
- Doble clic en la OC permite revisar las líneas consolidadas, las contribuciones de cada tarea/fila
  y las observaciones. Cada tarea mantiene su propio bloque de observación, separado por un salto
  de línea; las cantidades del detalle de cada tarea son las originales. No se truncan observaciones.
- El acceso a NAF verifica que usuario y contraseña se hayan escrito antes de confirmar el ingreso.
  Si CAS conserva la pantalla de login, el proceso termina con un error explicativo en
  lugar de permanecer esperando indefinidamente. Para CAS se usa siempre el usuario corporativo
  corto, sin `@telconet.ec` y en mayúsculas (por ejemplo, `USUARIO_DEMO`). Si CAS vuelve al formulario
  sin explicar el rechazo, se conserva el navegador y sus cookies, se recupera el destino CAS con
  `service` y se usa el siguiente intento permitido solo si vuelve a pedir credenciales. No se
  interrumpen redirecciones con `window.stop()`. Un rechazo explícito no se repite. Dashboard ya
  acredita autenticación; la apertura del menú se informa como una fase distinta.
- El login de Descargas OC y Carga de OC automática escribe el usuario, usa Tab, espera dos segundos,
  escribe la contraseña, espera otros dos segundos y confirma con Enter.
- La automatización genera la observación, pulsa **Guardar** una sola vez y nunca utiliza el visto
  de aprobación. El número asignado se escribe en G de todos los artículos de esa orden y se
  verifica antes de continuar. Si Sheets falla, se conserva el número y se detiene el lote;
  **Recuperar OC pendientes** permite completar la sincronización sin crear otra orden. Las filas
  con G vacía e intento `saving` o `pending` permanecen visibles pero bloqueadas para generar una
  nueva OC. Esta protección se conserva al reiniciar y no bloquea las otras órdenes válidas.
- Al guardar se vuelve a localizar el encabezado durante la recarga y se compara con la ruta exacta
  de la OC y el número anterior. Un fallo después del clic nunca provoca otro clic automático.
  El número confirmado se persiste antes de Sheets. Los errores temporales de conexión, 429 o 5xx
  se reintentan hasta tres veces, releyendo todas las celdas G: valores ya aplicados se reconocen,
  fórmulas, otra OC o artículos modificados no se sobrescriben.
- En **Recuperar OC pendientes**, revise las candidatas en NAF, indique únicamente la OC que
  conservará y documente la comprobación de proveedor, tareas y artículos. No se selecciona ni
  cancela automáticamente ninguna candidata. Solo descarte un intento cuando haya comprobado que
  no creó una orden. Ambas acciones conservan evidencia, usuario e historial en los JSON existentes.
- Al cambiar de Python, se reutiliza la base existente de Microsoft Store si es la única encontrada.
  Si hay varias bases, debe especificar la carpeta productiva mediante `COMPRAS_TN_DATA_DIR`.
  No se migra ni se reemplaza la base automáticamente.
- Los correos de Descargas OC conservan el asunto, las tablas HTML y el texto alternativo de la
  versión original; no adjuntan el Excel local de auditoría.
- Todos los reportes de resultados usan ese estilo de tablas dentro del correo, con correctos,
  errores y omitidos. No adjuntan Excel; el archivo de auditoría se conserva localmente. Los correos
  comerciales dirigidos a proveedores y sus adjuntos no cambian.
- Los procesos operativos muestran una confirmación final de éxito, novedades, cancelación o error.
- **Actualizar Tareas** agrupa por número de tarea; si llega repetida desde varios orígenes se muestra
  una sola fila con los datos más completos y los orígenes combinados.
- El origen **Carga de OC automática** incorpora nuevas cargas y sincronizaciones pendientes
  completadas con esta versión, no el historial anterior ya finalizado. Cada tarea aparece cuando
  sus nuevas OC están sincronizadas y todos sus artículos completos tienen OC, incluidos los de
  proveedores no seleccionados. Las tareas de una misma OC compartida se evalúan individualmente.
- Use **Actualizar origen OC** para volver a verificar GENERAL en segundo plano. Un fallo de lectura,
  una fórmula en G o un guardado pendiente no habilitan tareas. Antes de ejecutar se vuelve a validar.
  Una tarea consumida o descartada de ese origen no reaparece por una simple recarga.
- Marque **Ingreso manual** para desplegar el cuadro e ingresar una tarea por renglón. **Agregar tareas**
  omite vacíos y duplicados; acepta también comas o punto y coma. Si hay entradas no numéricas o de
  más de 14 dígitos, pide corregirlas sin agregar parcialmente. Esto no ejecuta el flujo.

## Verificación manual corporativa

Para comprobar exclusivamente el login NAF con Chrome oculto y sin crear OC ni escribir en Sheets,
ejecute `python tools/check_naf_login.py` con Python 3.12 y las dependencias de la aplicación. Solicita
la contraseña sin mostrarla ni guardarla y lee la configuración productiva en modo solo lectura.

Las pruebas reales no se ejecutan por defecto. Después de completar Configuración puede usar los
botones **Probar correo**, **Probar Google Sheets**, **Probar Seafile** y **Probar Telcos**. Para
ejecutar sus equivalentes desde pytest:

```powershell
$env:COMPRAS_TN_LIVE="1"
$env:COMPRAS_TN_USER="usuario@telconet.ec"
$env:COMPRAS_TN_PASSWORD="contraseña-de-sesión"
pytest -m live
```

No deje esas variables configuradas después de la prueba. Antes del cambio operativo deben recorrerse
manualmente Correos masivos, Seguimientos, Reasignación, Descargas normal/abastecimiento y Actualizar
Tareas en Bienes y Servicios con credenciales de sesión.
