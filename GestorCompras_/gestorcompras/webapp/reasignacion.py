import datetime
import imaplib
import email
import re
import time
import logging
from typing import Tuple

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from gestorcompras.services import db

logger = logging.getLogger(__name__)


def process_body(body: str):
    task_pattern = r'Tarea:\s+(\d+)\s+Reasignación a:\s+(.*?)\s+Datos relacionados:(.*?)\n(?=Tarea:|\Z)'
    tasks = re.findall(task_pattern, body, re.DOTALL)
    tasks_data = []
    for task_number, reasignacion, details in tasks:
        detail_pattern = r'- OC (\d+) \| (.*?) \| FAC\. (\S+) \| INGR\. (\S+)'
        details_list = re.findall(detail_pattern, details)
        task_info = {
            "task_number": task_number,
            "reasignacion": reasignacion,
            "details": [
                {"OC": oc, "Proveedor": supplier, "Factura": invoice, "Ingreso": ingreso}
                for oc, supplier, invoice, ingreso in details_list
            ],
        }
        tasks_data.append(task_info)
    return tasks_data


def load_tasks_from_email(email_address: str, email_password: str, date_input: str) -> Tuple[int, str]:
    """Carga tareas desde el correo y las guarda en la base de datos.
    Retorna (cantidad, mensaje)."""
    try:
        date_since = datetime.datetime.strptime(date_input, "%d/%m/%Y").strftime("%d-%b-%Y")
    except Exception:
        return 0, "Formato de fecha inválido. Use DD/MM/YYYY"

    imap_url = 'pop.telconet.ec'
    try:
        mail = imaplib.IMAP4_SSL(imap_url, 993)
        mail.login(email_address, email_password)
        mail.select("inbox")
    except Exception as e:
        return 0, f"Error de autenticación en correo: {e}"

    query = f'(FROM "omar777j@gmail.com" SINCE "{date_since}")'
    status, messages = mail.search(None, query)
    messages = messages[0].split()
    if not messages:
        mail.logout()
        return 0, f"No se encontraron correos desde {date_input}."

    loaded_count = 0
    for mail_id in messages:
        status, data = mail.fetch(mail_id, '(RFC822)')
        for response_part in data:
            if isinstance(response_part, tuple):
                try:
                    msg = email.message_from_bytes(response_part[1])
                    body = msg.get_payload(decode=True).decode()
                except Exception:
                    continue
                tasks_data = process_body(body)
                for task_info in tasks_data:
                    inserted = db.insert_task_temp(task_info["task_number"],
                                                   task_info["reasignacion"],
                                                   task_info["details"])
                    if inserted:
                        loaded_count += 1
    mail.logout()
    return loaded_count, f"Se cargaron {loaded_count} tareas (sin duplicados)."


def login_telcos(driver, username, password):
    driver.get('https://telcos.telconet.ec/inicio/?josso_back_to=http://telcos.telconet.ec/check&josso_partnerapp_host=telcos.telconet.ec')
    user_input = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.NAME, 'josso_username')))
    user_input.send_keys(username)
    password_input = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.NAME, 'josso_password')))
    password_input.send_keys(password)
    password_input.send_keys(Keys.RETURN)
    WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, 'spanTareasPersonales')))


def wait_clickable_or_error(driver, locator, description, timeout=30, retries=3):
    for intento in range(retries):
        try:
            return WebDriverWait(driver, timeout).until(EC.element_to_be_clickable(locator))
        except Exception as e:
            if intento == retries - 1:
                raise Exception(f"No se pudo encontrar {description}") from e
            time.sleep(1)


def process_task(driver, task):
    task_number = task["task_number"]
    dept = task["reasignacion"].strip().upper()
    assignments = db.get_assignment_config()
    empleado = assignments.get(dept, {}).get("person", "SIN ASIGNAR")
    dept_name = assignments.get(dept, {}).get("department", "")

    element = wait_clickable_or_error(driver, (By.ID, 'spanTareasPersonales'), 'el menú de tareas')
    driver.execute_script("arguments[0].click();", element)

    search_input = wait_clickable_or_error(driver, (By.CSS_SELECTOR, 'input[type="search"].form-control.form-control-sm'), 'el campo de búsqueda')
    search_input.clear()
    search_input.send_keys(task_number)
    search_input.send_keys(Keys.RETURN)

    time.sleep(1)
    try:
        wait_clickable_or_error(driver, (By.CSS_SELECTOR, 'span.glyphicon.glyphicon-step-forward'), 'el botón para abrir la tarea').click()
    except Exception:
        raise Exception(f"No se encontraron las tareas en la plataforma Telcos.\nTarea: {task_number}")

    time.sleep(1)
    comment_input = wait_clickable_or_error(driver, (By.ID, 'txtareaComentario'), 'el campo de comentarios')
    comment_input.clear()
    comment_input.send_keys(f"Departamento: {dept_name}\nEmpleado: {empleado}")

    submit_btn = wait_clickable_or_error(driver, (By.ID, 'btnGuardarAsignacion'), 'el botón de guardar')
    submit_btn.click()
    time.sleep(1)


def process_task_web(email_addr, email_pwd, task):
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    try:
        login_telcos(driver, email_addr, email_pwd)
        process_task(driver, task)
        return f"Tarea {task['task_number']} procesada"
    except Exception as e:
        return f"Error en tarea {task['task_number']}: {e}"
    finally:
        driver.quit()
