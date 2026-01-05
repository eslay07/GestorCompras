import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from gestorcompras.services import db
import threading
import time
import datetime
import imaplib
import email
import re
import logging
from typing import Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SERVICIOS_HEADLESS_KEY = "SERVICIOS_HEADLESS"
SERVICIOS_MENSAJE_KEY = "SERVICIOS_REASIGNACION_MSG"
SERVICIOS_DEPARTAMENTO_KEY = "SERVICIOS_DEPARTAMENTO"
SERVICIOS_USUARIO_KEY = "SERVICIOS_USUARIO"

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains


def center_window(win: tk.Tk | tk.Toplevel):
    win.update_idletasks()
    w = win.winfo_width()
    h = win.winfo_height()
    x = (win.winfo_screenwidth() // 2) - (w // 2)
    y = (win.winfo_screenheight() // 2) - (h // 2)
    win.geometry(f"{w}x{h}+{x}+{y}")

def process_body(body):
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
            ]
        }
        tasks_data.append(task_info)
    return tasks_data


def _normalize_template(template: str | None) -> str:
    if template is None or not template.strip():
        template = db.get_config(SERVICIOS_MENSAJE_KEY, 'Taller Asignado "{proveedor}"')
    return template


def _provider_from_details(task: dict[str, Any]) -> str:
    detalles = task.get("details") or []
    if isinstance(detalles, list):
        for detalle in detalles:
            if isinstance(detalle, dict):
                proveedor = detalle.get("Proveedor") or detalle.get("supplier")
                if proveedor:
                    return str(proveedor)
    return "N/D"


class DateDialog(simpledialog.Dialog):
    """Ventana para seleccionar una fecha con flechas."""

    def body(self, master):
        self.cur_date = datetime.date.today()
        ttk.Label(master, text="Ingresa la fecha (DD/MM/YYYY):").pack()
        ttk.Label(
            master,
            text=(
                "Los correos solo se podran buscar hasta maximo 15 dias atras "
                "debido a que el servidor de telconet los borra en ese periodo de tiempo"
            ),
            wraplength=300,
        ).pack(pady=(0, 5))
        self.entry = ttk.Entry(master)
        self.entry.pack()
        self._update()
        self.entry.bind("<Up>", self._prev)
        self.entry.bind("<Down>", self._next)
        return self.entry

    def _update(self):
        self.entry.delete(0, tk.END)
        self.entry.insert(0, self.cur_date.strftime("%d/%m/%Y"))

    def _prev(self, event):
        self.cur_date -= datetime.timedelta(days=1)
        self._update()
        return "break"

    def _next(self, event):
        self.cur_date += datetime.timedelta(days=1)
        self._update()
        return "break"

    def apply(self):
        self.result = self.entry.get()

def cargar_tareas_correo(email_address, email_password, window):
    dialog = DateDialog(window)
    date_input = dialog.result
    if not date_input:
        messagebox.showwarning("Advertencia", "No se ingresó fecha.", parent=window)
        return
    try:
        date_since = datetime.datetime.strptime(date_input, "%d/%m/%Y").strftime("%d-%b-%Y")
    except Exception:
        messagebox.showerror("Error", "Formato de fecha inválido. Use DD/MM/YYYY", parent=window)
        return

    task_filters = []

    imap_url = 'pop.telconet.ec'
    try:
        mail = imaplib.IMAP4_SSL(imap_url, 993)
        mail.login(email_address, email_password)
        mail.select("inbox")
    except Exception as e:
        messagebox.showerror("Error", f"Error de autenticación en correo: {e}", parent=window)
        return

    query = f'(FROM "omar777j@gmail.com" SINCE "{date_since}")'
    status, messages = mail.search(None, query)
    messages = messages[0].split()
    if not messages:
        messagebox.showinfo("Información", f"No se encontraron correos desde {date_input}.", parent=window)
        mail.logout()
        return

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
                    if task_filters and task_info["task_number"] not in task_filters:
                        continue
                    inserted = db.insert_task_temp(task_info["task_number"],
                                                   task_info["reasignacion"],
                                                   task_info["details"])
                    if inserted:
                        loaded_count += 1
                        logger.debug("Tasks after insert: %s", db.get_tasks_temp())
    mail.logout()
    messagebox.showinfo("Información", f"Se cargaron {loaded_count} tareas (sin duplicados).", parent=window)

