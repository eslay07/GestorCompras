import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from gestorcompras.services import db
import threading
import time
import datetime
import os
import email
try:
    import pypff
except ImportError:  # pragma: no cover - library may not be available during tests
    pypff = None
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

    pst_path = db.get_config("PST_FILE", "")
    if not pst_path or not os.path.exists(pst_path):
        messagebox.showerror("Error", "No se encontró el archivo PST configurado.", parent=window)
        return
    if pypff is None:
        messagebox.showerror("Error", "La librería pypff no está instalada.", parent=window)
        return
    try:
        pst = pypff.file()
        pst.open(pst_path)
    except Exception as e:
        messagebox.showerror("Error", f"No se pudo abrir el archivo PST: {e}", parent=window)
        return

    date_since_dt = datetime.datetime.strptime(date_input, '%d/%m/%Y')
    loaded_count = 0

    def traverse(folder):
        nonlocal loaded_count
        for i in range(folder.number_of_sub_messages):
            try:
                msg = folder.get_sub_message(i)
                sender = (msg.sender_email_address or "").lower()
                if sender != "omar777j@gmail.com":
                    continue
                msg_date = msg.client_submit_time or msg.delivery_time
                if msg_date and msg_date < date_since_dt:
                    continue
                body = ""
                if msg.plain_text_body:
                    body = msg.plain_text_body.decode(errors='ignore')
                elif msg.html_body:
                    body = msg.html_body.decode(errors='ignore')
                tasks_data = process_body(body)
                for task_info in tasks_data:
                    if task_filters and task_info["task_number"] not in task_filters:
                        continue
                    inserted = db.insert_task_temp(
                        task_info["task_number"],
                        task_info["reasignacion"],
                        task_info["details"])
                    if inserted:
                        loaded_count += 1
            except Exception:
                continue
        for j in range(folder.number_of_sub_folders):
            traverse(folder.get_sub_folder(j))

    traverse(pst.get_root_folder())
    pst.close()
    messagebox.showinfo("Información", f"Se cargaron {loaded_count} tareas (sin duplicados).", parent=window)

def login_telcos(driver, username, password):
    driver.get('https://telcos.telconet.ec/inicio/?josso_back_to=http://telcos.telconet.ec/check&josso_partnerapp_host=telcos.telconet.ec')
    user_input = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.NAME, 'josso_username')))
    user_input.send_keys(username)
    password_input = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.NAME, 'josso_password')))
    password_input.send_keys(password)
    password_input.send_keys(Keys.RETURN)
    WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, 'spanTareasPersonales')))

def process_task(task, email_session):
    service = Service(ChromeDriverManager().install())
    chrome_options = Options()
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
    
    try:
        time.sleep(0.5)
        WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, 'span.glyphicon.glyphicon-step-forward'))
        ).click()
    except Exception:
        driver.quit()
        # Se lanza la excepción con el mensaje exacto, sin mostrarla inmediatamente
        raise Exception(f"No se encontraron las tareas en la plataforma Telcos.\nTarea: {task_number}")
    
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
    #department_input.send_keys('Compras L')
    department_input.send_keys('Bodeg')
    time.sleep(1)
    #elemento para pruebas compras
    #department_input.send_keys(Keys.UP, Keys.RETURN)
    #////////////elementopara produccion bodega
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
    # Se mueve el ratón al botón antes de hacer clic
    from selenium.webdriver.common.action_chains import ActionChains
    ActionChains(driver).move_to_element(boton).perform()
    boton.click()
    final_confirm_button = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.ID, 'btnMensajeFinTarea')))
    final_confirm_button.click()
    time.sleep(2)
    
    driver.quit()

def open_reasignacion(master, email_session):
    window = tk.Toplevel(master)
    window.title("Reasignación de Tareas")
    window.geometry("670x600")
    window.transient(master)
    window.grab_set()

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

    process_btn = ttk.Button(
        bottom_frame,
        text="Reasignar Tareas",
        style="MyButton.TButton"
    )
    process_btn.pack(side="right")

    status_label = ttk.Label(window, text="", style="MyLabel.TLabel", foreground="blue")
    status_label.pack(pady=2)

    def actualizar_tareas():
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
            error_message = "Algunas tareas no fueron reasignadas:\n" + "\n".join(errors) + \
                            "\n\nPor favor revisar las tareas mencionadas"
            confirm = messagebox.askokcancel("Errores encontrados", error_message, parent=window)
        else:
            messagebox.showinfo("Éxito", "Tareas procesadas exitosamente.", parent=window)

        status_label.config(text="")
        process_btn.config(state="normal")
        actualizar_tareas()
        window.destroy()

    process_btn.configure(command=process_tasks)
    actualizar_tareas()

