from __future__ import annotations

import json
from typing import Any

from gestorcompras.services import db

VALID_ORIGINS = {"reasignacion", "descargas_oc", "correos_masivos"}


def _ensure_table() -> None:
    conn = db.get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS actua_bandeja (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                origen TEXT NOT NULL,
                task_number TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                consumed INTEGER DEFAULT 0
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def push(origen: str, tasks: list[dict[str, Any]]) -> int:
    _ensure_table()
    origen = (origen or "").strip().lower()
    if origen not in VALID_ORIGINS:
        raise ValueError(f"Origen no permitido: {origen}")

    conn = db.get_connection()
    inserted = 0
    try:
        cur = conn.cursor()
        for task in tasks:
            task_number = str(task.get("task_number", "")).strip()
            if not task_number:
                continue
            cur.execute(
                "INSERT INTO actua_bandeja (origen, task_number, payload_json, consumed) VALUES (?, ?, ?, 0)",
                (origen, task_number, json.dumps(task, ensure_ascii=False)),
            )
            inserted += 1
        conn.commit()
        return inserted
    finally:
        conn.close()


def list_pending(origen: str | None = None) -> list[dict[str, Any]]:
    _ensure_table()
    conn = db.get_connection()
    try:
        cur = conn.cursor()
        if origen:
            cur.execute(
                """
                SELECT id, origen, task_number, payload_json, created_at
                FROM actua_bandeja
                WHERE consumed=0 AND origen=?
                ORDER BY id
                """,
                (origen.strip().lower(),),
            )
        else:
            cur.execute(
                """
                SELECT id, origen, task_number, payload_json, created_at
                FROM actua_bandeja
                WHERE consumed=0
                ORDER BY id
                """
            )
        rows = cur.fetchall()
    finally:
        conn.close()

    data = []
    for row in rows:
        payload = json.loads(row[3] or "{}")
        data.append(
            {
                "id": row[0],
                "origen": row[1],
                "task_number": row[2],
                "payload": payload,
                "created_at": row[4],
            }
        )
    return data


def mark_consumed(ids: list[int]) -> None:
    if not ids:
        return
    _ensure_table()
    conn = db.get_connection()
    try:
        cur = conn.cursor()
        placeholders = ",".join("?" for _ in ids)
        cur.execute(f"UPDATE actua_bandeja SET consumed=1 WHERE id IN ({placeholders})", tuple(ids))
        conn.commit()
    finally:
        conn.close()


def clear(origen: str) -> None:
    _ensure_table()
    conn = db.get_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM actua_bandeja WHERE origen=?", (origen.strip().lower(),))
        conn.commit()
    finally:
        conn.close()