def login_telcos(driver, username, password):
    driver.get('https://telcos.telconet.ec/inicio/?josso_back_to=http://telcos.telconet.ec/check&josso_partnerapp_host=telcos.telconet.ec')
    user_input = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.NAME, 'josso_username')))
    user_input.send_keys(username)
    password_input = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.NAME, 'josso_password')))
    password_input.send_keys(password)
    password_input.send_keys(Keys.RETURN)
    WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, 'spanTareasPersonales')))


def wait_clickable_or_error(driver, locator, parent, description, timeout=30, retries=3):
    """Espera que un elemento sea clickeable reintentando varias veces."""
    for intento in range(retries):
        try:
            return WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable(locator)
            )
        except Exception as e:
            if intento == retries - 1:
                raise Exception(f"No se pudo encontrar {description}") from e
            time.sleep(1)

def process_task(driver, task, parent_window):
    task_number = task["task_number"]
    dept = task["reasignacion"].strip().upper()
    assignments = db.get_assignment_config()
    empleado = assignments.get(dept, {}).get("person", "SIN ASIGNAR")
    dept_name = assignments.get(dept, {}).get("department", "")

    element = wait_clickable_or_error(driver, (By.ID, 'spanTareasPersonales'), parent_window, 'el menú de tareas')
    driver.execute_script("arguments[0].click();", element)

    search_input = wait_clickable_or_error(
        driver,
        (By.CSS_SELECTOR, 'input[type="search"].form-control.form-control-sm'),
        parent_window,
        'el campo de búsqueda'
    )
    search_input.clear()
    search_input.send_keys(task_number)
    search_input.send_keys(Keys.RETURN)

    try:
        time.sleep(0.5)
        wait_clickable_or_error(
            driver,
            (By.CSS_SELECTOR, 'span.glyphicon.glyphicon-step-forward'),
            parent_window,
            'el botón para abrir la tarea'
        ).click()
    except Exception:
        # Se lanza la excepción con el mensaje exacto, sin mostrarla inmediatamente
        raise Exception(f"No se encontraron las tareas en la plataforma Telcos.\nTarea: {task_number}")

    time.sleep(1)
    comment_input = wait_clickable_or_error(
        driver, (By.ID, 'txtObservacionTarea'), parent_window, 'el campo de comentario')
    comment_input.send_keys('SE RECIBE LA MERCADERIA')
    time.sleep(1)
    wait_clickable_or_error(
        driver, (By.ID, 'btnGrabarEjecucionTarea'), parent_window, 'el botón Grabar Ejecución').click()
    time.sleep(2)
    wait_clickable_or_error(driver, (By.ID, 'btnSmsCustomOk'), parent_window, 'la confirmación inicial').click()
    time.sleep(2)

    for detail in task["details"]:
        tracking_button = wait_clickable_or_error(
            driver,
            (By.CSS_SELECTOR, "button[onclick*='mostrarIngresoSeguimiento']"),
            parent_window,
            'el botón de seguimiento'
        )
        tracking_button.click()
        time.sleep(2)
        tracking_input = wait_clickable_or_error(
            driver,
            (By.ID, 'txtSeguimientoTarea'),
            parent_window,
            'el campo de seguimiento'
        )
        tracking_message = f"SE INGRESA LA FACTURA {detail['Factura']} CON EL INGRESO {detail['Ingreso']}"
        tracking_input.clear()
        tracking_input.send_keys(tracking_message)
        time.sleep(2)
        wait_clickable_or_error(driver, (By.ID, 'btnIngresoSeguimiento'), parent_window, 'el botón Ingreso Seguimiento').click()
        time.sleep(2)
        wait_clickable_or_error(driver, (By.ID, 'btnSmsCustomOk'), parent_window, 'la confirmación de seguimiento').click()
        time.sleep(2)

    wait_clickable_or_error(
        driver,
        (By.CSS_SELECTOR, 'span.glyphicon.glyphicon-dashboard'),
        parent_window,
        'el botón de reasignar'
    ).click()
    time.sleep(2)
    department_input = wait_clickable_or_error(
        driver,
        (By.ID, 'txtDepartment'),
        parent_window,
        'el campo Departamento'
    )
    department_input.clear()
    department_input.send_keys(dept_name)
    time.sleep(1)
    #elemento para pruebas compras
    #department_input.send_keys(Keys.UP, Keys.RETURN)
    #////////////elementopara produccion bodega
    department_input.send_keys(Keys.DOWN, Keys.RETURN)
    time.sleep(2)
    department_input.send_keys(Keys.TAB)
    time.sleep(2)
    employee_input = WebDriverWait(driver, 20).until(
        EC.element_to_be_clickable((By.NAME, 'txtEmpleado'))
    )
    employee_input.click()
    employee_input.send_keys(empleado)
    time.sleep(1)
    employee_input.send_keys(Keys.DOWN, Keys.RETURN)
    time.sleep(2)
    employee_input.send_keys(Keys.TAB)
    time.sleep(2)
    observation_textarea = wait_clickable_or_error(
        driver,
        (By.ID, 'txtaObsTareaFinalReasigna'),
        parent_window,
        'el área de observación'
    )
    observation_textarea.send_keys('TRABAJO REALIZADO')
    try:
        WebDriverWait(driver, 20).until(
            EC.visibility_of_element_located((By.ID, "modalReasignarTarea"))
        )
    except Exception as e:
        raise Exception("No se abrió la ventana de reasignación") from e
    boton = wait_clickable_or_error(
        driver,
        (By.ID, "btnGrabarReasignaTarea"),
        parent_window,
        'el botón Guardar'
    )
    from selenium.webdriver.common.action_chains import ActionChains
    ActionChains(driver).move_to_element(boton).perform()
    boton.click()
    final_confirm_button = WebDriverWait(driver, 20).until(
        EC.element_to_be_clickable((By.ID, 'btnMensajeFinTarea'))
    )
    final_confirm_button.click()
    time.sleep(2)


