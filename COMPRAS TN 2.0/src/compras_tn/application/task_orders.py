"""Order associations shared by inbox, editor and one-pass workflow execution."""
from __future__ import annotations

import re

from compras_tn.domain.models import TaskRecord


def normalize_orders(rows: list[dict]) -> list[dict]:
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("La lista de órdenes no es válida; edítela nuevamente en la tabla.")
    result = []
    seen = {}
    for row in rows:
        number = str(row.get("order_number", "")).strip()
        supplier = str(row.get("supplier", "")).strip()
        raw = row.get("approvers") or []
        names = raw.split(",") if isinstance(raw, str) else raw
        approvers = list(dict.fromkeys(str(name).strip() for name in names if str(name).strip()))
        if not number and not supplier and not approvers:
            continue
        if number and not re.fullmatch(r"[0-9]{1,14}", number):
            raise ValueError("La OC debe contener solo números, hasta 14 dígitos.")
        if number in seen and number:
            previous = seen[number]
            if previous["supplier"] and supplier and previous["supplier"].casefold() != supplier.casefold():
                raise ValueError(f"La OC {number} tiene proveedores contradictorios.")
            previous["supplier"] = previous["supplier"] or supplier
            previous["approvers"] = list(dict.fromkeys(previous["approvers"] + approvers))
            continue
        item = dict(order_number=number, supplier=supplier, approvers=approvers)
        result.append(item)
        if number:
            seen[number] = item
    return result


def task_orders(task: TaskRecord) -> list[dict]:
    if "orders" in task.payload:
        return normalize_orders(task.payload["orders"])
    numbers = task.payload.get("order_numbers") or [n.strip() for n in task.order_number.split(",") if n.strip()]
    suppliers = task.payload.get("suppliers") or ([task.supplier] if task.supplier else [])
    # Old lists were independently deduplicated. Never invent pairings.
    if len(numbers) <= 1:
        return normalize_orders([dict(order_number=numbers[0] if numbers else "", supplier=task.supplier,
                                     approvers=task.payload.get("approvers") or task.payload.get("aprobadores", []))])
    return normalize_orders([dict(order_number=number, supplier=suppliers[0] if len(suppliers) == 1 else "") for number in numbers])


def missing_order_data(workflow, task: TaskRecord) -> list[str]:
    rows = task_orders(task)
    errors = []
    needed = set()
    defined = set()
    for step in workflow.steps:
        for token in ("orden_compra", "proveedor", "aprobadores"):
            if token not in defined and "{" + token + "}" in str(step.params):
                needed.add(token)
        if step.action_id in {"definir_variable", "capturar_dato"}:
            defined.add(step.params.get("nombre", ""))
    if needed and not rows:
        return [f"Tarea {task.task_number}: complete las órdenes y datos requeridos en la tabla."]
    for row in rows:
        for token, field in (("orden_compra", "order_number"), ("proveedor", "supplier"), ("aprobadores", "approvers")):
            if token in needed and not row[field]:
                errors.append(f"Tarea {task.task_number} · OC {row['order_number'] or 'sin número'}: falta {token}. Complete la tabla de órdenes.")
    return errors
