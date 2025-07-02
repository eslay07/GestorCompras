import tkinter as tk
from tkinter import ttk, messagebox
from tkinter.scrolledtext import ScrolledText

from gestorcompras.services import db
from gestorcompras.services import google_sheets
from gestorcompras.logic import despacho_logic


def open_seguimientos(master, email_session):
    window = tk.Toplevel(master)
    window.title("Seguimientos desde Sheet")
    window.geometry("700x500")
    window.transient(master)
    window.grab_set()

    frame = ttk.Frame(window, padding=10, style="MyFrame.TFrame")
    frame.pack(fill="both", expand=True)
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(3, weight=1)

    sid = db.get_config("GOOGLE_SHEET_ID", "")
    sname = db.get_config("GOOGLE_SHEET_NAME", "")

    ttk.Label(frame, text=f"Spreadsheet ID: {sid}", style="MyLabel.TLabel").grid(row=0, column=0, sticky="w")
    ttk.Label(frame, text=f"Hoja: {sname}", style="MyLabel.TLabel").grid(row=1, column=0, sticky="w", pady=(0,5))

    last_label = ttk.Label(frame, text="Datos no cargados", style="MyLabel.TLabel")
    last_label.grid(row=2, column=0, sticky="w")

    list_lf = ttk.LabelFrame(frame, text="Órdenes de Compra", style="MyLabelFrame.TLabelframe", padding=5)
    list_lf.grid(row=3, column=0, sticky="nsew", pady=5)

    canvas = tk.Canvas(list_lf, background="#FFFFFF", highlightthickness=1, highlightbackground="#CCCCCC")
    scrollbar = ttk.Scrollbar(list_lf, orient="vertical", command=canvas.yview)
    orders_frame = ttk.Frame(canvas, style="MyFrame.TFrame")

    def on_frame_configure(event):
        canvas.configure(scrollregion=canvas.bbox("all"))

    orders_frame.bind("<Configure>", on_frame_configure)
    canvas.create_window((0, 0), window=orders_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    ttk.Label(frame, text="Estado del Proceso:", style="MyLabel.TLabel").grid(row=5, column=0, sticky="w")
    log_box = ScrolledText(frame, height=6, state="disabled")
    log_box.grid(row=6, column=0, sticky="nsew", pady=5)

    ttk.Label(frame, text="Formato de correo:", style="MyLabel.TLabel").grid(row=4, column=0, sticky="w")
    formatos = ["FORMATO"] + [tpl[1] for tpl in db.get_email_templates()]
    formato_var = tk.StringVar(value="FORMATO")
    ttk.Combobox(frame, textvariable=formato_var, values=formatos, state="readonly").grid(row=4, column=0, sticky="e", padx=(150,0))

    attach_var = tk.BooleanVar(value=True)
    ttk.Checkbutton(frame, text="Adjuntar PDF", variable=attach_var, style="MyCheckbutton.TCheckbutton").grid(row=7, column=0, sticky="w")

    def log(msg: str):
        log_box.configure(state="normal")
        log_box.insert(tk.END, msg + "\n")
        log_box.see(tk.END)
        log_box.configure(state="disabled")

    order_vars = []

    def load_report():
        creds = db.get_config("GOOGLE_CREDS", "")
        if not (creds and sid and sname):
            messagebox.showwarning(
                "Advertencia",
                "Debe completar Spreadsheet ID y nombre de hoja y configurar las credenciales.",
            )
            return
        try:
            rows = google_sheets.read_report(creds, sid, sname)
        except Exception as e:
            messagebox.showerror("Error", str(e))
            return

        for widget in orders_frame.winfo_children():
            widget.destroy()
        order_vars.clear()

        for r in rows:
            text = f"OC {r['Orden de Compra']} - {r['Proveedor']} (Tarea {r['Tarea']})"
            var = tk.BooleanVar(value=False)
            chk = ttk.Checkbutton(
                orders_frame, text=text, variable=var, style="MyCheckbutton.TCheckbutton"
            )
            chk.pack(anchor="w", pady=2)
            order_vars.append((var, r))
        last_label.config(text=f"Datos cargados: {len(rows)} registros")
        canvas.update_idletasks()
        canvas.yview_moveto(0.0)

    def send_emails():
        selected = [r for var, r in order_vars if var.get()]
        if not selected:
            messagebox.showwarning("Advertencia", "No hay órdenes seleccionadas")
            return
        if formato_var.get() == "FORMATO":
            messagebox.showwarning("Advertencia", "Debe seleccionar un formato de correo.")
            return

        summaries = []
        for r in selected:
            oc = str(r["Orden de Compra"])
            if attach_var.get():
                info, error = despacho_logic.obtener_resumen_orden(oc)
                if info:
                    emails = ", ".join(info["emails"]) if info["emails"] else ""
                    summaries.append(f"OC {oc} -> {emails}")
                else:
                    summaries.append(f"OC {oc}: {error}")
            else:
                supplier = db.get_supplier_by_name(r.get("Proveedor"))
                if supplier:
                    emails = ", ".join(filter(None, [supplier[3], supplier[4]]))
                    summaries.append(f"OC {oc} -> {emails}")
                else:
                    summaries.append(
                        f"OC {oc}: Proveedor {r.get('Proveedor')} no encontrado"
                    )
        confirm_msg = (
            "\n".join(summaries)
            + f"\n\nFormato: {formato_var.get()}"
            + f"\n¿Enviar {len(selected)} correos?"
        )
        if not messagebox.askyesno("Confirmar", confirm_msg):
            return

        for r in selected:
            result = despacho_logic.process_order(
                email_session,
                str(r["Orden de Compra"]),
                include_pdf=attach_var.get(),
                template_name=formato_var.get(),
                cc_key="EMAIL_CC_SEGUIMIENTO",
                provider_name=r.get("Proveedor"),
            )
            log(result)
        messagebox.showinfo("Finalizado", "Proceso completado")

    select_all_var = tk.BooleanVar(value=False)

    def toggle_all():
        val = select_all_var.get()
        for var, _ in order_vars:
            var.set(val)

    btn_frame = ttk.Frame(frame, style="MyFrame.TFrame")
    btn_frame.grid(row=8, column=0, pady=10)
    ttk.Checkbutton(btn_frame, text="Marcar todas", variable=select_all_var, command=toggle_all, style="MyCheckbutton.TCheckbutton").pack(side="left", padx=5)
    ttk.Button(btn_frame, text="Cargar Reporte", style="MyButton.TButton", command=load_report).pack(side="left", padx=5)
    ttk.Button(btn_frame, text="Enviar Correos", style="MyButton.TButton", command=send_emails).pack(side="left", padx=5)


