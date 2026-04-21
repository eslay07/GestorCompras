import tkinter as tk
from tkinter import ttk, messagebox
from tkinter.scrolledtext import ScrolledText
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from gestorcompras.logic import despacho_logic
from gestorcompras.services import db
from gestorcompras import theme
from gestorcompras.ui.common import add_hover_effect


def center_window(win: tk.Tk | tk.Toplevel):
    win.update_idletasks()
    w = win.winfo_width()
    h = win.winfo_height()
    x = (win.winfo_screenwidth() // 2) - (w // 2)
    y = (win.winfo_screenheight() // 2) - (h // 2)
    win.geometry(f"{w}x{h}+{x}+{y}")


def open_despacho(master, email_session):
    window = tk.Toplevel(master)
    window.title("Correos Masivos - Despacho")
    window.geometry("720x600")
    window.transient(master)
    window.grab_set()
    center_window(window)

    main = ttk.Frame(window, style="MyFrame.TFrame", padding=20)
    main.pack(fill="both", expand=True)
    main.columnconfigure(0, weight=1)
    main.rowconfigure(2, weight=1)
    main.rowconfigure(4, weight=1)

    header = ttk.Frame(main, style="MyFrame.TFrame")
    header.grid(row=0, column=0, sticky="ew", pady=(0, 6))
    ttk.Label(header, text="Correos Masivos",
              font=("Segoe UI", 16, "bold"), foreground=theme.color_titulos).pack(side="left")
    ttk.Label(header, text="Envie correos de despacho a proveedores por numero de OC.",
              font=("Segoe UI", 10), foreground="#6B7280").pack(side="left", padx=(16, 0))

    ttk.Separator(main, orient="horizontal").grid(row=0, column=0, sticky="ew", pady=(36, 0))

    input_frame = ttk.LabelFrame(main, text="Ordenes de compra", style="MyLabelFrame.TLabelframe", padding=10)
    input_frame.grid(row=1, column=0, sticky="ew", pady=(8, 6))
    input_frame.columnconfigure(0, weight=1)

    ttk.Label(input_frame, text="Ingrese los numeros de OC, uno por linea:",
              style="MyLabel.TLabel").grid(row=0, column=0, sticky="w")
    ttk.Label(input_frame, text="Ejemplo: 1234567",
              font=("Segoe UI", 9), foreground="#6B7280").grid(row=0, column=1, sticky="e")

    text_area = tk.Text(input_frame, height=6, bg="#FFFFFF", fg=theme.color_texto,
                        font=("Segoe UI", 11), relief="solid", borderwidth=1,
                        highlightcolor=theme.color_primario, highlightthickness=1)
    text_area.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))

    config_frame = ttk.LabelFrame(main, text="Configuracion de envio", style="MyLabelFrame.TLabelframe", padding=10)
    config_frame.grid(row=2, column=0, sticky="nsew", pady=(6, 6))
    config_frame.columnconfigure(1, weight=1)

    ttk.Label(config_frame, text="Formato de correo:", style="MyLabel.TLabel").grid(row=0, column=0, sticky="w")
    formatos = ["-- Seleccione formato --"] + [tpl[1] for tpl in db.get_email_templates()]
    formato_var = tk.StringVar(value="-- Seleccione formato --")
    fmt_combo = ttk.Combobox(config_frame, textvariable=formato_var, values=formatos, state="readonly", width=30)
    fmt_combo.grid(row=0, column=1, sticky="w", padx=(8, 0))

    adjuntar_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(config_frame, text="Agrupar varias OC del mismo proveedor en un solo correo",
                    variable=adjuntar_var, style="MyCheckbutton.TCheckbutton").grid(
        row=1, column=0, columnspan=2, sticky="w", pady=(10, 0))
    ttk.Label(config_frame, text="Si esta activado, las OC con el mismo RUC se envian juntas.",
              font=("Segoe UI", 9), foreground="#6B7280").grid(
        row=2, column=0, columnspan=2, sticky="w", padx=(24, 0))

    log_frame = ttk.LabelFrame(main, text="Progreso", style="MyLabelFrame.TLabelframe", padding=10)
    log_frame.grid(row=3, column=0, sticky="ew", pady=(6, 6))
    log_frame.columnconfigure(0, weight=1)

    progress = ttk.Progressbar(log_frame, mode="indeterminate")
    progress.grid(row=0, column=0, sticky="ew")
    progress.grid_remove()

    status_var = tk.StringVar(value="Listo para enviar.")
    ttk.Label(log_frame, textvariable=status_var, style="MyLabel.TLabel",
              font=("Segoe UI", 9)).grid(row=1, column=0, sticky="w", pady=(4, 0))

    log_box = ScrolledText(log_frame, height=6, state="disabled",
                           bg="#FFFFFF", fg=theme.color_texto, font=("Segoe UI", 9))
    log_box.grid(row=2, column=0, sticky="ew", pady=(6, 0))

    btn_frame = ttk.Frame(main, style="MyFrame.TFrame")
    btn_frame.grid(row=5, column=0, sticky="ew", pady=(6, 0))

    btn_procesar = ttk.Button(btn_frame, text="Enviar correos", style="MyButton.TButton")
    btn_procesar.pack(side="right")
    add_hover_effect(btn_procesar)

    def log_func(message):
        log_box.configure(state="normal")
        log_box.insert(tk.END, message + "\n")
        log_box.see(tk.END)
        log_box.configure(state="disabled")

    def process_input_orders():
        orders = [o.strip() for o in text_area.get("1.0", tk.END).splitlines() if o.strip()]
        if not orders:
            messagebox.showwarning("Advertencia", "Ingrese al menos un numero de OC.", parent=window)
            return

        if formato_var.get() == "-- Seleccione formato --":
            messagebox.showwarning("Advertencia", "Seleccione un formato de correo antes de enviar.", parent=window)
            return

        summaries = []
        infos = {}
        status_var.set("Verificando ordenes...")
        window.update()

        for oc in orders:
            info, error = despacho_logic.obtener_resumen_orden(oc)
            if info:
                emails = ", ".join(info["emails"]) if info["emails"] else "sin correo"
                summaries.append(f"OC {oc}  →  {emails}")
                infos[oc] = info
            else:
                summaries.append(f"OC {oc}  →  {error}")
        if not summaries:
            return
        if adjuntar_var.get():
            group_count = len({info["ruc"] for info in infos.values()})
        else:
            group_count = len(infos)

        confirm_msg = "\n".join(summaries) + f"\n\nFormato: {formato_var.get()}\n¿Enviar {group_count} correo(s)?"
        if not messagebox.askyesno("Confirmar envio", confirm_msg, parent=window):
            status_var.set("Envio cancelado.")
            return

        log_func(f"Enviando {group_count} correo(s)...")
        btn_procesar.configure(state="disabled")
        progress.grid()
        progress.start(10)
        status_var.set("Enviando correos...")

        def process_all_orders():
            results = []
            if adjuntar_var.get():
                results.extend(
                    despacho_logic.process_orders_grouped(
                        email_session, list(infos.keys()), True,
                        formato_var.get(), "EMAIL_CC_DESPACHO",
                    )
                )
                for result in results:
                    window.after(0, lambda r=result: log_func(r))
            else:
                with ThreadPoolExecutor(max_workers=4) as executor:
                    futures = [
                        executor.submit(
                            despacho_logic.process_order, email_session,
                            orden, True, formato_var.get(), "EMAIL_CC_DESPACHO",
                        )
                        for orden in orders
                    ]
                    for future in as_completed(futures):
                        try:
                            result = future.result()
                        except Exception as e:
                            result = f"Error: {e}"
                        results.append(result)
                        window.after(0, lambda r=result: log_func(r))

            def _done():
                progress.stop()
                progress.grid_remove()
                btn_procesar.configure(state="normal")
                n_ok = sum(1 for r in results if "error" not in r.lower())
                status_var.set(f"Completado: {n_ok} de {len(results)} enviados correctamente.")
                messagebox.showinfo("Resultado", "\n".join(results), parent=window)

            window.after(0, _done)

            try:
                from gestorcompras.ui.actua_tareas_gui import abrir_panel_tareas
                tareas = []
                for orden, info in infos.items():
                    tareas.append({
                        "task_number": str(info.get("tarea") or ""),
                        "oc": str(orden),
                        "ruc": info.get("ruc", ""),
                        "proveedor": info.get("folder_name", ""),
                        "emails": info.get("emails", []) or [],
                        "folder_name": info.get("folder_name", ""),
                    })
                tareas = [t for t in tareas if t["task_number"]]
                if tareas:
                    def _abrir_panel():
                        if messagebox.askyesno(
                            "Actualizar Tareas",
                            "¿Desea abrir el panel de Actualizar Tareas\ncon las OC procesadas?",
                            parent=window,
                        ):
                            abrir_panel_tareas(window, email_session, "correos_masivos", tareas)
                    window.after(0, _abrir_panel)
            except Exception as exc:
                window.after(0, lambda: log_func(f"[Hook Actualizar Tareas] {exc}"))

        threading.Thread(target=process_all_orders, daemon=True).start()

    btn_procesar.configure(command=process_input_orders)
