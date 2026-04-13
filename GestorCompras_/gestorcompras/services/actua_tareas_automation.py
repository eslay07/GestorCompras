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
    {"id": "abrir_tareas_personales", "label": "Abrir tareas personales", "descripcion": "Abre el panel de tareas.", "params": []},
    {"id": "ingresar_numero_tarea", "label": "Ingresar N° tarea", "descripcion": "Escribe el número de tarea.", "params": [{"name": "numero", "label": "Número", "tipo": "texto"}]},
    {"id": "consultar", "label": "Consultar", "descripcion": "Ejecuta consulta.", "params": []},
    {"id": "filtrar_tareas", "label": "Filtrar tareas", "descripcion": "Filtra tabla de tareas.", "params": [{"name": "texto", "label": "Texto", "tipo": "texto"}]},
    {"id": "seleccionar_tarea", "label": "Seleccionar tarea", "descripcion": "Selecciona primera tarea.", "params": [{"name": "numero", "label": "Número (referencia)", "tipo": "texto"}]},
    {"id": "reanudar_tarea", "label": "▶ Reanudar tarea", "descripcion": "Reanuda la tarea.", "params": []},
    {"id": "ingresar_observacion", "label": "Ingresar observación", "descripcion": "Escribe observación.", "params": [{"name": "texto", "label": "Observación", "tipo": "texto"}]},
    {"id": "aceptar_observacion", "label": "Aceptar observación", "descripcion": "Confirma observación.", "params": []},
    {"id": "cerrar_mensaje_ok", "label": "Cerrar OK", "descripcion": "Cierra modal OK.", "params": []},
    {"id": "abrir_seguimiento", "label": "Abrir seguimiento", "descripcion": "Abre módulo seguimiento.", "params": []},
    {"id": "guardar_seguimiento", "label": "Guardar seguimiento", "descripcion": "Guarda seguimiento.", "params": []},
    {"id": "abrir_subida_archivo", "label": "📄 Subida de archivo", "descripcion": "Abre módulo carga.", "params": []},
    {"id": "seleccionar_archivo", "label": "Seleccionar archivo", "descripcion": "Carga ruta de archivo.", "params": [{"name": "ruta", "label": "Ruta / alias", "tipo": "archivo"}]},
    {"id": "subir_archivo", "label": "Subir archivo", "descripcion": "Ejecuta subida.", "params": []},
    {"id": "cerrar_mensaje_fin_tarea", "label": "Cerrar fin tarea", "descripcion": "Cierra confirmación final.", "params": []},
    {"id": "abrir_reasignar", "label": "Abrir reasignar", "descripcion": "Abre modal de reasignación.", "params": []},
    {"id": "ingresar_departamento", "label": "Departamento", "descripcion": "Selecciona departamento.", "params": [{"name": "nombre", "label": "Departamento", "tipo": "texto"}]},
    {"id": "ingresar_empleado", "label": "Empleado", "descripcion": "Selecciona empleado.", "params": [{"name": "nombre", "label": "Empleado", "tipo": "texto"}]},
    {"id": "observacion_reasignacion", "label": "Obs. reasignación", "descripcion": "Escribe observación.", "params": [{"name": "texto", "label": "Observación", "tipo": "texto"}]},
    {"id": "guardar_reasignacion", "label": "Guardar reasignación", "descripcion": "Guarda reasignación.", "params": []},
    {"id": "pausar_tarea", "label": "Pausar tarea", "descripcion": "Pausa tarea activa.", "params": []},
    {
        "id": "motivo_pausa",
        "label": "Motivo de pausa",
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
    {"id": "aceptar_pausa", "label": "Aceptar pausa", "descripcion": "Confirma pausa.", "params": []},
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
