import json
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

# Ruta correcta del archivo JSON
json_path = r"E:\Proyecto compras\GestorCompras\GestorCompras\bin\Debug\datos_automatizacion_temp.json"

# Cargar datos desde el JSON, asegurando que todas las claves sean minúsculas
try:
    with open(json_path, encoding="utf-8") as f:
        datos = json.load(f)
    datos = {k.lower(): v for k, v in datos.items()}  # Convertir claves a minúsculas
    print("Contenido del JSON cargado:", datos)  # Verificación
except FileNotFoundError:
    print(f"Error: No se encontró el archivo JSON en {json_path}")
    input("Presiona Enter para salir...")
    exit()
except json.JSONDecodeError:
    print("Error: El archivo JSON tiene un formato incorrecto.")
    input("Presiona Enter para salir...")
    exit()

# Obtener la categoría sin importar mayúsculas/minúsculas
categoria = datos.get("categoria", "").strip().lower()

# Obtener la tarea (ahora correctamente llamada "numerotarea")
numerotarea = datos.get("numerotarea", "").strip()

# Validar si la categoría está presente
if not categoria:
    print("Error: No se encontró la clave 'categoria' en el JSON o está vacía.")
    input("Presiona Enter para salir...")
    exit()

# Validar si la tarea está presente
if not numerotarea:
    print("Error: No se encontró la clave 'numerotarea' en el JSON o está vacía.")
    input("Presiona Enter para salir...")
    exit()

# Configurar Selenium con ChromeDriver
service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service)
wait = WebDriverWait(driver, 15)  # Espera explícita global

# URL de la página
url = "https://katuk.pro/management/tenders/posts"
driver.get(url)
time.sleep(5)

# 1. Hacer clic en el botón "Ingresar"
try:
    boton_ingresar = driver.find_element(By.CLASS_NAME, "katuk-sign-button")
    boton_ingresar.click()
    time.sleep(2)
except:
    print("No se encontró el botón de Ingresar.")

# 2. Ingresar email
try:
    email_input = driver.find_element(By.ID, "email")
    email_input.send_keys("jotoapanta@telconet.ec")
except:
    print("No se encontró el campo de email.")

# 3. Ingresar contraseña
try:
    password_input = driver.find_element(By.ID, "password")
    password_input.send_keys("3413620Heidan")
    password_input.send_keys(Keys.RETURN)  # Dar Enter para iniciar sesión
    time.sleep(3)
except:
    print("No se encontró el campo de contraseña.")

# 4. Hacer clic en la flecha desplegable
try:
    flecha_desplegable = driver.find_element(By.CLASS_NAME, "pi-chevron-down")
    flecha_desplegable.click()
    time.sleep(2)
except:
    print("No se encontró el icono de desplegable.")

# 5. Seleccionar "Telconet Latam"
try:
    telconet_opcion = driver.find_element(By.XPATH, "//div[@class='account-item-content']/span[contains(text(), 'Telconet Latam')]")
    telconet_opcion.click()
    time.sleep(2)
except:
    print("No se encontró la opción 'Telconet Latam'.")

# 6. Hacer clic en "Licitaciones"
try:
    licitaciones_link = driver.find_element(By.LINK_TEXT, "Licitaciones")
    licitaciones_link.click()
    time.sleep(3)
except:
    print("No se encontró el enlace de 'Licitaciones'.")

# 7. Hacer clic en "Omitir" antes de "Nueva Publicación"
try:
    boton_omitir = driver.find_element(By.XPATH, "//button[@data-test-id='button-skip']")
    boton_omitir.click()
    time.sleep(2)
except:
    print("No se encontró el botón de 'Omitir'.")

# 8. Hacer clic en "Nueva Publicación"
try:
    nueva_publicacion = driver.find_element(By.XPATH, "//span[contains(text(), 'Nueva Publicación')]")
    nueva_publicacion.click()
    time.sleep(2)
except:
    print("No se encontró el botón de 'Nueva Publicación'.")

# 9. Hacer clic en "Producto"
try:
    boton_producto = driver.find_element(By.XPATH, "//span[contains(text(), 'Producto')]")
    boton_producto.click()
    time.sleep(2)
except:
    print("No se encontró el botón de 'Producto'.")

