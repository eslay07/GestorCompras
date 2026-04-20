import tkinter as tk
from tkinter import ttk, messagebox
from tkinter.scrolledtext import ScrolledText

from gestorcompras.services import db
from gestorcompras.services import google_sheets
from gestorcompras.logic import despacho_logic
from gestorcompras import theme
from gestorcompras.ui.common import add_hover_effect


def center_window(win: tk.Tk | tk.Toplevel):
    win.update_idletasks()
    w = win.winfo_width()
    h = win.winfo_height()
    x = (win.winfo_screenwidth() // 2) - (w // 2)
    y = (win.winfo_screenheight() // 2) - (h // 2)
    win.geometry(f"{w}x{h}+{x}+{y}")


def open_seguimientos(master, email_session):
    window = tk.Toplevel(master)
    window.title("Seguimientos desde Google Sheets")
    window.geometry("800x620")
    window.transient(master)
    window.grab_set()
    center_window(window)

    main = ttk.Frame(window, padding=20, style="MyFrame.TFrame")
    main.pack(fill="both", expand=True)
    main.columnconfigure(0, weight=1)
    main.rowconfigure(3, weight=1)

    header = ttk.Frame(main, style="MyFrame.TFrame")
    header.grid(row=0, column=0, sticky="ew", pady=(0, 6))
    ttk.Label(header, text="Seguimientos",
              font=("Segoe UI", 16, "bold"), foreground=theme.color_titulos).pack(side="left")
    ttk.Label(header, text="Envie correos de seguimiento desde datos de Google Sheets.",
              font=("Segoe UI", 10), foreground="#6B7280").pack(side="left", padx=(16, 0))

    ttk.Separator(main, orient="horizontal").grid(row=0, column=0, sticky="ew", pady=(36, 0))

    sid = db.get_config("GOOGLE_SHEET_ID", "")
    sname = db.get_config("GOOGLE_SHEET_NAME", "")

    info_frame = ttk.LabelFrame(main, text="Origen de datos", style="MyLabelFrame.TLabelframe", padding=10)
    info_frame.grid(row=1, column=0, sticky="ew", pady=(8, 6))
    info_frame.columnconfigure(1, weight=1)

    ttk.Label(info_frame, text="Hoja de calculo:", style="MyLabel.TLabel").grid(row=0, column=0, sticky="w")
    ttk.Label(info_frame, text=sid if sid else "No configurado",
              foreground=theme.color_texto if sid else "#9CA3AF").grid(row=0, column=1, sticky="w", padx=(8, 0))
    ttk.Label(info_frame, text="Hoja:", style="MyLabel.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))
    ttk.Label(info_frame, text=sname if sname else "No configurado",
              foreground=theme.color_texto if sname else "#9CA3AF").grid(row=1, column=1, sticky="w", padx=(8, 0), pady=(4, 0))

    status_var = tk.StringVar(value="Presione 'Cargar datos' para obtener las ordenes.")
    ttk.Label(info_frame, textvariable=status_var, font=("Segoe UI", 9),
              foreground="#6B7280").grid(row=2, column=0, columnspan=3, sticky="w", pady=(8, 0))

    btn_cargar = ttk.Button(info_frame, text="Cargar datos", style="MyButton.TButton")
    btn_cargar.grid(row=0, column=2, rowspan=2, padx=(12, 0), sticky="ne")
    add_hover_effect(btn_cargar)

    orders_frame = ttk.LabelFrame(main, text="Ordenes de compra", style="MyLabelFrame.TLabelframe", padding=10)
    orders_frame.grid(row=3, column=0, sticky="nsew", pady=(6, 6))
    orders_frame.rowconfigure(0, weight=1)
    orders_frame.columnconfigure(0, weight=1)

    canvas = tk.Canvas(orders_frame, background="#FFFFFF", highlightthickness=1,
                       highlightbackground=theme.color_borde)
    scrollbar = ttk.Scrollbar(orders_frame, orient="vertical", command=canvas.yview)
    inner = ttk.Frame(canvas, style="MyFrame.TFrame")

    def on_inner_configure(event):
        canvas.configure(scrollregion=canvas.bbox("all"))
    inner.bind("<Configure>", on_inner_configure)
    canvas.create_window((0, 0), window=inner, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.grid(row=0, column=0, sticky="nsew")
    scrollbar.grid(row=0, column=1, sticky="ns")

    select_row = ttk.Frame(orders_frame, style="MyFrame.TFrame")
    select_row.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))

    select_all_var = tk.BooleanVar(value=False)
    order_vars = []

    def toggle_all():
        val = select_all_var.get()
        for var, _ in order_vars:
            var.set(val)

    ttk.Checkbutton(select_row, text="Seleccionar todas", variable=select_all_var,
                    command=toggle_all, style="MyCheckbutton.TCheckbutton").pack(side="left")
    count_lbl = ttk.Label(select_row, text="", style="MyLabel.TLabel", font=("Segoe UI", 10, "bold"))
    count_lbl.pack(side="left", padx=(16, 0))

    config_frame = ttk.LabelFrame(main, text="Opciones de envio", style="MyLabelFrame.TLabelframe", padding=10)
    config_frame.grid(row=4, column=0, sticky="ew", pady=(6, 6))
    config_frame.columnconfigure(1, weight=1)

    ttk.Label(config_frame, text="Formato de correo:", style="MyLabel.TLabel").grid(row=0, column=0, sticky="w")
    formatos = ["-- Seleccione formato --"] + [tpl[1] for tpl in db.get_email_templates()]
    formato_var = tk.StringVar(value="-- Seleccione formato --")
    ttk.Combobox(config_frame, textvariable=formato_var, values=formatos,
                 state="readonly", width=30).grid(row=0, column=1, sticky="w", padx=(8, 0))

    attach_var = tk.BooleanVar(value=True)
    ttk.Checkbutton(config_frame, text="Adjuntar PDF de la orden",
                    variable=attach_var, style="MyCheckbutton.TCheckbutton").grid(
        row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))

    log_frame = ttk.LabelFrame(main, text="Progreso", style="MyLabelFrame.TLabelframe", padding=10)
    log_frame.grid(row=5, column=0, sticky="ew", pady=(6, 6))
    log_frame.columnconfigure(0, weight=1)

    log_box = ScrolledText(log_frame, height=5, state="disabled",
                           bg="#FFFFFF", fg=theme.color_texto, font=("Segoe UI", 9))
    log_box.grid(row=0, column=0, sticky="ew")

    btn_frame = ttk.Frame(main, style="MyFrame.TFrame")
    btn_frame.grid(row=6, column=0, sticky="ew", pady=(6, 0))

    btn_enviar = ttk.Button(btn_frame, text="Enviar correos", style="MyButton.TButton")
    btn_enviar.pack(side="right")
    add_hover_effect(btn_enviar)

    def log(msg: str):
        log_box.configure(state="normal")
        log_box.insert(tk.END, msg + "\n")
        log_box.see(tk.END)
        log_box.configure(state="disabled")

    def load_report():
        creds = db.get_config("GOOGLE_CREDS", "")
        if not (creds and sid and sname):
            messagebox.showwarning(
                "Configuracion incompleta",
                "Debe configurar las credenciales de Google, el ID de la hoja\n"
                "y el nombre de la hoja en la seccion de Configuracion.",
                parent=window,
            )
            return
        status_var.set("Cargando datos desde Google Sheets...")
        window.update()
        try:
            rows = google_sheets.read_report(creds, sid, sname)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo leer la hoja de calculo:\n{e}", parent=window)
            status_var.set("Error al cargar datos.")
            return

        for widget in inner.winfo_children():
            widget.destroy()
        order_vars.clear()

        for r in rows:
            row_frame = ttk.Frame(inner, style="MyFrame.TFrame")
            row_frame.pack(fill="x", padx=8, pady=2)
            var = tk.BooleanVar(value=False)
            ttk.Checkbutton(row_frame, variable=var, style="MyCheckbutton.TCheckbutton").pack(side="left")
            ttk.Label(row_frame, text=f"OC {r['Orden de Compra']}",
                      font=("Segoe UI", 10, "bold"), foreground=theme.color_titulos).pack(side="left", padx=(4, 8))
            ttk.Label(row_frame, text=f"{r['Proveedor']}  (Tarea {r['Tarea']})",
                      style="MyLabel.TLabel").pack(side="left")
            order_vars.append((var, r))

        count_lbl.configure(text=f"{len(rows)} ordenes cargadas")
        status_var.set(f"Datos cargados: {len(rows)} registros. Seleccione las ordenes a enviar.")
        canvas.update_idletasks()
        canvas.yview_moveto(0.0)

    def send_emails():
        selected = [r for var, r in order_vars if var.get()]
        if not selected:
            messagebox.showwarning("Advertencia", "Seleccione al menos una orden.", parent=window)
            return
        if formato_var.get() == "-- Seleccione formato --":
            messagebox.showwarning("Advertencia", "Seleccione un formato de correo.", parent=window)
            return

        summaries = []
        for r in selected:
            oc = str(r["Orden de Compra"])
            info, error = despacho_logic.obtener_resumen_orden(oc)
            if info:
                emails = ", ".join(info["emails"]) if info["emails"] else "sin correo"
                summaries.append(f"OC {oc}  →  {emails}")
            else:
                summaries.append(f"OC {oc}  →  {error}")

        confirm_msg = "\n".join(summaries) + f"\n\nFormato: {formato_var.get()}\n¿Enviar {len(selected)} correo(s)?"
        if not messagebox.askyesno("Confirmar envio", confirm_msg, parent=window):
            return

        btn_enviar.configure(state="disabled")
        status_var.set("Enviando correos...")

        for r in selected:
            result = despacho_logic.process_order(
                email_session, str(r["Orden de Compra"]),
                include_pdf=attach_var.get(),
                template_name=formato_var.get(),
                cc_key="EMAIL_CC_SEGUIMIENTO",
            )
            log(result)

        btn_enviar.configure(state="normal")
        status_var.set(f"Envio completado: {len(selected)} correo(s) procesados.")
        messagebox.showinfo("Completado", f"Se procesaron {len(selected)} correo(s).", parent=window)

    btn_cargar.configure(command=load_report)
    btn_enviar.configure(command=send_emails)
