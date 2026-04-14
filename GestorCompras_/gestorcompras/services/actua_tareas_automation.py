from __future__ import annotations

from pathlib import Path
from typing import Any

from gestorcompras.services.telcos_automation import wait_clickable_or_error

MOTIVOS_PAUSA_CATALOGO = [
    ("1641", "SE SOLICITA COTIZACION AL PROVEEDOR"),
    ("1642", "EN ESPERA DE AUTORIZACION EN EL NAF"),
    ("1643", "POR TIEMPO DE ENTREGA DEL PRODUCTO NACIONAL/IMPORTADO"),
    ("1644", "POR MOTIVO DE PAGO: ANTICIPO / CONTADO"),
    ("1645", "POR MOTIVO DE ENVIO DE FACTURA ELECTRONICA"),
    ("1701", "GESTIÓN DE PERMISOS PARA ACCEDER A LAS INSTALACIONES DE CLIENTES"),
    ("1702", "GESTIÓN DE PERMISOS PARA INGRESAR A CENTROS COMERCIALES"),
    ("1703", "GESTIÓN DE ASIGNACIÓN DE FISCALIZADOR EN SECTORES REGENERADOS"),
    ("1704", "GESTIÓN DE ASIGNACIÓN DE CUSTODIOS EN SECTORES PELIGROSOS"),
    ("1804", "A LA ESPERA DE PERMISOS POR PARTE DEL C.C/ADMINISTRACIÓN"),
    ("1805", "A LA ESPERA DE PERMISOS POR PARTE DEL CLIENTE"),
    ("1806", "A LA ESPERA DE QUE SE DESCARTEN PROBLEMAS ELÉCTRICOS"),
    ("1807", "A LA ESPERA DE RESPUESTA POR PARTE DE LA EMPRESA TERCERIZADORA"),
    ("1808", "EN ESPERA DE RESPUESTA DEL CLIENTE (ENVIO DE PRUEBAS)"),
    ("1809", "NO SE TIENE RESPUESTA DEL CONTACTO PROPORCIONADO"),
    ("1810", "SOLICITUD DE NUEVO CONTACTO EN SITIO"),
    ("1814", "PRODUCTO- SOLICITUD DE INFORMACION AL CLIENTE FINAL"),
    ("1815", "PRODUCTO- SOLICITUD DE FACTIBILIDAD A TÉCNICO"),
    ("1816", "PRODUCTO- SOLICITUD DE APLAZAMIENTO DE COTIZACIÓN PRIORITARIA"),
    ("1831", "INACTIVACION POR MORA"),
    ("1832", "CONVENIO DE PAGO"),
    ("1833", "CONFIRMACION DE PAGO"),
    ("1834", "N/D PENDIENTE"),
    ("1835", "N/C PENDIENTE"),
    ("1836", "SOLICTUD DE SLA Y CACTI"),
    ("1837", "CONFIRMACION FECHA DE PAGO"),
    ("1761", "EN ESPERA DE REPORTE DE MOVILIZACION"),
    ("1813", "PRODUCTO- SOLICITUD DE COTIZACION AL FABRICANTE"),
    ("1744", "CORTE FO ACCESO TERCERIZADA - EDIFICIO/C.C."),
    ("1745", "ATENUACIÓN FO ACCESO TERCERIZADA - EDIFICIO/C.C."),
    ("1798", "GESTIÓN POR ACCESOS AL NODO"),
    ("1799", "NODO EN BATERÍAS"),
    ("1812", "PRODUCTO- SOLICITUD DE COTIZACION AL MAYORISTA"),
    ("1818", "SOLICITUD DE INFORMACION AL ASESOR COMERCIAL"),
    ("1819", "SOLICITUD DE ASIGNACION DE MAYORISTA"),
    ("1820", "SOLICITUD DE COTIZACION NO RECURRENTES A IMPORTACIONES"),
    ("1821", "SOLICITUD DE COTIZACION NO RECURRENTES A COMPRAS"),
    ("1735", "EN ESPERA DE RESPUESTA DEL CLIENTE"),
    ("1736", "CLIENTE NO CONTACTADO"),
    ("1737", "CLIENTE SOLICITA ATENCION DIFERIDA"),
    ("1738", "GESTION POR PERMISOS DEL CLIENTE"),
    ("1739", "GESTION POR PERMISOS C.C./EDIFICIOS"),
    ("1740", "SOLICITUD DE FISCALIZADOR"),
    ("1741", "SOLICITUD DE CUSTODIO"),
    ("1746", "REVISIÓN FO ACCESO TERCERIZADA"),
    ("2995", "POR ESPERA RESPUESTA DEL USUARIO"),
    ("2996", "POR FIRMA DE LA ORDEN DE COMPRA"),
    ("2997", "POR CREACION DE CODIGO DEL ITEM POR PARTE DE BODEGA"),
    ("2998", "POR CREACION DE PROVEEDOR POR PARTE DE CONTABILIDAD"),
    ("2999", "POR GESTION DE ENTREGA PROVEEDOR"),
    ("3649", "CLIENTE SOLICITA REPROGRAMAR"),
    ("1619", "SUSPENDE TRABAJO POR SOLICITUD DE CLIENTE"),
    ("1620", "ASIGNACIÓN DE CASO PRIORITARIO"),
    ("1621", "TRABAJOS O PERMISOS DE EMPRESAS EXTERNAS"),
    ("1622", "CONDICIONES CLIMÁTICAS"),
    ("1623", "DAÑO DE EQUIPAMIENTO"),
    ("1624", "DAÑO DE INFRAESTRUCTURA"),
    ("1625", "REQUERIMIENTO DE RECURSO EXTERNO"),
    ("1626", "SECTOR PELIGROSO/INTENTO DE ROBO"),
    ("2376", "GESTION DE EXAMENES MEDICOS"),
    ("2377", "SOLICITUD DE PLANOS ARQUITECTONICOS AL CLIENTE"),
    ("2378", "GESTION DE RECURSOS ADICIONALES DE PERSONAL TECNICO"),
    ("2379", "A LA ESPERA DE INFORMES TECNICOS"),
    ("2380", "GESTION DE APROVISIONAMIENTO DE MATERIALES"),
    ("2381", "GESTION DE DOCUMENTACION PARA INGRESO A INSTALACION A CLIENTE"),
    ("4214", "DESARROLLO IyD"),
    ("4215", "IA-VISION SOLICITUD DE FACTIBILIDAD"),
    ("4216", "LLM-PROCESOS SOLICITUD DE FACTIBILIDAD"),
    ("4217", "SOLICITUD DE FACTIBILIDAD"),
]

