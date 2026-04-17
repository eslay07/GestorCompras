"""Repositorio para correos escaneados del módulo Actua. Tareas."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List

from gestorcompras.services import db

_TABLE = "actua_correos_escaneados"


def upsert(item: Dict[str, Any]) -> int:
    message_id = item.get("message_id")
    r_hash = item.get("raw_hash")
    if not message_id and not r_hash:
        raise ValueError("Se requiere message_id o raw_hash")

    fecha = item.get("fecha")
    if isinstance(fecha, datetime):
        fecha = fecha.isoformat()

    payload = json.dumps(item, default=str, ensure_ascii=False)
    conn = db.get_connection()
    try:
        cur = conn.cursor()
        existing_id = None
        if message_id:
            cur.execute(f"SELECT id FROM {_TABLE} WHERE message_id=?", (message_id,))
            row = cur.fetchone()
            if row:
                existing_id = row[0]
        if existing_id is None and r_hash:
            cur.execute(f"SELECT id FROM {_TABLE} WHERE raw_hash=?", (r_hash,))
            row = cur.fetchone()
            if row:
                existing_id = row[0]

        if existing_id is not None:
            cur.execute(
                f"UPDATE {_TABLE} SET fecha=?, task_number=?, asunto=?, remitente=?, "
                f"payload_json=? WHERE id=?",
                (fecha, item.get("task_number"), item.get("asunto"),
                 item.get("from", ""), payload, existing_id),
            )
            record_id = existing_id
        else:
            cur.execute(
                f"INSERT INTO {_TABLE} "
                f"(message_id, raw_hash, fecha, task_number, asunto, remitente, payload_json) "
                f"VALUES (?,?,?,?,?,?,?)",
                (message_id, r_hash, fecha, item.get("task_number"),
                 item.get("asunto"), item.get("from", ""), payload),
            )
            record_id = cur.lastrowid
        conn.commit()
        return record_id
    finally:
        conn.close()


def list_by_task(task_number: str) -> List[Dict[str, Any]]:
    conn = db.get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT id, payload_json, created_at FROM {_TABLE} WHERE task_number=? "
            f"ORDER BY fecha DESC",
            (task_number,),
        )
        results = []
        for row in cur.fetchall():
            data = json.loads(row[1])
            data["_db_id"] = row[0]
            data["_created_at"] = row[2]
            results.append(data)
        return results
    finally:
        conn.close()


def list_recent(limit: int = 100) -> List[Dict[str, Any]]:
    conn = db.get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT id, payload_json, created_at FROM {_TABLE} "
            f"ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        results = []
        for row in cur.fetchall():
            data = json.loads(row[1])
            data["_db_id"] = row[0]
            data["_created_at"] = row[2]
            results.append(data)
        return results
    finally:
        conn.close()


def delete(message_id: str) -> bool:
    conn = db.get_connection()
    try:
        cur = conn.cursor()
        cur.execute(f"DELETE FROM {_TABLE} WHERE message_id=?", (message_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def clear() -> int:
    conn = db.get_connection()
    try:
        cur = conn.cursor()
        cur.execute(f"DELETE FROM {_TABLE}")
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


__all__ = ["upsert", "list_by_task", "list_recent", "delete", "clear"]
