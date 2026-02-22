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
    try:
        cur = conn.cursor()

        existing_id = None
        if normalized.get("message_id"):
            cur.execute(
                f"SELECT id FROM {_TABLE} WHERE message_id=?",
                (normalized["message_id"],),
            )
            row = cur.fetchone()
            if row:
                existing_id = row[0]
        if existing_id is None and normalized.get("raw_hash"):
            cur.execute(
                f"SELECT id FROM {_TABLE} WHERE raw_hash=?",
                (normalized["raw_hash"],),
            )
            row = cur.fetchone()
            if row:
                existing_id = row[0]

        if existing_id is not None:
            # UPDATE por id (siempre válido, independientemente de cómo se encontró el registro)
            set_clause = ", ".join(f"{col}=?" for col in _COLUMNS)
            values = [normalized[col] for col in _COLUMNS]
            values.append(existing_id)
            cur.execute(
                f"UPDATE {_TABLE} SET {set_clause} WHERE id=?",
                values,
            )
            record_id = existing_id
        else:
            placeholders = ",".join("?" for _ in _COLUMNS)
            cur.execute(
                f"INSERT OR IGNORE INTO {_TABLE} ({', '.join(_COLUMNS)}) VALUES ({placeholders})",
                [normalized[col] for col in _COLUMNS],
            )
            record_id = cur.lastrowid

        conn.commit()
    finally:
        conn.close()

    record_copy = dict(record)
    record_copy["id"] = record_id
    return record_copy


__all__ = ["upsert"]