MOTIVOS_PAUSA_PERMITIDOS = tuple(label for _, label in MOTIVOS_PAUSA_CATALOGO)
MOTIVOS_PAUSA_VALORES = {value for value, _ in MOTIVOS_PAUSA_CATALOGO}
MOTIVOS_PAUSA_OPCIONES_UI = [f"{value} - {label}" for value, label in MOTIVOS_PAUSA_CATALOGO]


def _resolve(value: str, ctx: dict[str, Any]) -> str:
    text = str(value or "")
    try:
        return text.format(**ctx)
    except Exception:
        return text


def abrir_tareas_personales(driver, **_params):
    from selenium.webdriver.common.by import By

    btn = wait_clickable_or_error(driver, (By.ID, "spanTareasPersonales"), None, "Tareas Personales")
    driver.execute_script("arguments[0].click();", btn)


def ingresar_numero_tarea(driver, numero: str, **_params):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys

    campo = wait_clickable_or_error(driver, (By.ID, "txtActividad"), None, "Número de tarea")
    campo.clear()
    campo.send_keys(str(numero))
    campo.send_keys(Keys.RETURN)


def consultar(driver, **_params):
    from selenium.webdriver.common.by import By

    btn = wait_clickable_or_error(
        driver,
        (By.XPATH, "//button[contains(., 'Consultar') or contains(@onclick, 'buscar()')]"),
        None,
        "Consultar",
    )
    btn.click()


