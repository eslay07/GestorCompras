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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SERVICIOS_HEADLESS_KEY = "SERVICIOS_HEADLESS"

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains

# Funciones Selenium puras centralizadas en la capa de servicios (sin dependencias GUI)
from gestorcompras.services.telcos_automation import (
    login_telcos,
    wait_clickable_or_error,
    process_task_servicios,
)
from gestorcompras.services.selenium_utils import click_with_fallback, click_robust, retry_task


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

def cargar_tareas_correo(email_address, email_password, window, *, date_override=None):
    date_input = date_override
    if not date_input:
        dialog = DateDialog(window)
        date_input = dialog.result
    if not date_input:
        messagebox.showwarning("Advertencia", "No se ingreso una fecha.", parent=window)
        return
    try:
        date_since = datetime.datetime.strptime(date_input, "%d/%m/%Y").strftime("%d-%b-%Y")
    except Exception:
        messagebox.showerror("Error", "El formato de fecha debe ser DD/MM/AAAA.", parent=window)
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
        click_with_fallback(
            driver,
            [
                (By.CSS_SELECTOR, 'span.glyphicon.glyphicon-step-forward'),
                (By.XPATH, "//button[.//span[contains(@class,'glyphicon-step-forward')]]"),
            ],
            'el botón para abrir la tarea',
            parent_window=parent_window,
        )
    except Exception:
        # Se lanza la excepción con el mensaje exacto, sin mostrarla inmediatamente
        raise Exception(f"No se encontraron las tareas en la plataforma Telcos.\nTarea: {task_number}")

    time.sleep(1)
    comment_input = wait_clickable_or_error(
        driver, (By.ID, 'txtObservacionTarea'), parent_window, 'el campo de comentario')
    comment_input.send_keys('SE RECIBE LA MERCADERIA')
    time.sleep(1)
    click_with_fallback(
        driver,
        [
            (By.ID, 'btnGrabarEjecucionTarea'),
            (By.XPATH, "//*[@id='btnGrabarEjecucionTarea']//span"),
            (By.XPATH, "//span[contains(@class,'text-btn') and normalize-space(.)='Aceptar']"),
        ],
        'el botón Grabar Ejecución',
        parent_window=parent_window,
    )
    time.sleep(2)
    click_with_fallback(
        driver,
        [
            (By.ID, 'btnSmsCustomOk'),
            (By.XPATH, "//*[@id='btnSmsCustomOk']//span"),
            (By.XPATH, "//span[contains(@class,'text-btn') and normalize-space(.)='OK']"),
        ],
        'la confirmación inicial',
        parent_window=parent_window,
    )
    time.sleep(2)

    for detail in task["details"]:
        click_with_fallback(
            driver,
            [
                (By.CSS_SELECTOR, "button[onclick*='mostrarIngresoSeguimiento']"),
                (By.XPATH, "//button[contains(@onclick,'mostrarIngresoSeguimiento')]//span"),
            ],
            'el botón de seguimiento',
            parent_window=parent_window,
        )
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
        click_with_fallback(
            driver,
            [
                (By.ID, 'btnIngresoSeguimiento'),
                (By.XPATH, "//*[@id='btnIngresoSeguimiento']//span"),
            ],
            'el botón Ingreso Seguimiento',
            parent_window=parent_window,
        )
        time.sleep(2)
        click_with_fallback(
            driver,
            [
                (By.ID, 'btnSmsCustomOk'),
                (By.XPATH, "//*[@id='btnSmsCustomOk']//span"),
                (By.XPATH, "//span[contains(@class,'text-btn') and normalize-space(.)='OK']"),
            ],
            'la confirmación de seguimiento',
            parent_window=parent_window,
        )
        time.sleep(2)

    click_with_fallback(
        driver,
        [
            (By.CSS_SELECTOR, 'span.glyphicon.glyphicon-dashboard'),
            (By.XPATH, "//button[.//span[contains(@class,'glyphicon-dashboard')]]"),
        ],
        'el botón de reasignar',
        parent_window=parent_window,
    )
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
    try:
        click_robust(driver, boton)
    except Exception:
        click_with_fallback(
            driver,
            [
                (By.ID, "btnGrabarReasignaTarea"),
                (By.XPATH, "//*[@id='btnGrabarReasignaTarea']//span"),
            ],
            'el botón Guardar',
            parent_window=parent_window,
        )
    final_confirm_button = WebDriverWait(driver, 20).until(
        EC.element_to_be_clickable((By.ID, 'btnMensajeFinTarea'))
    )
    try:
        click_robust(driver, final_confirm_button)
    except Exception:
        click_with_fallback(
            driver,
            [
                (By.ID, 'btnMensajeFinTarea'),
                (By.XPATH, "//*[@id='btnMensajeFinTarea']//span"),
            ],
            'la confirmación final',
            parent_window=parent_window,
        )
    time.sleep(2)