# 10. Hacer clic en "Seleccionar Imagen"
try:
    seleccionar_imagen = driver.find_element(By.XPATH, "//div[@class='edit-wrapper']")
    seleccionar_imagen.click()
    time.sleep(2)
except:
    print("No se encontró el botón de 'Seleccionar Imagen'.")

# 11. Seleccionar la imagen según la categoría
try:
    if categoria in ["electrico", "obra civil"]:
        img_selector = "//img[@src='https://ktask.pro/document/visor/CATALOG/567f6ea9-4f9e-451b-90f7-2279eae14a57.png']"
    elif categoria == "camaras":
        img_selector = "//img[@src='https://ktask.pro/document/visor/CATALOG/7d42b8c2-dd7a-4210-983a-d9ddaf5c3d83.png']"
    else:
        raise ValueError("Categoría no reconocida en el JSON.")

    img_element = driver.find_element(By.XPATH, img_selector)
    img_element.click()
    time.sleep(2)
except:
    print("No se encontró la imagen de la categoría seleccionada.")

# 12. Hacer clic en "Aceptar"
try:
    boton_aceptar = driver.find_element(By.XPATH, "//span[contains(text(), 'Aceptar')]")
    boton_aceptar.click()
    time.sleep(2)
except:
    print("No se encontró el botón de 'Aceptar'.")

# 13. Ingresar el título según la categoría
try:
    title_input = driver.find_element(By.ID, "title")
    if categoria == "electrico":
        title_input.send_keys("MATERIAL ELECTRICO")
    elif categoria == "obra civil":
        title_input.send_keys("MATERIAL OBRA CIVIL")
    elif categoria == "camaras":
        title_input.send_keys("CAMARAS DE SEGURIDAD")
except:
    print("No se encontró el campo de título.")

# 14. Ingresar el número de tarea con un "#" antes y texto adicional
try:
    tarea_input = driver.find_element(By.CLASS_NAME, "ql-editor")
    tarea_input.send_keys(f"#{numerotarea}")
    tarea_input.send_keys(Keys.ENTER)  # Salto de línea
    tarea_input.send_keys("Se necesita adquirir lo siguiente:")
except:
    print("No se encontró el campo de tarea.")
    
# 15. Abrir el dropdown de tipo de adquisición
try:
    dropdown = wait.until(EC.presence_of_element_located((
        By.XPATH, 
        "//div[contains(@class,'p-dropdown') and .//label[text()='Tipo de Adquisición']]"
    )))
    dropdown.click()
except (NoSuchElementException, TimeoutException) as e:
    print(f"Error al encontrar dropdown de tipo de adquisición: {str(e)}")
    driver.save_screenshot('error_dropdown.png')


# 16. Seleccionar "Por Totalidad" con espera explícita
try:
    opcion_totalidad = wait.until(EC.element_to_be_clickable((
        By.XPATH,
        "//li[@aria-label='Por Totalidad']"
    )))
    opcion_totalidad.click()
except (NoSuchElementException, TimeoutException) as e:
    print(f"Error al seleccionar 'Por Totalidad': {str(e)}")
    driver.save_screenshot('error_totalidad.png')

# 17. Activar checkbox de términos y condiciones
try:
    checkbox = wait.until(EC.element_to_be_clickable((
        By.XPATH,
        "//div[contains(@class,'p-checkbox')]/following-sibling::label[contains(.,'Acepto términos y condiciones')]"
    )))
    
    # Verificar estado actual del checkbox
    if not checkbox.find_element(By.XPATH, "./preceding-sibling::div[contains(@class,'p-checkbox')]").get_attribute("aria-checked") == "true":
        checkbox.click()
except Exception as e:
    print(f"Error con el checkbox: {str(e)}")
    driver.save_screenshot('error_checkbox.png')

# 18. Validación final antes de cerrar
try:
    # Verificar que todos los elementos obligatorios están completos
    elementos_obligatorios = wait.until(EC.presence_of_all_elements_located((
        By.XPATH,
        "//*[contains(@class,'p-filled') or contains(@class,'p-checkbox-checked')]"
    )))
    print(f"Elementos obligatorios completados: {len(elementos_obligatorios)}")
except Exception as e:
    print(f"Validación fallida: {str(e)}")

# Mantener la ventana abierta
input("Presiona Enter para cerrar el navegador...")
driver.quit()