def filtrar_tareas(driver, texto: str, **_params):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys

    campo = wait_clickable_or_error(driver, (By.CSS_SELECTOR, "#gridTareas input[type='search']"), None, "Filtro")
    campo.clear()
    campo.send_keys(texto)
    campo.send_keys(Keys.RETURN)


def seleccionar_tarea(driver, numero: str, **_params):
    from selenium.webdriver.common.by import By

    fila = wait_clickable_or_error(driver, (By.CSS_SELECTOR, "#gridTareas tbody tr"), None, f"fila tarea {numero}")
    fila.click()


def reanudar_tarea(driver, **_params):
    from selenium.webdriver.common.by import By

    wait_clickable_or_error(driver, (By.CSS_SELECTOR, "span.glyphicon.glyphicon-step-forward"), None, "Reanudar").click()


def ingresar_observacion(driver, texto: str, **_params):
    from selenium.webdriver.common.by import By

    campo = wait_clickable_or_error(driver, (By.ID, "txtObservacionTarea"), None, "Observación")
    campo.clear()
    campo.send_keys(texto)


def aceptar_observacion(driver, **_params):
    from selenium.webdriver.common.by import By

    wait_clickable_or_error(driver, (By.XPATH, "//button[contains(@class,'text-btn') and contains(.,'Aceptar')]"), None, "Aceptar").click()


def cerrar_mensaje_ok(driver, **_params):
    from selenium.webdriver.common.by import By

    try:
        wait_clickable_or_error(driver, (By.ID, "btnSmsCustomOk"), None, "OK", timeout=8).click()
    except Exception:
        wait_clickable_or_error(driver, (By.XPATH, "//button[contains(@class,'text-btn') and contains(.,'OK')]"), None, "OK fallback", timeout=8).click()


def abrir_seguimiento(driver, **_params):
    from selenium.webdriver.common.by import By

    wait_clickable_or_error(driver, (By.CSS_SELECTOR, "span.glyphicon.glyphicon-list-alt"), None, "Seguimiento").click()


def guardar_seguimiento(driver, **_params):
    from selenium.webdriver.common.by import By

    wait_clickable_or_error(driver, (By.ID, "btnIngresoSeguimiento"), None, "Guardar seguimiento").click()


def abrir_subida_archivo(driver, **_params):
    from selenium.webdriver.common.by import By

    wait_clickable_or_error(driver, (By.CSS_SELECTOR, "span.glyphicon.glyphicon-open-file"), None, "Subir archivo").click()


def seleccionar_archivo(driver, ruta: str, **_params):
    from selenium.webdriver.common.by import By

    wait_clickable_or_error(driver, (By.CSS_SELECTOR, "input[name='archivos[]']"), None, "Selector archivo").send_keys(ruta)


def subir_archivo(driver, **_params):
    from selenium.webdriver.common.by import By

    wait_clickable_or_error(driver, (By.ID, "btnCargarArchivo"), None, "Cargar archivo").click()


def cerrar_mensaje_fin_tarea(driver, **_params):
    from selenium.webdriver.common.by import By

    wait_clickable_or_error(driver, (By.ID, "btnMensajeFinTarea"), None, "Cerrar fin tarea").click()


def abrir_reasignar(driver, **_params):
    from selenium.webdriver.common.by import By

    wait_clickable_or_error(driver, (By.CSS_SELECTOR, "span.glyphicon.glyphicon-dashboard"), None, "Reasignar").click()


def ingresar_departamento(driver, nombre: str, **_params):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys

    campo = wait_clickable_or_error(driver, (By.ID, "txtDepartment"), None, "Departamento")
    campo.clear()
    campo.send_keys(nombre)
    campo.send_keys(Keys.DOWN, Keys.RETURN)


def ingresar_empleado(driver, nombre: str, **_params):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys

    campo = wait_clickable_or_error(driver, (By.ID, "txtEmpleado"), None, "Empleado")
    campo.clear()
    campo.send_keys(nombre)
    campo.send_keys(Keys.DOWN, Keys.RETURN)


