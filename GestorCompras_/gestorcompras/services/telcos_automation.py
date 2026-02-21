"""Funciones de automatización Selenium para el portal Telcos.

Este módulo contiene ÚNICAMENTE lógica de Selenium sin dependencias de UI/Tkinter.
Puede ser importado tanto desde la capa de servicios como desde la capa GUI.
"""
from __future__ import annotations

import time
from typing import Any

from gestorcompras.services import db

SERVICIOS_MENSAJE_KEY = "SERVICIOS_REASIGNACION_MSG"
SERVICIOS_DEPARTAMENTO_KEY = "SERVICIOS_DEPARTAMENTO"
SERVICIOS_USUARIO_KEY = "SERVICIOS_USUARIO"

_DEFAULT_TEMPLATE = 'Taller Asignado "{proveedor}"'


def _normalize_template(template: str | None) -> str:
    if template is None or not str(template).strip():
        template = db.get_config(SERVICIOS_MENSAJE_KEY, _DEFAULT_TEMPLATE)
    return template or _DEFAULT_TEMPLATE


def _provider_from_details(task: dict[str, Any]) -> str:
    detalles = task.get("details") or []
    if isinstance(detalles, list):
        for detalle in detalles:
            if isinstance(detalle, dict):
                proveedor = detalle.get("Proveedor") or detalle.get("supplier")
                if proveedor:
                    return str(proveedor)
    return "N/D"


def wait_clickable_or_error(driver, locator, parent, description, timeout=30, retries=3):
    """Espera que un elemento sea clickeable reintentando varias veces."""
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    for intento in range(retries):
        try:
            return WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable(locator)
            )
        except Exception as e:
            if intento == retries - 1:
                raise Exception(f"No se pudo encontrar {description}") from e
            time.sleep(1)


def login_telcos(driver, username: str, password: str) -> None:
    """Inicia sesión en el portal Telcos usando Selenium."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    driver.get(
        "https://telcos.telconet.ec/inicio/?josso_back_to=http://telcos.telconet.ec/check"
        "&josso_partnerapp_host=telcos.telconet.ec"
    )
    user_input = WebDriverWait(driver, 20).until(
        EC.element_to_be_clickable(("name", "josso_username"))
    )
    user_input.send_keys(username)
    password_input = WebDriverWait(driver, 20).until(
        EC.element_to_be_clickable(("name", "josso_password"))
    )
    password_input.send_keys(password)
    password_input.send_keys(Keys.RETURN)
    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.ID, "spanTareasPersonales"))
    )


def process_task_servicios(driver, task: dict[str, Any], parent_window) -> None:
    """Ejecuta la reasignación de una tarea de Servicios en el portal Telcos."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    task_number = task["task_number"]
    dept = str(task.get("reasignacion", "")).strip().upper()
    assignments = db.get_assignment_config()
    assignment_info = assignments.get(dept, {})

    dept_name = (
        task.get("department_override")
        or task.get("department")
        or assignment_info.get("department")
        or db.get_config(SERVICIOS_DEPARTAMENTO_KEY, "")
    )
    empleado = (
        task.get("employee_override")
        or task.get("empleado")
        or assignment_info.get("person")
        or db.get_config(SERVICIOS_USUARIO_KEY, "SIN ASIGNAR")
    )

    if not dept_name or not empleado:
        raise Exception(
            "No existe configuración de departamento o usuario para la reasignación de la tarea "
            f"{task_number}"
        )

    proveedor = task.get("proveedor") or _provider_from_details(task)
    mecanico = task.get("mecanico", "")
    telefono = task.get("telefono", "")
    inf_vehiculo = task.get("inf_vehiculo", "")
    template = _normalize_template(task.get("comentario_template"))
    variables = {
        "proveedor": proveedor or "N/D",
        "mecanico": mecanico or "N/D",
        "telefono": telefono or "N/D",
        "inf_vehiculo": inf_vehiculo or "N/D",
        "task_number": task_number,
    }
    try:
        comentario = template.format(**variables).strip()
    except Exception:
        comentario = template.replace("{proveedor}", variables["proveedor"]).strip()

    element = wait_clickable_or_error(
        driver, (By.ID, "spanTareasPersonales"), parent_window, "el menú de tareas"
    )
    driver.execute_script("arguments[0].click();", element)

    search_input = wait_clickable_or_error(
        driver,
        (By.CSS_SELECTOR, 'input[type="search"].form-control.form-control-sm'),
        parent_window,
        "el campo de búsqueda",
    )
    search_input.clear()
    search_input.send_keys(task_number)
    search_input.send_keys(Keys.RETURN)

    try:
        time.sleep(0.5)
        wait_clickable_or_error(
            driver,
            (By.CSS_SELECTOR, "span.glyphicon.glyphicon-step-forward"),
            parent_window,
            "el botón para abrir la tarea",
        ).click()
    except Exception:
        raise Exception(
            f"No se encontraron las tareas en la plataforma Telcos.\nTarea: {task_number}"
        )

    time.sleep(1)
    comment_input = wait_clickable_or_error(
        driver, (By.ID, "txtObservacionTarea"), parent_window, "el campo de comentario"
    )
    comment_input.send_keys(comentario)
    time.sleep(1)
    wait_clickable_or_error(
        driver, (By.ID, "btnGrabarEjecucionTarea"), parent_window, "el botón Grabar Ejecución"
    ).click()
    time.sleep(2)
    wait_clickable_or_error(
        driver, (By.ID, "btnSmsCustomOk"), parent_window, "la confirmación inicial"
    ).click()
    time.sleep(2)

    wait_clickable_or_error(
        driver,
        (By.CSS_SELECTOR, "span.glyphicon.glyphicon-dashboard"),
        parent_window,
        "el botón de reasignar",
    ).click()
    time.sleep(2)
    department_input = wait_clickable_or_error(
        driver, (By.ID, "txtDepartment"), parent_window, "el campo Departamento"
    )
    department_input.clear()
    department_input.send_keys(dept_name)
    time.sleep(1)
    department_input.send_keys(Keys.DOWN, Keys.RETURN)
    time.sleep(2)
    department_input.send_keys(Keys.TAB)
    time.sleep(2)
    employee_input = WebDriverWait(driver, 20).until(
        EC.element_to_be_clickable(("name", "txtEmpleado"))
    )
    employee_input.click()
    employee_input.send_keys(empleado)
    time.sleep(1)
    employee_input.send_keys(Keys.DOWN, Keys.RETURN)
    time.sleep(2)
    employee_input.send_keys(Keys.TAB)
    time.sleep(2)
    observation_textarea = wait_clickable_or_error(
        driver,
        (By.ID, "txtaObsTareaFinalReasigna"),
        parent_window,
        "el área de observación",
    )
    observation_textarea.send_keys("TALLER ASIGNADO")
    try:
        WebDriverWait(driver, 20).until(
            EC.visibility_of_element_located((By.ID, "modalReasignarTarea"))
        )
    except Exception as e:
        raise Exception("No se abrió la ventana de reasignación") from e
    boton = wait_clickable_or_error(
        driver, (By.ID, "btnGrabarReasignaTarea"), parent_window, "el botón Guardar"
    )
    ActionChains(driver).move_to_element(boton).perform()
    boton.click()
    final_confirm_button = WebDriverWait(driver, 20).until(
        EC.element_to_be_clickable((By.ID, "btnMensajeFinTarea"))
    )
    final_confirm_button.click()
    time.sleep(2)


__all__ = [
    "login_telcos",
    "wait_clickable_or_error",
    "process_task_servicios",
    "_normalize_template",
    "_provider_from_details",
]
