"""Adaptador para reutilizar la lógica previa de reasignación."""
from __future__ import annotations

import logging
from typing import Dict

from gestorcompras.services import db

logger = logging.getLogger(__name__)


def _find_legacy_task(task_number: str) -> Dict[str, object]:
    for task in db.get_tasks_temp():
        if str(task.get("task_number")) == str(task_number):
            return task
    raise LookupError(f"Tarea {task_number} no encontrada en el repositorio legado")


def reassign_by_task_number(
    task_number: str,
    proveedor: str,
    mecanico: str,
    telefono: str,
    inf_vehiculo: str,
    fuente: str = "SERVICIOS",
) -> Dict[str, object]:
    """Intenta reasignar utilizando la base de datos temporal previa."""
    try:
        legacy_task = _find_legacy_task(task_number)
    except LookupError as exc:
        logger.warning("Tarea no encontrada para reasignación: %s", task_number)
        return {"status": "not_found", "details": str(exc)}

    try:
        resultado = {
            "task_number": task_number,
            "reasignacion": legacy_task.get("reasignacion", ""),
            "proveedor": proveedor,
            "mecanico": mecanico,
            "telefono": telefono,
            "inf_vehiculo": inf_vehiculo,
            "fuente": fuente,
        }
        logger.info("Reasignación simulada para tarea %s", task_number)
        return {"status": "ok", "details": resultado}
    except Exception as exc:  # pragma: no cover - protección adicional
        logger.exception("Error durante la reasignación de %s", task_number)
        return {"status": "error", "details": str(exc)}


__all__ = ["reassign_by_task_number"]
