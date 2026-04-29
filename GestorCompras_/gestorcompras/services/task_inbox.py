from __future__ import annotations

import json
from typing import Any

from gestorcompras.services import db
from gestorcompras.services.actua_payload import normalize_payload

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
        cur.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_actua_bandeja_pending_unique
            ON actua_bandeja (origen, task_number)
            WHERE consumed=0
            """
        )
        conn.commit()
    finally:
        conn.close()


def push(origen: str, tasks: list[dict[str, Any]]) -> dict[str, int]:
    _ensure_table()
    origen = (origen or "").strip().lower()
    if origen not in VALID_ORIGINS:
        raise ValueError(f"Origen no permitido: {origen}")

    conn = db.get_connection()
    inserted = 0
    skipped_duplicates = 0
    try:
        cur = conn.cursor()
        for task in tasks:
            task_number = str(task.get("task_number", "")).strip()
            if not task_number:
                continue
            normalized = normalize_payload(task_number, task)
            task_number = normalized["task_number"]

            cur.execute(
                """
                SELECT 1
                FROM actua_bandeja
                WHERE origen=? AND task_number=? AND consumed=0
                LIMIT 1
                """,
                (origen, task_number),
            )
            already_pending = cur.fetchone() is not None
            if already_pending:
                skipped_duplicates += 1
                continue

            cur.execute(
                "INSERT INTO actua_bandeja (origen, task_number, payload_json, consumed) VALUES (?, ?, ?, 0)",
                (origen, task_number, json.dumps(normalized, ensure_ascii=False)),
            )
            inserted += 1
        conn.commit()
        return {
            "inserted": inserted,
            "skipped_duplicates": skipped_duplicates,
        }
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
