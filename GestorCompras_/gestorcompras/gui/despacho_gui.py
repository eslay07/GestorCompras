import tkinter as tk
from tkinter import ttk, messagebox
from tkinter.scrolledtext import ScrolledText
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from gestorcompras.logic import despacho_logic
from gestorcompras.services import db

def open_despacho(master, email_session):
    window = tk.Toplevel(master)
    window.title("Solicitud de Despachos")
    window.geometry("600x450")
    window.transient(master)
    window.grab_set()
    
    main_frame = ttk.Frame(window, style="MyFrame.TFrame", padding=10)
    main_frame.pack(fill="both", expand=True)
    main_frame.rowconfigure(1, weight=1)
    main_frame.rowconfigure(3, weight=1)
    main_frame.columnconfigure(0, weight=1)
    
    label = ttk.Label(main_frame, text="Ingrese números de OC (una por línea):", style="MyLabel.TLabel")
    label.grid(row=0, column=0, sticky="w", pady=10)
    
    text_area = tk.Text(main_frame, height=10)
    text_area.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
    
    ttk.Label(main_frame, text="Estado del Proceso:", style="MyLabel.TLabel").grid(row=2, column=0, sticky="w")
    log_box = ScrolledText(main_frame, height=8, state="disabled")
    log_box.grid(row=3, column=0, sticky="nsew", padx=5, pady=5)

    ttk.Label(main_frame, text="Formato de correo:", style="MyLabel.TLabel").grid(row=4, column=0, sticky="w")
    formatos = ["Bienes", "Servicios"] + [tpl[1] for tpl in db.get_email_templates()]
    formato_var = tk.StringVar(value=db.get_config("EMAIL_TEMPLATE", "Bienes"))
    ttk.Combobox(main_frame, textvariable=formato_var, values=formatos, state="readonly").grid(row=4, column=0, sticky="e", padx=(150,0))
    
    def log_func(message):
        log_box.configure(state="normal")
        log_box.insert(tk.END, message + "\n")
        log_box.see(tk.END)
        log_box.configure(state="disabled")
    
    def process_input_orders():
        orders = [o.strip() for o in text_area.get("1.0", tk.END).splitlines() if o.strip()]
        if not orders:
            messagebox.showwarning("Advertencia", "Ingrese al menos un número de OC.")
            return

        summaries = []
        for oc in orders:
            info, error = despacho_logic.obtener_resumen_orden(oc)
            if info:
                emails = ", ".join(info["emails"]) if info["emails"] else ""
                summaries.append(f"OC {oc} -> {emails}")
            else:
                summaries.append(f"OC {oc}: {error}")
        if not summaries:
            return
        confirm_msg = (
            "\n".join(summaries)
            + f"\n\nFormato: {formato_var.get()}"
            + f"\n¿Enviar {len(orders)} correos?"
        )
        if not messagebox.askyesno("Confirmar envíos", confirm_msg):
            return

        log_func("Enviando correos, espere...")
        btn_procesar.configure(state="disabled")

        def process_all_orders():
            results = []
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = [
                    executor.submit(
                        despacho_logic.process_order,
                        email_session,
                        orden,
                        True,
                        formato_var.get(),
                        "EMAIL_CC_DESPACHO",
                    )
                    for orden in orders
                ]
                for future in as_completed(futures):
                    try:
                        result = future.result()
                    except Exception as e:
                        result = f"Error en el procesamiento: {str(e)}"
                    results.append(result)
                    log_func(result)
            messagebox.showinfo("Resultado", "\n".join(results))
            window.after(0, lambda: btn_procesar.configure(state="normal"))

        threading.Thread(target=process_all_orders).start()

    btn_procesar = ttk.Button(main_frame, text="Procesar Despachos",
                               style="MyButton.TButton",
                               command=process_input_orders)
    btn_procesar.grid(row=5, column=0, pady=10)
