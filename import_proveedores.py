import os
import pandas as pd
import db

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
    # Obtiene la ruta absoluta del script y se añade el nombre del archivo Excel
    script_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(script_dir, "correos.xlsx")
    
    try:
        # Forzamos que la columna "ruc" se lea como string para preservar los ceros iniciales
        df = pd.read_excel(file_path, dtype={'ruc': str})
    except Exception as e:
        print(f"Error al leer el Excel: {e}")
        return

    # Se asume que el Excel tiene las columnas "name", "ruc" y "email".
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
    # Inicializamos la base de datos si no existe
    db.init_db()
    # Primero, eliminamos todos los registros actuales de la tabla
    reset_proveedores()
    # Luego, importamos los nuevos datos
    import_proveedores_from_excel()
