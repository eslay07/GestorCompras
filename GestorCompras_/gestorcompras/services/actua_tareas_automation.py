from __future__ import annotations

from pathlib import Path
from typing import Any

from gestorcompras.services.telcos_automation import wait_clickable_or_error

MOTIVOS_PAUSA_PERMITIDOS = (
    "CLIENTE NO DISPONIBLE",
    "FALTA INFORMACIÓN",
    "MATERIAL PENDIENTE",
    "PERMISO/ACCESO",
    "OTROS",
)


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
    requested = (valor_o_label or "").strip().upper()
    if requested not in MOTIVOS_PAUSA_PERMITIDOS:
        permitidos = ", ".join(MOTIVOS_PAUSA_PERMITIDOS)
        raise ValueError(
            "Motivo de pausa no permitido. Debe ser uno de: "
            f"{permitidos}"
        )
    for option in select.options:
        label = option.text.strip().upper()
        value = (option.get_attribute("value") or "").strip().upper()
        if requested == label or requested == value:
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
                "opciones": list(MOTIVOS_PAUSA_PERMITIDOS),
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