def observacion_reasignacion(driver, texto: str, **_params):
    from selenium.webdriver.common.by import By

    campo = wait_clickable_or_error(driver, (By.ID, "txtaObsTareaFinalReasigna"), None, "Observación reasignación")
    campo.clear()
    campo.send_keys(texto)


def guardar_reasignacion(driver, **_params):
    from selenium.webdriver.common.by import By

    wait_clickable_or_error(driver, (By.ID, "btnGrabarReasignaTarea"), None, "Guardar reasignación").click()


def pausar_tarea(driver, **_params):
    from selenium.webdriver.common.by import By

    wait_clickable_or_error(driver, (By.CSS_SELECTOR, "span.glyphicon.glyphicon-pause"), None, "Pausar tarea").click()


def motivo_pausa(driver, valor_o_label: str, **_params):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import Select

    select = Select(wait_clickable_or_error(driver, (By.ID, "cmbMotivoPausa"), None, "Motivo de pausa"))
    raw_requested = (valor_o_label or "").strip()
    requested = raw_requested.upper()
    if " - " in requested and requested.split(" - ", 1)[0].strip().isdigit():
        requested = requested.split(" - ", 1)[0].strip()

    # Truco operativo: si el usuario envía una sola letra, selecciona
    # el primer motivo del catálogo que inicie con esa letra.
    if len(requested) == 1 and requested.isalpha():
        for _, label in MOTIVOS_PAUSA_CATALOGO:
            if label.startswith(requested):
                requested = label
                break

    if requested not in MOTIVOS_PAUSA_VALORES and requested not in {m.upper() for m in MOTIVOS_PAUSA_PERMITIDOS}:
        raise ValueError("Motivo de pausa no permitido en el catálogo oficial.")
    for option in select.options:
        label = option.text.strip().upper()
        value = (option.get_attribute("value") or "").strip().upper()
        if requested == value or requested == label:
            option.click()
            return
    raise ValueError(f"El motivo de pausa '{requested}' no está disponible en Telcos.")


def aceptar_pausa(driver, **_params):
    from selenium.webdriver.common.by import By

    wait_clickable_or_error(driver, (By.XPATH, "//button[contains(@class,'text-btn') and contains(.,'Aceptar')]"), None, "Aceptar pausa").click()


