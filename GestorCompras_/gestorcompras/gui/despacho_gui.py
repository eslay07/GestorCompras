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
        orders = text_area.get("1.0", tk.END).strip().splitlines()
        if not orders:
            messagebox.showwarning("Advertencia", "Ingrese al menos un número de OC.")
            return
        log_func("Procesando órdenes, espere...")
        
        def process_all_orders():
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = [executor.submit(despacho_logic.process_order, email_session, orden) for orden in orders]
                for future in as_completed(futures):
                    try:
                        result = future.result()
                        log_func(result)
                    except Exception as e:
                        log_func(f"Error en el procesamiento: {str(e)}")
        
        threading.Thread(target=process_all_orders).start()
    
    btn_procesar = ttk.Button(main_frame, text="Procesar Despachos",
                               style="MyButton.TButton",
                               command=process_input_orders)
    btn_procesar.grid(row=3, column=0, pady=10)
