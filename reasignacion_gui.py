import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import db
import threading
import time
import datetime
import imaplib
import email
import re

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains

def process_body(body):
    """
    Procesa el cuerpo del correo para extraer la información de cada tarea.
    
    Busca mediante expresiones regulares el número de tarea, el destinatario
    de la reasignación y los detalles asociados (OC, Proveedor, Factura, Ingreso).
    
    Args:
        body (str): Texto del correo.
        
    Returns:
        list: Lista de diccionarios, cada uno con los datos de una tarea.
    """
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

def cargar_tareas_correo(email_address, email_password, window):
    """
    Solicita al usuario una fecha y opcionalmente filtros de tareas, y luego carga las tareas
    notificadas por correo. Se conecta al servidor IMAP, busca correos desde la fecha especificada,
    procesa cada mensaje y almacena las tareas en la base de datos.
    
    Args:
        email_address (str): Dirección de correo.
        email_password (str): Contraseña del correo.
        window (tk.Tk o tk.Toplevel): Ventana padre para diálogos.
    """
    date_input = simpledialog.askstring("Fecha", "Ingresa la fecha (DD/MM/YYYY):", parent=window)
    if not date_input:
        messagebox.showwarning("Advertencia", "No se ingresó fecha.", parent=window)
        return
    try:
        date_since = datetime.datetime.strptime(date_input, '%d/%m/%Y').strftime('%d-%b-%Y')
    except Exception:
        messagebox.showerror("Error", "Formato de fecha inválido. Use DD/MM/YYYY", parent=window)
        return

    filtro_str = simpledialog.askstring("Filtro de Tareas", "Números de tarea separados por comas (opcional):", parent=window)
    if filtro_str:
        task_filters = [x.strip() for x in filtro_str.split(",") if x.strip()]
    else:
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
                        print("DEBUG tras insert:", db.get_tasks_temp())
    mail.logout()
    messagebox.showinfo("Información", f"Se cargaron {loaded_count} tareas (sin duplicados).", parent=window)

def login_telcos(driver, username, password):
    """
    Realiza el login en el portal de Telcos utilizando Selenium.
    
    Args:
        driver (webdriver.Chrome): Instancia del navegador.
        username (str): Nombre de usuario (sin dominio).
        password (str): Contraseña de acceso.
    """
    driver.get('https://telcos.telconet.ec/inicio/?josso_back_to=http://telcos.telconet.ec/check&josso_partnerapp_host=telcos.telconet.ec')
    user_input = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.NAME, 'josso_username')))
    user_input.send_keys(username)
    password_input = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.NAME, 'josso_password')))
    password_input.send_keys(password)
    password_input.send_keys(Keys.RETURN)
    WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, 'spanTareasPersonales')))

