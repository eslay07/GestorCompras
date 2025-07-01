import tkinter as tk
from tkinter import ttk, messagebox
from tkinter.scrolledtext import ScrolledText

from gestorcompras.services import db
from gestorcompras.services import google_sheets
from gestorcompras.logic import despacho_logic


def open_sheet_report(master, email_session):
    window = tk.Toplevel(master)
    window.title("Reporte Google Sheets")
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

    tree = ttk.Treeview(frame, columns=("tarea", "oc", "proveedor"), show="headings", style="MyTreeview.Treeview")
    tree.heading("tarea", text="Tarea")
    tree.heading("oc", text="Orden")
    tree.heading("proveedor", text="Proveedor")
    tree.grid(row=3, column=0, sticky="nsew", pady=5)

    log_box = ScrolledText(frame, height=6, state="disabled")
    log_box.grid(row=6, column=0, sticky="nsew", pady=5)

    ttk.Label(frame, text="Formato de correo:", style="MyLabel.TLabel").grid(row=4, column=0, sticky="w")
    formatos = ["Bienes", "Servicios"] + [tpl[1] for tpl in db.get_email_templates()]
    formato_var = tk.StringVar(value=db.get_config("EMAIL_TEMPLATE", "Bienes"))
    ttk.Combobox(frame, textvariable=formato_var, values=formatos, state="readonly").grid(row=4, column=0, sticky="e", padx=(150,0))

    attach_var = tk.BooleanVar(value=True)
    ttk.Checkbutton(frame, text="Adjuntar PDF", variable=attach_var, style="MyCheckbutton.TCheckbutton").grid(row=7, column=0, sticky="w")

    def log(msg: str):
        log_box.configure(state="normal")
        log_box.insert(tk.END, msg + "\n")
        log_box.see(tk.END)
        log_box.configure(state="disabled")

    def load_report():
        creds = db.get_config("GOOGLE_CREDS", "")
        if not (creds and sid and sname):
            messagebox.showwarning("Advertencia", "Debe completar Spreadsheet ID y nombre de hoja y configurar las credenciales.")
            return
        try:
            rows = google_sheets.read_report(creds, sid, sname)
        except Exception as e:
            messagebox.showerror("Error", str(e))
            return
        for i in tree.get_children():
            tree.delete(i)
        for r in rows:
            tree.insert("", "end", values=(r["Tarea"], r["Orden de Compra"], r["Proveedor"]))
        last_label.config(text=f"Datos cargados: {len(rows)} registros")

    def send_emails():
        items = tree.get_children()
        if not items:
            messagebox.showwarning("Advertencia", "No hay datos para enviar")
            return
        if not messagebox.askyesno("Confirmar", f"¿Enviar {len(items)} correos?"):
            return
        for it in items:
            tarea, oc, prov = tree.item(it)["values"]
            result = despacho_logic.process_order(
                email_session,
                str(oc),
                include_pdf=attach_var.get(),
                template_name=formato_var.get(),
            )
            log(result)
        messagebox.showinfo("Finalizado", "Proceso completado")

    btn_frame = ttk.Frame(frame, style="MyFrame.TFrame")
    btn_frame.grid(row=8, column=0, pady=10)
    ttk.Button(btn_frame, text="Cargar Reporte", style="MyButton.TButton", command=load_report).pack(side="left", padx=5)
    ttk.Button(btn_frame, text="Enviar Correos", style="MyButton.TButton", command=send_emails).pack(side="left", padx=5)


