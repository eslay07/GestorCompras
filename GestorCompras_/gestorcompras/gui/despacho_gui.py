import tkinter as tk
from tkinter import ttk, messagebox
from tkinter.scrolledtext import ScrolledText
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from gestorcompras.logic import despacho_logic

def open_despacho(master, email_session):
    window = tk.Toplevel(master)
    window.title("Solicitud de Despachos")
    window.geometry("520x400")
    window.transient(master)
    window.grab_set()
    
    main_frame = ttk.Frame(window, style="MyFrame.TFrame", padding=10)
    main_frame.pack(fill="both", expand=True)
    main_frame.rowconfigure(1, weight=1)
    main_frame.rowconfigure(2, weight=1)
    main_frame.columnconfigure(0, weight=1)
    
    label = ttk.Label(main_frame, text="Ingrese números de OC (una por línea):", style="MyLabel.TLabel")
    label.grid(row=0, column=0, sticky="w", pady=10)
    
    text_area = tk.Text(main_frame, height=10)
    text_area.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
    
    log_box = ScrolledText(main_frame, height=8, state="disabled")
    log_box.grid(row=2, column=0, sticky="nsew", padx=5, pady=5)
    
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

        previews = []
        valid_orders = []
        for orden in orders:
            ctx, err = despacho_logic.prepare_order_context(orden)
            if err:
                previews.append(err)
            else:
                previews.append(f"OC {orden} -> {ctx['email_to']}")
                valid_orders.append(orden)

        if not valid_orders:
            for line in previews:
                log_func(line)
            return

        summary = "\n".join(previews)
        if not messagebox.askyesno("Confirmar envío", f"Se enviarán {len(valid_orders)} correos:\n{summary}\n¿Continuar?"):
            return

        log_func("Procesando órdenes, espere...")

        def process_all_orders():
            results = []
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {executor.submit(despacho_logic.process_order, email_session, oc): oc for oc in valid_orders}
                for future in as_completed(futures):
                    orden = futures[future]
                    try:
                        result = future.result()
                    except Exception as e:
                        result = f"❌ Error al enviar el correo para OC {orden}: {str(e)}"
                    results.append(result)
                    log_func(result)
            errors = [r for r in results if not r.startswith("✅")]
            if errors:
                messagebox.showerror("Resultado de envío", "\n".join(errors))
            else:
                messagebox.showinfo("Resultado de envío", "Todos los correos fueron enviados correctamente.")

        threading.Thread(target=process_all_orders).start()
    
    btn_procesar = ttk.Button(main_frame, text="Procesar Despachos",
                               style="MyButton.TButton",
                               command=process_input_orders)
    btn_procesar.grid(row=3, column=0, pady=10)
