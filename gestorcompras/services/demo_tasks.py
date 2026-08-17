"""Operaciones de tareas limitadas al estado volátil de la aplicación."""

from __future__ import annotations

from gestorcompras.core.models import OperationResult, PurchaseTask, Supplier
from gestorcompras.demo import fixtures


class DemoTaskService:
    def __init__(self) -> None:
        self._tasks = {task.task_id: task for task in fixtures.tasks()}
        self._suppliers = {item.supplier_id: item for item in fixtures.suppliers()}

    def list_tasks(self) -> tuple[PurchaseTask, ...]:
        return tuple(self._tasks.values())

    def list_suppliers(self) -> tuple[Supplier, ...]:
        return tuple(self._suppliers.values())

    def reassign(self, task_id: str, supplier_id: str) -> OperationResult:
        task = self._require_task(task_id)
        supplier = self._suppliers.get(supplier_id)
        if supplier is None:
            raise KeyError("Proveedor demostrativo desconocido.")
        self._tasks[task_id] = task.reassigned(supplier_id)
        return OperationResult(
            ok=True,
            message=f"{task_id} reasignada a {supplier.name} en memoria.",
            reference=task_id,
        )

    def update(self, task_id: str) -> OperationResult:
        task = self._require_task(task_id)
        self._tasks[task_id] = task.completed()
        return OperationResult(
            ok=True,
            message=f"{task_id} actualizada mediante el flujo simulado.",
            reference=task_id,
        )

    def _require_task(self, task_id: str) -> PurchaseTask:
        task = self._tasks.get(task_id)
        if task is None:
            raise KeyError("Tarea demostrativa desconocida.")
        return task
