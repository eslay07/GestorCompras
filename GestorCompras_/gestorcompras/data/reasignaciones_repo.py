"""Acceso a datos para la tabla de reasignaciones de servicios."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from gestorcompras.services import db

_TABLE = "reasignaciones_servicios"

_COLUMNS = (
    "message_id",
    "fecha",
    "asunto",
    "task_number",
    "proveedor",
    "mecanico",
    "telefono",
    "inf_vehiculo",
    "correo_usuario",
    "raw_hash",
)


def _normalize_record(record: Dict[str, Any]) -> Dict[str, Any]:
    normalized = {key: record.get(key) for key in _COLUMNS}
    fecha = record.get("fecha")
    if isinstance(fecha, datetime):
        normalized["fecha"] = fecha.isoformat()
    return normalized


def upsert(record: Dict[str, Any]) -> Dict[str, Any]:
    if not record.get("message_id") and not record.get("raw_hash"):
        raise ValueError("Se requiere message_id o raw_hash para guardar la reasignación")

    normalized = _normalize_record(record)
    conn = db.get_connection()
    cur = conn.cursor()

    existing = None
    if normalized.get("message_id"):
        cur.execute(
            f"SELECT id FROM {_TABLE} WHERE message_id=?",
            (normalized["message_id"],),
        )
        existing = cur.fetchone()
    if existing is None and normalized.get("raw_hash"):
        cur.execute(
            f"SELECT id FROM {_TABLE} WHERE raw_hash=?",
            (normalized["raw_hash"],),
        )
        existing = cur.fetchone()

    if existing:
        set_clause = ", ".join(f"{col}=?" for col in _COLUMNS if col != "message_id")
        values = [normalized[col] for col in _COLUMNS if col != "message_id"]
        values.append(normalized.get("message_id"))
        cur.execute(
            f"UPDATE {_TABLE} SET {set_clause} WHERE message_id=?",
            values,
        )
        record_id = existing[0]
    else:
        placeholders = ",".join("?" for _ in _COLUMNS)
        cur.execute(
            f"INSERT OR IGNORE INTO {_TABLE} ({', '.join(_COLUMNS)}) VALUES ({placeholders})",
            [normalized[col] for col in _COLUMNS],
        )
        record_id = cur.lastrowid

    conn.commit()
    conn.close()
    record_copy = dict(record)
    record_copy["id"] = record_id
    return record_copy


__all__ = ["upsert"]
