"""Adaptador para ejecutar la reasignación desde el flujo de Servicios."""
from __future__ import annotations

import logging
from typing import Any, Dict

from gestorcompras.services import db

logger = logging.getLogger(__name__)

_DEFAULT_TEMPLATE = 'Taller Asignado "{proveedor}"'


def _normalize_template(template: str | None) -> str:
    if template is None:
        template = db.get_config("SERVICIOS_REASIGNACION_MSG", _DEFAULT_TEMPLATE)
    return template or _DEFAULT_TEMPLATE


def _ensure_credentials(email_session: Dict[str, str] | None) -> tuple[str, str]:
    if not email_session:
        raise ValueError("No hay sesión de Telcos disponible.")
    address = email_session.get("address", "")
    password = email_session.get("password", "")
    if not address or not password:
        raise ValueError("Credenciales incompletas para iniciar sesión en Telcos.")
    return address, password


def _build_payload(
    task_number: str,
    proveedor: str,
    mecanico: str,
    telefono: str,
    inf_vehiculo: str,
    fuente: str,
    department: str | None,
    employee: str | None,
    comentario_template: str,
) -> Dict[str, Any]:
    return {
        "task_number": task_number,
        "reasignacion": "",
        "details": [],
        "proveedor": proveedor or "N/D",
        "mecanico": mecanico or "N/D",
        "telefono": telefono or "N/D",
        "inf_vehiculo": inf_vehiculo or "N/D",
        "department_override": (department or "").strip(),
        "employee_override": (employee or "").strip(),
        "comentario_template": comentario_template,
        "fuente": fuente,
    }


def _run_selenium_reassign(
    email_session: Dict[str, str],
    payload: Dict[str, Any],
    headless: bool,
) -> Dict[str, Any]:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager

    from gestorcompras.gui.reasignacion_gui import login_telcos, process_task

    service = Service(ChromeDriverManager().install())
    options = Options()
    if headless:
        options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    prefs = {"profile.managed_default_content_settings.images": 2}
    options.add_experimental_option("prefs", prefs)

    driver = webdriver.Chrome(service=service, options=options)
    try:
        address, password = _ensure_credentials(email_session)
        login_telcos(driver, address.split("@")[0], password)
        process_task(driver, payload, None)
    finally:
        driver.quit()
    return {"status": "ok", "details": payload}


def reassign_by_task_number(
    task_number: str,
    proveedor: str,
    mecanico: str,
    telefono: str,
    inf_vehiculo: str,
    *,
    fuente: str = "SERVICIOS",
    department: str | None = None,
    employee: str | None = None,
    headless: bool = True,
    comentario_template: str | None = None,
    email_session: Dict[str, str] | None = None,
) -> Dict[str, Any]:
    """Ejecuta la reasignación de una tarea utilizando Selenium."""

    if not task_number:
        return {"status": "error", "details": "Número de tarea inválido"}

    template = _normalize_template(comentario_template)
    payload = _build_payload(
        task_number,
        proveedor,
        mecanico,
        telefono,
        inf_vehiculo,
        fuente,
        department,
        employee,
        template,
    )

    try:
        result = _run_selenium_reassign(email_session or {}, payload, headless)
        logger.info(
            "Reasignación completada para tarea %s (%s)",
            task_number,
            payload.get("fuente"),
        )
        return result
    except ValueError as exc:
        logger.warning("Reasignación cancelada: %s", exc)
        return {"status": "error", "details": str(exc)}
    except Exception as exc:  # pragma: no cover - protección adicional
        mensaje = str(exc)
        logger.exception("Error durante la reasignación de la tarea %s", task_number)
        if "No se encontraron las tareas" in mensaje:
            return {"status": "not_found", "details": mensaje}
        return {"status": "error", "details": mensaje}


__all__ = ["reassign_by_task_number"]

