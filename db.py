import sqlite3
import os
import json

# Definición de la ruta base y creación del directorio para la base de datos.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "app.db")

def get_connection():
    """
    Retorna una conexión a la base de datos SQLite.
    
    Returns:
        sqlite3.Connection: Conexión establecida.
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
    # Tabla para la asignación única por departamento
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS config_assignment (
            department TEXT PRIMARY KEY,
            person TEXT NOT NULL
        )
    """)
    # Tabla para la configuración general de la aplicación
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS app_config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

# ------------------ Operaciones con Proveedores ------------------
def get_suppliers():
    """
    Retorna una lista de proveedores registrados.
    
    Returns:
        list of tuples: Cada tupla contiene (id, name, ruc, email).
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, ruc, email FROM suppliers")
    rows = cursor.fetchall()
    conn.close()
    return rows

def add_supplier(name, ruc, email):
    """
    Agrega o actualiza un proveedor en la base de datos.
    
    Args:
        name (str): Nombre del proveedor.
        ruc (str): RUC del proveedor.
        email (str): Correo electrónico del proveedor.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO suppliers (name, ruc, email) VALUES (?, ?, ?)", (name, ruc, email))
    conn.commit()
    conn.close()

def update_supplier(supplier_id, name, ruc, email):
    """
    Actualiza la información de un proveedor existente.
    
    Args:
        supplier_id (int): ID del proveedor.
        name (str): Nuevo nombre.
        ruc (str): Nuevo RUC.
        email (str): Nuevo correo electrónico.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE suppliers SET name=?, ruc=?, email=? WHERE id=?", (name, ruc, email, supplier_id))
    conn.commit()
    conn.close()

def delete_supplier(supplier_id):
    """
    Elimina un proveedor de la base de datos.
    
    Args:
        supplier_id (int): ID del proveedor a eliminar.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM suppliers WHERE id=?", (supplier_id,))
    conn.commit()
    conn.close()

# ------------------ Configuración de Asignación Única ------------------
def set_assignment_config(dept, person):
    """
    Inserta o actualiza la asignación de una persona a un departamento.
    
    Args:
        dept (str): Nombre del departamento.
        person (str): Nombre de la persona asignada.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO config_assignment (department, person) VALUES (?, ?)", (dept, person))
    conn.commit()
    conn.close()

def get_assignment_config_single():
    """
    Retorna la asignación actual como un diccionario.
    
    Returns:
        dict: Diccionario con {department: person}.
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

# ------------------ Gestión de Tareas Temporales ------------------
def clear_tasks_temp():
    """
    Elimina todas las tareas temporales almacenadas.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tasks_temp")
    conn.commit()
    conn.close()

def insert_task_temp(task_number, reasignacion, details_dict):
    """
    Inserta una tarea temporal en la base de datos.
    Los detalles se guardan en formato JSON para facilitar su manejo.
    Evita duplicados si ya existe el mismo task_number.
    
    Args:
        task_number (str): Número de tarea.
        reasignacion (str): Departamento o destinatario de la reasignación.
        details_dict (dict): Detalles de la tarea.
    
    Returns:
        bool: True si se insertó, False si ya existía.
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
    Retorna la lista de tareas temporales almacenadas en la base de datos.
    
    Returns:
        list: Cada elemento es un diccionario con keys: id, task_number, reasignacion, details.
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
    
    Args:
        task_id (int): ID de la tarea a eliminar.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tasks_temp WHERE id=?", (task_id,))
    conn.commit()
    conn.close()

# ------------------ Configuración General de la Aplicación ------------------
def get_config(key, default=None):
    """
    Retorna el valor de una clave en la configuración general.
    
    Args:
        key (str): Clave de configuración.
        default: Valor por defecto si la clave no existe.
    
    Returns:
        str: Valor asociado a la clave o el valor por defecto.
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
    Establece o actualiza un valor de configuración general.
    
    Args:
        key (str): Clave de configuración.
        value (str): Valor a almacenar.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO app_config (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()
