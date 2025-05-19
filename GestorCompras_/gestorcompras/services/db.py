import sqlite3
import os
import json

# Definición de rutas y creación de carpeta de datos
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "app.db")

def get_connection():
    """
    Retorna una conexión a la base de datos SQLite.
    """
    return sqlite3.connect(DB_PATH)

def init_db():
    """
    Inicializa la base de datos creando las tablas necesarias si no existen.
    """
    conn = get_connection()
    cursor = conn.cursor()
    # Tabla de proveedores
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            ruc TEXT UNIQUE NOT NULL,
            email TEXT NOT NULL
        )
    """)
    # Tabla para tareas temporales
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks_temp (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_number TEXT NOT NULL,
            reasignacion TEXT NOT NULL,
            details TEXT NOT NULL
        )
    """)
    # Configuración de asignación: solo 1 persona por departamento
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS config_assignment (
            department TEXT PRIMARY KEY,
            person TEXT NOT NULL
        )
    """)
    # Tabla para configuración general de la aplicación
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS app_config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

# ------------------ Proveedores ------------------
def get_suppliers():
    """
    Retorna una lista con los proveedores registrados.
    Cada elemento es una tupla (id, name, ruc, email).
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, ruc, email FROM suppliers")
    rows = cursor.fetchall()
    conn.close()
    return rows

def add_supplier(name, ruc, email):
    """
    Agrega o actualiza un proveedor en la tabla.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO suppliers (name, ruc, email) VALUES (?, ?, ?)", (name, ruc, email))
    conn.commit()
    conn.close()

def update_supplier(supplier_id, name, ruc, email):
    """
    Actualiza la información de un proveedor.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE suppliers SET name=?, ruc=?, email=? WHERE id=?", (name, ruc, email, supplier_id))
    conn.commit()
    conn.close()

def delete_supplier(supplier_id):
    """
    Elimina un proveedor de la base de datos.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM suppliers WHERE id=?", (supplier_id,))
    conn.commit()
    conn.close()

# ------------------ Configuración de Asignación Única ------------------
def set_assignment_config(dept, person):
    """
    Inserta o actualiza la asignación para un departamento (solo 1 persona).
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO config_assignment (department, person) VALUES (?, ?)", (dept, person))
    conn.commit()
    conn.close()

def get_assignment_config_single():
    """
    Retorna un diccionario con la asignación única: {department: person}.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT department, person FROM config_assignment")
    rows = cursor.fetchall()
    conn.close()
    config = {}
    for dept, person in rows:
        config[dept] = person
    return config

# ------------------ Tareas Temporales ------------------
def clear_tasks_temp():
    """
    Elimina todas las tareas temporales registradas.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tasks_temp")
    conn.commit()
    conn.close()

def insert_task_temp(task_number, reasignacion, details_dict):
    """
    Inserta una tarea temporal. Los detalles se guardan en formato JSON.
    Evita duplicados (no inserta la misma task_number dos veces).
    Retorna True si se insertó la tarea, False si ya existía.
    """
    details_json = json.dumps(details_dict)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM tasks_temp WHERE task_number=?", (task_number,))
    count = cursor.fetchone()[0]
    inserted = False
    if count == 0:
        cursor.execute("INSERT INTO tasks_temp (task_number, reasignacion, details) VALUES (?, ?, ?)",
                       (task_number, reasignacion, details_json))
        inserted = True
    conn.commit()
    conn.close()
    return inserted

def get_tasks_temp():
    """
    Retorna la lista de tareas temporales registradas.
    Cada tarea es un diccionario con las claves: id, task_number, reasignacion, details.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, task_number, reasignacion, details FROM tasks_temp")
    rows = cursor.fetchall()
    conn.close()
    tasks = []
    for row in rows:
        tasks.append({
            "id": row[0],
            "task_number": row[1],
            "reasignacion": row[2],
            "details": json.loads(row[3])
        })
    return tasks

def delete_task_temp(task_id):
    """
    Elimina una tarea temporal específica.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tasks_temp WHERE id=?", (task_id,))
    conn.commit()
    conn.close()

# ------------------ Configuración General (app_config) ------------------
def get_config(key, default=None):
    """
    Retorna el valor asociado a la clave en app_config. Si no existe, retorna default.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM app_config WHERE key=?", (key,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return row[0]
    return default

def set_config(key, value):
    """
    Establece o actualiza el valor asociado a la clave en app_config.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO app_config (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()
