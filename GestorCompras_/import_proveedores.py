import os
import pandas as pd
from gestorcompras.services import db

# ============================================================
# SCRIPT PARA IMPORTAR PROVEEDORES DESDE UN ARCHIVO EXCEL
# Propósito: Reiniciar la tabla de proveedores y cargar nuevos registros
# desde un archivo Excel, preservando la integridad de los datos (como ceros en RUC).
# ============================================================

def reset_proveedores():
    """Elimina todos los registros de la tabla de proveedores."""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM suppliers")
        conn.commit()
        conn.close()
        print("Tabla de proveedores reiniciada (vacía).")
    except Exception as e:
        print(f"Error al resetear la tabla: {e}")

def import_proveedores_from_excel():
    """
    Importa proveedores desde un archivo Excel.
    
    Se asume que el Excel contiene las columnas "name", "ruc" y "email".
    Se fuerza la lectura de la columna 'ruc' como cadena para preservar ceros iniciales.
    """
    # Obtiene la ruta absoluta del script y compone la ruta del archivo Excel
    script_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(script_dir, "correos.xlsx")
    
    try:
        # Lee el Excel, forzando la columna "ruc" a tipo string
        df = pd.read_excel(file_path, dtype={'ruc': str})
    except Exception as e:
        print(f"Error al leer el Excel: {e}")
        return

    # Itera sobre cada fila del DataFrame para insertar el proveedor en la base de datos
    for index, row in df.iterrows():
        name = str(row.get("name", "")).strip()
        ruc = str(row.get("ruc", "")).strip()
        email = str(row.get("email", "")).strip()
        if name and ruc and email:
            try:
                db.add_supplier(name, ruc, email)
                print(f"Proveedor importado: {name} - {ruc} - {email}")
            except Exception as e:
                print(f"Error al insertar proveedor {name}: {e}")
        else:
            print(f"Fila {index} incompleta, se omite.")
    print("Importación de proveedores finalizada.")

if __name__ == '__main__':
    # Inicializa la base de datos si no existe
    db.init_db()
    # Reinicia la tabla de proveedores
    reset_proveedores()
    # Importa los nuevos datos de proveedores desde el Excel
    import_proveedores_from_excel()