def process_task_servicios(driver, task, parent_window):
    task_number = task["task_number"]
    dept = str(task.get("reasignacion", "")).strip().upper()
    assignments = db.get_assignment_config()
    assignment_info = assignments.get(dept, {})

    dept_name = (
        task.get("department_override")
        or task.get("department")
        or assignment_info.get("department")
        or db.get_config(SERVICIOS_DEPARTAMENTO_KEY, "")
    )
    empleado = (
        task.get("employee_override")
        or task.get("empleado")
        or assignment_info.get("person")
        or db.get_config(SERVICIOS_USUARIO_KEY, "SIN ASIGNAR")
    )

    if not dept_name or not empleado:
        raise Exception(
            "No existe configuración de departamento o usuario para la reasignación de la tarea "
            f"{task_number}"
        )

    proveedor = task.get("proveedor") or _provider_from_details(task)
    mecanico = task.get("mecanico", "")
    telefono = task.get("telefono", "")
    inf_vehiculo = task.get("inf_vehiculo", "")
    template = _normalize_template(task.get("comentario_template"))
    variables = {
        "proveedor": proveedor or "N/D",
        "mecanico": mecanico or "N/D",
        "telefono": telefono or "N/D",
        "inf_vehiculo": inf_vehiculo or "N/D",
        "task_number": task_number,
    }
    try:
        comentario = template.format(**variables).strip()
    except Exception:
        comentario = template.replace("{proveedor}", variables["proveedor"]).strip()

    element = wait_clickable_or_error(driver, (By.ID, 'spanTareasPersonales'), parent_window, 'el menú de tareas')
    driver.execute_script("arguments[0].click();", element)

    search_input = wait_clickable_or_error(
        driver,
        (By.CSS_SELECTOR, 'input[type="search"].form-control.form-control-sm'),
        parent_window,
        'el campo de búsqueda'
    )
    search_input.clear()
    search_input.send_keys(task_number)
    search_input.send_keys(Keys.RETURN)

    try:
        time.sleep(0.5)
        wait_clickable_or_error(
            driver,
            (By.CSS_SELECTOR, 'span.glyphicon.glyphicon-step-forward'),
            parent_window,
            'el botón para abrir la tarea'
        ).click()
    except Exception:
        # Se lanza la excepción con el mensaje exacto, sin mostrarla inmediatamente
        raise Exception(f"No se encontraron las tareas en la plataforma Telcos.\nTarea: {task_number}")

    time.sleep(1)
    comment_input = wait_clickable_or_error(
        driver, (By.ID, 'txtObservacionTarea'), parent_window, 'el campo de comentario')
    comment_input.send_keys(comentario)
    time.sleep(1)
    wait_clickable_or_error(
        driver, (By.ID, 'btnGrabarEjecucionTarea'), parent_window, 'el botón Grabar Ejecución').click()
    time.sleep(2)
    wait_clickable_or_error(driver, (By.ID, 'btnSmsCustomOk'), parent_window, 'la confirmación inicial').click()
    time.sleep(2)

    wait_clickable_or_error(
        driver,
        (By.CSS_SELECTOR, 'span.glyphicon.glyphicon-dashboard'),
        parent_window,
        'el botón de reasignar'
    ).click()
    time.sleep(2)
    department_input = wait_clickable_or_error(
        driver,
        (By.ID, 'txtDepartment'),
        parent_window,
        'el campo Departamento'
    )
    department_input.clear()
    department_input.send_keys(dept_name)
    time.sleep(1)
    #elemento para pruebas compras
    #department_input.send_keys(Keys.UP, Keys.RETURN)
    #////////////elementopara produccion bodega
    department_input.send_keys(Keys.DOWN, Keys.RETURN)
    time.sleep(2)
    department_input.send_keys(Keys.TAB)
    time.sleep(2)
    employee_input = WebDriverWait(driver, 20).until(
        EC.element_to_be_clickable((By.NAME, 'txtEmpleado'))
    )
    employee_input.click()
    employee_input.send_keys(empleado)
    time.sleep(1)
    employee_input.send_keys(Keys.DOWN, Keys.RETURN)
    time.sleep(2)
    employee_input.send_keys(Keys.TAB)
    time.sleep(2)
    observation_textarea = wait_clickable_or_error(
        driver,
        (By.ID, 'txtaObsTareaFinalReasigna'),
        parent_window,
        'el área de observación'
    )
    observation_textarea.send_keys('TALLER ASIGNADO')
    try:
        WebDriverWait(driver, 20).until(
            EC.visibility_of_element_located((By.ID, "modalReasignarTarea"))
        )
    except Exception as e:
        raise Exception("No se abrió la ventana de reasignación") from e
    boton = wait_clickable_or_error(
        driver,
        (By.ID, "btnGrabarReasignaTarea"),
        parent_window,
        'el botón Guardar'
    )
    from selenium.webdriver.common.action_chains import ActionChains
    ActionChains(driver).move_to_element(boton).perform()
    boton.click()
    final_confirm_button = WebDriverWait(driver, 20).until(
        EC.element_to_be_clickable((By.ID, 'btnMensajeFinTarea'))
    )
    final_confirm_button.click()
    time.sleep(2)