def process_task(task, email_session):
    """
    Procesa una tarea: realiza login en Telcos, busca la tarea,
    ingresa los datos requeridos y finaliza la reasignación.
    
    Args:
        task (dict): Diccionario con información de la tarea.
        email_session (dict): Diccionario con datos de la sesión de correo.
    """
    service = Service(ChromeDriverManager().install())
    chrome_options = Options()
    # Opción headless comentada para visualizar el navegador si se requiere
    # chrome_options.add_argument("--headless")
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
    
    task_number = task["task_number"]
    dept = task["reasignacion"].strip().upper()
    assignments = db.get_assignment_config_single()
    empleado = assignments[dept] if (dept in assignments and assignments[dept].strip()) else "SIN ASIGNAR"
    
    element = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.ID, 'spanTareasPersonales')))
    driver.execute_script("arguments[0].click();", element)
    
    search_input = WebDriverWait(driver, 20).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, 'input[type="search"].form-control.form-control-sm'))
    )
    search_input.clear()
    search_input.send_keys(task_number)
    search_input.send_keys(Keys.RETURN)
    time.sleep(0.5)
    WebDriverWait(driver, 20).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, 'span.glyphicon.glyphicon-step-forward'))
    ).click()
    time.sleep(1)
    comment_input = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.ID, 'txtObservacionTarea')))
    comment_input.send_keys('SE RECIBE LA MERCADERIA')
    time.sleep(1)
    WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.ID, 'btnGrabarEjecucionTarea'))).click()
    time.sleep(2)
    WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.ID, 'btnSmsCustomOk'))).click()
    time.sleep(2)
    
    for detail in task["details"]:
        tracking_button = WebDriverWait(driver, 20).until(EC.element_to_be_clickable(
            (By.CSS_SELECTOR, "button[onclick*='mostrarIngresoSeguimiento']")))
        tracking_button.click()
        time.sleep(2)
        tracking_input = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.ID, 'txtSeguimientoTarea')))
        tracking_message = f"SE INGRESA LA FACTURA {detail['Factura']} CON EL INGRESO {detail['Ingreso']}"
        tracking_input.clear()
        tracking_input.send_keys(tracking_message)
        time.sleep(2)
        WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.ID, 'btnIngresoSeguimiento'))).click()
        time.sleep(2)
        WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.ID, 'btnSmsCustomOk'))).click()
        time.sleep(2)
    
    WebDriverWait(driver, 20).until(EC.element_to_be_clickable(
        (By.CSS_SELECTOR, 'span.glyphicon.glyphicon-dashboard')
    )).click()
    time.sleep(2)
    department_input = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.ID, 'txtDepartment')))
    department_input.clear()
    department_input.send_keys('Bodeg')
    time.sleep(1)
    department_input.send_keys(Keys.DOWN, Keys.RETURN)
    time.sleep(2)
    department_input.send_keys(Keys.TAB)
    time.sleep(2)
    employee_input = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.NAME, 'txtEmpleado')))
    employee_input.click()
    employee_input.send_keys(empleado)
    time.sleep(1)
    employee_input.send_keys(Keys.DOWN, Keys.RETURN)
    time.sleep(2)
    employee_input.send_keys(Keys.TAB)
    time.sleep(2)
    observation_textarea = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.ID, 'txtaObsTareaFinalReasigna')))
    observation_textarea.send_keys('TRABAJO REALIZADO')
    WebDriverWait(driver, 20).until(EC.visibility_of_element_located((By.ID, "modalReasignarTarea")))
    boton = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.ID, "btnGrabarReasignaTarea")))
    ActionChains(driver).move_to_element(boton).perform()
    boton.click()
    final_confirm_button = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.ID, 'btnMensajeFinTarea')))
    final_confirm_button.click()
    time.sleep(2)
    
    driver.quit()

def open_reasignacion(master, email_session):
    """
    Abre la ventana de reasignación de tareas, configurando la interfaz gráfica para la selección
    y procesamiento de tareas cargadas desde el correo.
    
    Args:
        master (tk.Tk o tk.Toplevel): Ventana principal.
        email_session (dict): Información de la sesión de correo.
    """
    window = tk.Toplevel(master)
    window.title("Reasignación de Tareas")
    window.geometry("670x600")
    window.transient(master)
    window.grab_set()

    def on_close():
        # Limpia las tareas temporales antes de cerrar la ventana.
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
        # Actualiza la región de desplazamiento del canvas.
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

    def toggle_select_all():
        # Selecciona o deselecciona todas las tareas listadas.
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

    process_btn = ttk.Button(
        bottom_frame,
        text="Reasignar Tareas",
        style="MyButton.TButton"
    )
    process_btn.pack(side="right")

    status_label = ttk.Label(window, text="", style="MyLabel.TLabel", foreground="blue")
    status_label.pack(pady=2)

    def actualizar_tareas():
        """
        Actualiza la lista de tareas en la interfaz consultando la base de datos.
        """
        all_tasks = db.get_tasks_temp()
        print("DEBUG - Tareas en DB:", all_tasks)

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
        """
        Procesa las tareas seleccionadas, ejecutando la función para cada tarea y
        eliminándola de la base de datos al finalizar.
        """
        if not any(var.get() for var, _ in task_vars.values()):
            messagebox.showwarning("Advertencia", "No se ha seleccionado ninguna tarea.", parent=window)
            return

        process_btn.config(state="disabled")
        status_label.config(text="Procesando tareas, por favor espere...")
        window.update()

        errors = []
        tasks_in_db = db.get_tasks_temp()
        tasks_dict = {t["id"]: t for t in tasks_in_db}

        for t_id, (var, _) in task_vars.items():
            if var.get():
                task = tasks_dict[t_id]
                try:
                    process_task(task, email_session)
                    db.delete_task_temp(t_id)
                except Exception as e:
                    errors.append(str(e))

        if errors:
            messagebox.showerror("Errores", "\n".join(errors), parent=window)
        else:
            messagebox.showinfo("Éxito", "Tareas procesadas exitosamente.", parent=window)

        status_label.config(text="")
        process_btn.config(state="normal")
        actualizar_tareas()
        window.destroy()

    process_btn.configure(command=process_tasks)
    actualizar_tareas()