ACCIONES = [
    {"id": "abrir_tareas_personales", "label": "Navegación → Abrir 'Tareas personales'", "descripcion": "Abre el panel principal de tareas en Telcos.", "params": []},
    {"id": "ingresar_numero_tarea", "label": "Búsqueda → Escribir N° de tarea", "descripcion": "Escribe el número de tarea en el campo principal.", "params": [{"name": "numero", "label": "Número", "tipo": "texto"}]},
    {"id": "consultar", "label": "Búsqueda → Consultar", "descripcion": "Ejecuta la búsqueda de tareas.", "params": []},
    {"id": "filtrar_tareas", "label": "Tabla → Filtrar resultados", "descripcion": "Filtra la tabla de tareas por texto.", "params": [{"name": "texto", "label": "Texto", "tipo": "texto"}]},
    {"id": "seleccionar_tarea", "label": "Tabla → Seleccionar primera tarea", "descripcion": "Selecciona la primera fila visible de la tabla.", "params": [{"name": "numero", "label": "Número (referencia)", "tipo": "texto"}]},
    {"id": "reanudar_tarea", "label": "Ejecución → Reanudar tarea", "descripcion": "Abre/reanuda la tarea seleccionada.", "params": []},
    {"id": "ingresar_observacion", "label": "Ejecución → Escribir observación", "descripcion": "Escribe la observación de ejecución.", "params": [{"name": "texto", "label": "Observación", "tipo": "texto"}]},
    {"id": "aceptar_observacion", "label": "Ejecución → Aceptar observación", "descripcion": "Confirma la observación ingresada.", "params": []},
    {"id": "cerrar_mensaje_ok", "label": "Modal → Cerrar mensaje OK", "descripcion": "Cierra el mensaje de confirmación tipo OK.", "params": []},
    {"id": "abrir_seguimiento", "label": "Seguimiento → Abrir panel", "descripcion": "Abre la ventana de seguimiento de la tarea.", "params": []},
    {"id": "guardar_seguimiento", "label": "Seguimiento → Guardar", "descripcion": "Guarda la información del seguimiento.", "params": []},
    {"id": "abrir_subida_archivo", "label": "Archivos → Abrir carga", "descripcion": "Abre el módulo para cargar archivos.", "params": []},
    {"id": "seleccionar_archivo", "label": "Archivos → Seleccionar archivo", "descripcion": "Selecciona archivo (ruta o alias).", "params": [{"name": "ruta", "label": "Ruta / alias", "tipo": "archivo"}]},
    {"id": "subir_archivo", "label": "Archivos → Subir archivo", "descripcion": "Ejecuta la carga del archivo seleccionado.", "params": []},
    {"id": "cerrar_mensaje_fin_tarea", "label": "Modal → Cerrar fin de tarea", "descripcion": "Cierra la confirmación final de tarea.", "params": []},
    {"id": "abrir_reasignar", "label": "Reasignación → Abrir panel", "descripcion": "Abre la ventana de reasignación.", "params": []},
    {"id": "ingresar_departamento", "label": "Reasignación → Elegir departamento", "descripcion": "Selecciona el departamento destino.", "params": [{"name": "nombre", "label": "Departamento", "tipo": "texto"}]},
    {"id": "ingresar_empleado", "label": "Reasignación → Elegir empleado", "descripcion": "Selecciona el empleado destino.", "params": [{"name": "nombre", "label": "Empleado", "tipo": "texto"}]},
    {"id": "observacion_reasignacion", "label": "Reasignación → Escribir observación", "descripcion": "Escribe observación para la reasignación.", "params": [{"name": "texto", "label": "Observación", "tipo": "texto"}]},
    {"id": "guardar_reasignacion", "label": "Reasignación → Guardar", "descripcion": "Guarda y confirma la reasignación.", "params": []},
    {"id": "pausar_tarea", "label": "Ejecución → Pausar tarea", "descripcion": "Abre el flujo de pausa de tarea.", "params": []},
    {
        "id": "motivo_pausa",
        "label": "Ejecución → Seleccionar motivo de pausa",
        "descripcion": "Selecciona motivo (catálogo cerrado).",
        "params": [
            {
                "name": "valor_o_label",
                "label": "Motivo",
                "tipo": "select",
                "opciones": list(MOTIVOS_PAUSA_OPCIONES_UI),
            }
        ],
    },
    {"id": "aceptar_pausa", "label": "Ejecución → Confirmar pausa", "descripcion": "Confirma y guarda la pausa.", "params": []},
]

_DISPATCH = {item["id"]: globals()[item["id"]] for item in ACCIONES}


def _resolver_archivo(raw: str, ctx: dict[str, Any]) -> str:
    aliases = ctx.get("file_aliases", {}) or {}
    carpeta_base = ctx.get("carpeta_base", "")
    value = _resolve(raw, ctx)
    if value in aliases:
        return aliases[value]
    path = Path(value)
    if path.is_absolute():
        return str(path)
    if carpeta_base:
        return str((Path(carpeta_base) / value).resolve())
    return value


def ejecutar_flujo(driver, pasos: list[dict[str, Any]], ctx: dict[str, Any] | None = None):
    ctx = dict(ctx or {})
    for idx, paso in enumerate(pasos, start=1):
        action_id = paso.get("id")
        if action_id not in _DISPATCH:
            raise ValueError(f"Acción no soportada: {action_id}")
        params = dict(paso.get("params") or {})
        for key, value in list(params.items()):
            params[key] = _resolve(value, ctx)
        if action_id == "seleccionar_archivo" and "ruta" in params:
            params["ruta"] = _resolver_archivo(params["ruta"], ctx)
        _DISPATCH[action_id](driver, **params)
        if ctx.get("on_step"):
            ctx["on_step"](idx, action_id, params)
