from __future__ import annotations

import json
from typing import Any

from gestorcompras.services import db

ACTUA_TAREAS_CARPETA_BASE = "ACTUA_TAREAS_CARPETA_BASE"


def _ensure_table() -> None:
    conn = db.get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS actua_flujos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL UNIQUE,
                mode TEXT NOT NULL,
                pasos_json TEXT NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def list_flujos(mode: str | None = None) -> list[dict[str, Any]]:
    _ensure_table()
    conn = db.get_connection()
    try:
        cur = conn.cursor()
        if mode:
            cur.execute(
                "SELECT id, nombre, mode, pasos_json, updated_at FROM actua_flujos WHERE mode=? ORDER BY nombre",
                (mode,),
            )
        else:
            cur.execute("SELECT id, nombre, mode, pasos_json, updated_at FROM actua_flujos ORDER BY nombre")
        rows = cur.fetchall()
    finally:
        conn.close()

    salida = []
    for row in rows:
        salida.append(
            {
                "id": row[0],
                "nombre": row[1],
                "mode": row[2],
                "pasos": json.loads(row[3] or "[]"),
                "updated_at": row[4],
            }
        )
    return salida


def load_flujo(flujo_id: int) -> dict[str, Any] | None:
    _ensure_table()
    conn = db.get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, nombre, mode, pasos_json, updated_at FROM actua_flujos WHERE id=?",
            (flujo_id,),
        )
        row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return {
        "id": row[0],
        "nombre": row[1],
        "mode": row[2],
        "pasos": json.loads(row[3] or "[]"),
        "updated_at": row[4],
    }


def save_flujo(nombre: str, mode: str, pasos: list[dict[str, Any]]) -> int:
    _ensure_table()
    payload = json.dumps(pasos, ensure_ascii=False)
    conn = db.get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO actua_flujos (nombre, mode, pasos_json, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(nombre) DO UPDATE SET
                mode=excluded.mode,
                pasos_json=excluded.pasos_json,
                updated_at=CURRENT_TIMESTAMP
            """,
            (nombre.strip(), mode.strip() or "general", payload),
        )
        conn.commit()
        cur.execute("SELECT id FROM actua_flujos WHERE nombre=?", (nombre.strip(),))
        row = cur.fetchone()
        return int(row[0])
    finally:
        conn.close()


def delete_flujo(flujo_id: int) -> None:
    _ensure_table()
    conn = db.get_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM actua_flujos WHERE id=?", (flujo_id,))
        conn.commit()
    finally:
        conn.close()


def get_carpeta_base(default: str = "") -> str:
    return db.get_config(ACTUA_TAREAS_CARPETA_BASE, default)


def set_carpeta_base(path: str) -> None:
    db.set_config(ACTUA_TAREAS_CARPETA_BASE, path or "")
