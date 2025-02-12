from selenium import webdriver
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import time

# Usar webdriver-manager para manejar chromedriver automáticamente
service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service)

# URL de la página de inicio de sesión
url = 'https://telcos.telconet.ec/inicio/?josso_back_to=http://telcos.telconet.ec/check&josso_partnerapp_host=telcos.telconet.ec'

# Abre la página de inicio de sesión
driver.get(url)

# Tiempo de espera para que la página cargue completamente
time.sleep(2)

# Encuentra el campo de usuario por su atributo 'name' y completa el campo con el nombre de usuario
usuario_input = driver.find_element(By.NAME, 'josso_username')
usuario_input.send_keys('jotoapanta')  # Reemplaza 'tu_usuario' por tu nombre de usuario

# Encuentra el campo de contraseña por su atributo 'name' y completa el campo con la contraseña
password_input = driver.find_element(By.NAME, 'josso_password')
password_input.send_keys('Sebas3413620j7.')  # Reemplaza 'tu_contraseña' por tu contraseña

# Enviar el formulario presionando la tecla Enter
password_input.send_keys(Keys.RETURN)

# Tiempo para asegurarse de que la página cargue después de iniciar sesión
time.sleep(2)

# Hacer clic en el elemento <span> con el id "spanTareasPersonales"
span_tareas_personales = driver.find_element(By.ID, 'spanTareasPersonales')  # Usamos el id para encontrar el <span>
span_tareas_personales.click()


# Espera para ver el resultado
time.sleep(2)

# Ingresar datos en el campo de búsqueda (input)
campo_busqueda = driver.find_element(By.CSS_SELECTOR, 'input[type="search"].form-control.form-control-sm')
campo_busqueda.send_keys('121106675')  # Escribe 'Dato de prueba' en el campo de búsqueda

# Espera para ver el resultado
time.sleep(100)

