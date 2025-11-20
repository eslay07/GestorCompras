"""Adaptador para ejecutar la reasignación desde el flujo de Servicios."""
from __future__ import annotations

import logging
from typing import Any, Dict, List

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


def _create_driver(headless: bool):
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager

    service = Service(ChromeDriverManager().install())
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    prefs = {"profile.managed_default_content_settings.images": 2}
    options.add_experimental_option("prefs", prefs)
    return webdriver.Chrome(service=service, options=options)


def _reanudar_panel(driver) -> None:
    try:
        from selenium.webdriver.common.by import By

        from gestorcompras.gui.reasignacion_gui import wait_clickable_or_error

        boton = wait_clickable_or_error(
            driver,
            (By.ID, "spanTareasPersonales"),
            None,
            "el menú de tareas",
            timeout=15,
            retries=1,
        )
        driver.execute_script("arguments[0].click();", boton)
    except Exception as exc:  # pragma: no cover - mejora de resiliencia
        logger.debug("No se pudo reabrir el panel de tareas: %s", exc)


def _run_selenium_batch(
    email_session: Dict[str, str],
    payloads: List[Dict[str, Any]],
    headless: bool,
) -> List[Dict[str, Any]]:
    if not payloads:
        return []

    from gestorcompras.gui.reasignacion_gui import login_telcos, process_task_servicios

    driver = None
    resultados: List[Dict[str, Any]] = []
    try:
        address, password = _ensure_credentials(email_session)
        driver = _create_driver(headless)
        login_telcos(driver, address.split("@")[0], password)

        for payload in payloads:
            message_id = payload.get("message_id")
            try:
                process_task_servicios(driver, payload, None)
                _reanudar_panel(driver)
                resultados.append({
                    "status": "ok",
                    "details": payload,
                    "message_id": message_id,
                })
            except Exception as exc:  # pragma: no cover - se registra para diagnóstico
                estado = "not_found" if "No se encontraron las tareas" in str(exc) else "error"
                resultados.append({
                    "status": estado,
                    "details": payload,
                    "message_id": message_id,
                    "error": str(exc),
                })
                try:
                    _reanudar_panel(driver)
                except Exception:
                    pass
        return resultados
    finally:
        if driver:
            driver.quit()


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
    payload["message_id"] = None

    resultados = reassign_tasks(
        [payload],
        fuente=fuente,
        department=department,
        employee=employee,
        headless=headless,
        comentario_template=template,
        email_session=email_session,
        _prebuilt_payloads=True,
    )
    return resultados[0] if resultados else {"status": "error", "details": "Sin resultado"}


def reassign_tasks(
    records: List[Dict[str, Any]],
    *,
    fuente: str = "SERVICIOS",
    department: str | None = None,
    employee: str | None = None,
    headless: bool = True,
    comentario_template: str | None = None,
    email_session: Dict[str, str] | None = None,
    _prebuilt_payloads: bool = False,
) -> List[Dict[str, Any]]:
    """Reasigna múltiples tareas reutilizando la misma sesión de navegador."""

    if not records:
        return []

    template = _normalize_template(comentario_template)
    payloads: List[Dict[str, Any]] = []
    if _prebuilt_payloads:
        payloads = records
        for payload in payloads:
            if "comentario_template" not in payload or not payload["comentario_template"]:
                payload["comentario_template"] = template
    else:
        for record in records:
            task_number = record.get("task_number")
            payload = _build_payload(
                str(task_number or ""),
                record.get("proveedor", ""),
                record.get("mecanico", ""),
                record.get("telefono", ""),
                record.get("inf_vehiculo", ""),
                fuente,
                department,
                employee,
                template,
            )
            payload["message_id"] = record.get("message_id")
            payloads.append(payload)

    try:
        resultados = _run_selenium_batch(email_session or {}, payloads, headless)
        for resultado in resultados:
            if resultado.get("status") == "ok":
                detalle = resultado.get("details", {})
                logger.info(
                    "Reasignación completada para tarea %s (%s)",
                    detalle.get("task_number"),
                    detalle.get("fuente", fuente),
                )
        return resultados
    except ValueError as exc:
        logger.warning("Reasignación cancelada: %s", exc)
        return [
            {
                "status": "error",
                "message_id": payload.get("message_id"),
                "error": str(exc),
                "details": payload,
            }
            for payload in payloads
        ]
    except Exception as exc:  # pragma: no cover - protección adicional
        logger.exception("Error durante la reasignación de tareas")
        mensaje = str(exc)
        return [
            {
                "status": "error",
                "message_id": payload.get("message_id"),
                "error": mensaje,
                "details": payload,
            }
            for payload in payloads
        ]


__all__ = ["reassign_by_task_number", "reassign_tasks"]