def open_reasignacion(master, email_session):
    from gestorcompras import theme
    from gestorcompras.ui.common import create_tooltip
    from tkinter.scrolledtext import ScrolledText

    window = tk.Toplevel(master)
    window.title("Reasignacion de Tareas - Bienes")
    window.geometry("920x700")
    window.transient(master)
    window.grab_set()
    center_window(window)

    def on_close():
        db.clear_tasks_temp()
        window.destroy()
    window.protocol("WM_DELETE_WINDOW", on_close)

    main = ttk.Frame(window, style="MyFrame.TFrame", padding=20)
    main.pack(fill="both", expand=True)
    main.columnconfigure(0, weight=1)
    main.rowconfigure(2, weight=1)

    header = ttk.Frame(main, style="MyFrame.TFrame")
    header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
    ttk.Label(
        header, text="Reasignacion de Tareas",
        font=("Segoe UI", 16, "bold"), foreground=theme.color_titulos,
    ).pack(side="left")
    ttk.Label(
        header, text="Busque tareas desde el correo y reasignelas automaticamente.",
        font=("Segoe UI", 10), foreground="#6B7280",
    ).pack(side="left", padx=(16, 0))

    ttk.Separator(main, orient="horizontal").grid(row=0, column=0, sticky="ew", pady=(40, 0))

    search_frame = ttk.LabelFrame(main, text="Buscar tareas", style="MyLabelFrame.TLabelframe", padding=12)
    search_frame.grid(row=1, column=0, sticky="ew", pady=(8, 8))
    search_frame.columnconfigure(1, weight=1)

    ttk.Label(search_frame, text="Fecha desde:", style="MyLabel.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8))
    date_var = tk.StringVar(value=datetime.date.today().strftime("%d/%m/%Y"))
    date_entry = ttk.Entry(search_frame, textvariable=date_var, style="MyEntry.TEntry", width=16)
    date_entry.grid(row=0, column=1, sticky="w")
    ttk.Label(
        search_frame, text="Formato: DD/MM/AAAA  |  Maximo 15 dias atras",
        font=("Segoe UI", 9), foreground="#6B7280",
    ).grid(row=0, column=2, sticky="w", padx=(12, 0))

    status_var = tk.StringVar(value="Ingrese una fecha y presione Buscar.")
    btn_buscar = ttk.Button(search_frame, text="Buscar en correo", style="MyButton.TButton")
    btn_buscar.grid(row=0, column=3, padx=(12, 0))
    from gestorcompras.ui.common import add_hover_effect
    add_hover_effect(btn_buscar)

    ttk.Label(search_frame, textvariable=status_var, style="MyLabel.TLabel",
              font=("Segoe UI", 9), foreground="#6B7280").grid(row=1, column=0, columnspan=4, sticky="w", pady=(6, 0))

    task_frame = ttk.LabelFrame(main, text="Tareas encontradas", style="MyLabelFrame.TLabelframe", padding=10)
    task_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 8))
    task_frame.rowconfigure(0, weight=1)
    task_frame.columnconfigure(0, weight=1)

    canvas = tk.Canvas(task_frame, background="#FFFFFF", highlightthickness=1,
                       highlightbackground=theme.color_borde)
    scrollbar = ttk.Scrollbar(task_frame, orient="vertical", command=canvas.yview)
    tasks_inner = ttk.Frame(canvas, style="MyFrame.TFrame")

    def on_frame_configure(event):
        canvas.configure(scrollregion=canvas.bbox("all"))
    tasks_inner.bind("<Configure>", on_frame_configure)

    canvas.create_window((0, 0), window=tasks_inner, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.grid(row=0, column=0, sticky="nsew")
    scrollbar.grid(row=0, column=1, sticky="ns")

    select_row = ttk.Frame(task_frame, style="MyFrame.TFrame")
    select_row.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))

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

    ttk.Checkbutton(select_row, text="Seleccionar todas", style="MyCheckbutton.TCheckbutton",
                    variable=select_all_var, command=toggle_select_all).pack(side="left")
    count_lbl = ttk.Label(select_row, text="", style="MyLabel.TLabel", font=("Segoe UI", 10, "bold"))
    count_lbl.pack(side="left", padx=(16, 0))

    action_frame = ttk.LabelFrame(main, text="Ejecutar", style="MyLabelFrame.TLabelframe", padding=12)
    action_frame.grid(row=3, column=0, sticky="ew", pady=(0, 0))
    action_frame.columnconfigure(1, weight=1)

    ttk.Checkbutton(action_frame, text="Mostrar navegador durante la ejecucion",
                    style="MyCheckbutton.TCheckbutton",
                    variable=headless_var, onvalue=False, offvalue=True).grid(row=0, column=0, sticky="w")
    create_tooltip(action_frame.winfo_children()[-1],
                   "Si esta activado, podra ver el navegador mientras se reasignan las tareas.")

    progress = ttk.Progressbar(action_frame, mode="determinate")
    progress.grid(row=0, column=1, sticky="ew", padx=(16, 12))
    progress.grid_remove()

    process_btn = ttk.Button(action_frame, text="Reasignar seleccionadas", style="MyButton.TButton")
    process_btn.grid(row=0, column=2, sticky="e")
    add_hover_effect(process_btn)

    log_box = ScrolledText(action_frame, height=5, state="disabled",
                           bg="#FFFFFF", fg=theme.color_texto, font=("Segoe UI", 9))
    log_box.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(8, 0))
    log_box.grid_remove()

    def _log(msg):
        log_box.grid()
        log_box.configure(state="normal")
        log_box.insert(tk.END, msg + "\n")
        log_box.see(tk.END)
        log_box.configure(state="disabled")

    def _do_search():
        date_input = date_var.get().strip()
        if not date_input:
            messagebox.showwarning("Advertencia", "Ingrese una fecha para buscar.", parent=window)
            return
        try:
            datetime.datetime.strptime(date_input, "%d/%m/%Y")
        except ValueError:
            messagebox.showerror("Error", "El formato de fecha debe ser DD/MM/AAAA.", parent=window)
            return

        btn_buscar.config(state="disabled")
        status_var.set("Buscando tareas en el correo...")
        window.update()

        cargar_tareas_correo(email_session["address"], email_session["password"], window,
                             date_override=date_input)
        actualizar_tareas()
        btn_buscar.config(state="normal")

    btn_buscar.configure(command=_do_search)

    def actualizar_tareas():
        all_tasks = db.get_tasks_temp()

        for widget in tasks_inner.winfo_children():
            widget.destroy()
        task_vars.clear()
        select_all_var.set(False)

        if not all_tasks:
            ttk.Label(tasks_inner, text="No hay tareas cargadas. Presione 'Buscar en correo' para comenzar.",
                      style="MyLabel.TLabel", foreground="#6B7280").pack(pady=30, padx=20)
            count_lbl.configure(text="")
            status_var.set("No se encontraron tareas.")
            return

        count_lbl.configure(text=f"{len(all_tasks)} tareas encontradas")
        status_var.set(f"Se cargaron {len(all_tasks)} tareas. Seleccione las que desea reasignar.")

        for task in all_tasks:
            var = tk.BooleanVar(value=False)
            row = ttk.Frame(tasks_inner, style="MyFrame.TFrame")
            row.pack(fill="x", padx=8, pady=2)
            chk = ttk.Checkbutton(row, style="MyCheckbutton.TCheckbutton", variable=var)
            chk.pack(side="left")
            ttk.Label(row, text=f"Tarea {task['task_number']}",
                      font=("Segoe UI", 11, "bold"), foreground=theme.color_titulos).pack(side="left", padx=(4, 8))
            ttk.Label(row, text=task['reasignacion'],
                      style="MyLabel.TLabel").pack(side="left")
            task_vars[task["id"]] = (var, chk)

        canvas.update_idletasks()
        canvas.yview_moveto(0.0)

    def process_tasks():
        selected = [(t_id, var) for t_id, (var, _) in task_vars.items() if var.get()]
        if not selected:
            messagebox.showwarning("Advertencia", "Seleccione al menos una tarea para reasignar.", parent=window)
            return

        n_total = len(selected)
        if not messagebox.askyesno("Confirmar",
                                   f"Se reasignaran {n_total} tarea(s).\n¿Desea continuar?",
                                   parent=window):
            return

        process_btn.config(state="disabled")
        btn_buscar.config(state="disabled")
        progress.configure(maximum=n_total, value=0)
        progress.grid()
        log_box.grid()
        log_box.configure(state="normal")
        log_box.delete("1.0", tk.END)
        log_box.configure(state="disabled")
        status_var.set("Iniciando reasignacion...")
        window.update()

        def _run():
            errors: list[str] = []
            tasks_in_db = db.get_tasks_temp()
            tasks_dict = {t["id"]: t for t in tasks_in_db}
            procesadas_ok: list[dict] = []

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

            def _reabrir_panel():
                element = wait_clickable_or_error(
                    driver, (By.ID, "spanTareasPersonales"), window, "menú de tareas", timeout=10, retries=1
                )
                driver.execute_script("arguments[0].click();", element)

            try:
                for i, (t_id, _var) in enumerate(selected):
                    task = tasks_dict[t_id]
                    window.after(0, lambda ii=i, tn=task['task_number']: (
                        progress.configure(value=ii),
                        status_var.set(f"Procesando tarea {tn} ({ii+1}/{n_total})..."),
                        _log(f"Procesando tarea {tn}..."),
                    ))
                    try:
                        retry_task(
                            process_task,
                            args=(driver, task, window),
                            max_attempts=2,
                            log=lambda msg: logger.info(msg),
                            on_retry=lambda _: _reabrir_panel(),
                        )
                        db.delete_task_temp(t_id)
                        procesadas_ok.append(task)
                        window.after(0, lambda tn=task['task_number']: _log(f"  Tarea {tn} reasignada correctamente."))
                    except Exception as e:
                        errors.append(f"Tarea {task['task_number']}: {e}")
                        window.after(0, lambda tn=task['task_number'], err=str(e): _log(f"  Error en tarea {tn}: {err}"))
            finally:
                driver.quit()

            def _finish():
                progress.configure(value=n_total)
                process_btn.config(state="normal")
                btn_buscar.config(state="normal")

                n_ok = len(procesadas_ok)
                n_err = len(errors)
                if errors:
                    status_var.set(f"Finalizado: {n_ok} exitosas, {n_err} con error.")
                    summary = f"Se reasignaron {n_ok} de {n_total} tareas.\n\nErrores:\n" + "\n".join(errors)
                    messagebox.showwarning("Resultado parcial", summary, parent=window)
                else:
                    status_var.set(f"Todas las tareas fueron reasignadas exitosamente ({n_ok}).")
                    messagebox.showinfo("Completado", f"Las {n_ok} tareas fueron reasignadas correctamente.", parent=window)

                actualizar_tareas()

                try:
                    from gestorcompras.ui.actua_tareas_gui import abrir_panel_tareas
                    tareas_panel = []
                    for task in procesadas_ok:
                        detalles = task.get("details") or []
                        primer_detalle = detalles[0] if detalles else {}
                        tareas_panel.append({
                            "task_number": str(task.get("task_number", "")),
                            "proveedor": primer_detalle.get("Proveedor", ""),
                            "oc": primer_detalle.get("OC", ""),
                            "factura": primer_detalle.get("Factura", ""),
                            "ingreso": primer_detalle.get("Ingreso", ""),
                            "reasignacion": task.get("reasignacion", ""),
                        })
                    if tareas_panel and messagebox.askyesno(
                        "Actualizar Tareas",
                        "¿Desea ejecutar un flujo de Actualizar Tareas\nsobre las tareas reasignadas?",
                        parent=window,
                    ):
                        abrir_panel_tareas(window, email_session, "reasignacion", tareas_panel, mode="bienes")
                except Exception:
                    logger.exception("No se pudo abrir el panel de Actualizar Tareas")

            window.after(0, _finish)

        threading.Thread(target=_run, daemon=True).start()

    process_btn.configure(command=process_tasks)
    actualizar_tareas()

