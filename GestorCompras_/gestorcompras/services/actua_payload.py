"""Normalización de payload para flujos de Actua Tareas."""

from __future__ import annotations

from typing import Any

ORIGIN_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "reasignacion": ("task_number",),
    "correos_masivos": ("task_number", "orden_compra", "proveedor"),
    "descargas_oc": ("task_number",),
}


def normalize_payload(task_number: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = dict(payload or {})
    task = str(task_number or payload.get("task_number") or payload.get("numero_tarea") or "").strip()
    out: dict[str, Any] = dict(payload)
    out["task_number"] = task
    out["numero_tarea"] = task

    # Alias comunes para orden de compra.
    oc = (
        payload.get("orden_compra")
        or payload.get("oc")
        or payload.get("numero_orden")
        or payload.get("orden")
        or ""
    )
    oc = str(oc).strip() if oc is not None else ""
    if oc:
        out["orden_compra"] = oc
        out["oc"] = oc
        out["numero_orden"] = oc
    return out


def missing_required_fields(origen: str, payload: dict[str, Any]) -> list[str]:
    required = ORIGIN_REQUIRED_FIELDS.get((origen or "").strip().lower(), ("task_number",))
    missing: list[str] = []
    for field in required:
        if not str(payload.get(field, "") or "").strip():
            missing.append(field)
    return missing