def open_reasignacion(master, email_session):
    window = tk.Toplevel(master)
    window.title("Reasignación de Tareas")
    window.geometry("820x650")
    window.transient(master)
    window.grab_set()
    center_window(window)

    def on_close():
        db.clear_tasks_temp()
        window.destroy()
    window.protocol("WM_DELETE_WINDOW", on_close)

    banner = ttk.Label(window, text="Sistema de automatización - compras")
    banner.configure(font=("Helvetica", 24, "bold"), foreground="#222222")
    banner.pack(pady=(20,10))

    top_frame = ttk.Frame(window, style="MyFrame.TFrame", padding=5)
    top_frame.pack(fill="x")

    btn_cargar = ttk.Button(
        top_frame,
        text="Buscar Tareas",
        style="MyButton.TButton",
        command=lambda: [cargar_tareas_correo(email_session["address"], email_session["password"], window),
                         actualizar_tareas()]
    )
    btn_cargar.pack(side="left", padx=5)

    lbl_title = ttk.Label(top_frame, text="(Se buscan tareas notificadas mediante correo)", style="MyLabel.TLabel")
    lbl_title.pack(side="left", padx=13)

    main_frame = ttk.Frame(window, style="MyFrame.TFrame", padding=5)
    main_frame.pack(fill="both", expand=True)

    task_lf = ttk.LabelFrame(main_frame, text="Listado de Tareas",
                             style="MyLabelFrame.TLabelframe", padding=5)
    task_lf.pack(fill="both", expand=True)

    canvas = tk.Canvas(task_lf, background="#FFFFFF", highlightthickness=1,
                       highlightbackground="#CCCCCC")
    scrollbar = ttk.Scrollbar(task_lf, orient="vertical", command=canvas.yview)
    tasks_frame = ttk.Frame(canvas, style="MyFrame.TFrame")

    def on_frame_configure(event):
        canvas.configure(scrollregion=canvas.bbox("all"))
    tasks_frame.bind("<Configure>", on_frame_configure)

    canvas.create_window((0, 0), window=tasks_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    bottom_frame = ttk.Frame(window, style="MyFrame.TFrame", padding=5)
    bottom_frame.pack(fill="x")

    task_vars = {}
    select_all_var = tk.BooleanVar(value=False)
    headless_var = tk.BooleanVar(value=db.get_config(SERVICIOS_HEADLESS_KEY, "1") != "0")

    def toggle_headless(*_args):
        db.set_config(SERVICIOS_HEADLESS_KEY, "1" if headless_var.get() else "0")

    headless_var.trace_add("write", toggle_headless)

    def toggle_select_all():
        new_val = select_all_var.get()
        for t_id, (var, _) in task_vars.items():
            var.set(new_val)

    chk_select_all = ttk.Checkbutton(
        bottom_frame,
        text="Marcar todas",
        style="MyCheckbutton.TCheckbutton",
        variable=select_all_var,
        command=toggle_select_all
    )
    chk_select_all.pack(side="left", padx=5)

    ttk.Checkbutton(
        bottom_frame,
        text="Ejecutar navegador en modo oculto (headless)",
        style="MyCheckbutton.TCheckbutton",
        variable=headless_var,
    ).pack(side="left", padx=5)

    process_btn = ttk.Button(
        bottom_frame,
        text="Reasignar Tareas",
        style="MyButton.TButton"
    )
    process_btn.pack(side="right")


    def actualizar_tareas():
        all_tasks = db.get_tasks_temp()
        logger.debug("Tareas en DB: %s", all_tasks)

        for widget in tasks_frame.winfo_children():
            widget.destroy()
        task_vars.clear()
        select_all_var.set(False)

        if not all_tasks:
            no_tareas_label = ttk.Label(tasks_frame, text="No se encontraron tareas.", style="MyLabel.TLabel")
            no_tareas_label.pack(pady=20)
            process_btn.pack_forget()
            return
        else:
            cantidad_label = ttk.Label(tasks_frame,
                                       text=f"Se encontraron {len(all_tasks)} tareas:",
                                       style="MyLabel.TLabel")
            cantidad_label.pack(pady=(0,10))

        for task in all_tasks:
            var = tk.BooleanVar(value=False)
            chk_text = f"Tarea {task['task_number']} - {task['reasignacion']}"
            chk = ttk.Checkbutton(tasks_frame, text=chk_text,
                                  style="MyCheckbutton.TCheckbutton",
                                  variable=var)
            chk.pack(anchor="w", pady=2)
            task_vars[task["id"]] = (var, chk)

        process_btn.pack(side="right")
        canvas.update_idletasks()
        canvas.yview_moveto(0.0)

    def process_tasks():
        if not any(var.get() for var, _ in task_vars.values()):
            messagebox.showinfo(
                "Resultado", "No se ha seleccionado ninguna tarea.", parent=window
            )
            return

        process_btn.config(state="disabled", text="Procesando...")
        window.update()

        errors: list[str] = []
        tasks_in_db = db.get_tasks_temp()
        tasks_dict = {t["id"]: t for t in tasks_in_db}

        service = Service(ChromeDriverManager().install())
        chrome_options = Options()
        if headless_var.get():
            chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        prefs = {"profile.managed_default_content_settings.images": 2}
        chrome_options.add_experimental_option("prefs", prefs)
        driver = webdriver.Chrome(service=service, options=chrome_options)

        telcos_username = email_session["address"].split("@")[0]
        telcos_password = email_session["password"]
        login_telcos(driver, telcos_username, telcos_password)

        try:
            for t_id, (var, _) in task_vars.items():
                if var.get():
                    task = tasks_dict[t_id]
                    try:
                        process_task(driver, task, window)
                        db.delete_task_temp(t_id)
                    except Exception as e:
                        errors.append(str(e))
        finally:
            driver.quit()

        if errors:
            summary = "Algunas tareas no fueron reasignadas:\n" + "\n".join(errors)
        else:
            summary = "Tareas procesadas exitosamente."
        messagebox.showinfo("Resultado", summary, parent=window)

        process_btn.config(state="normal", text="Reasignar Tareas")
        actualizar_tareas()
        window.destroy()

    process_btn.configure(command=process_tasks)
    actualizar_tareas()

