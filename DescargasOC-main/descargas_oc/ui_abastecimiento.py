"""Interfaz para descargar órdenes de compra de Abastecimiento."""
import threading
import tkinter as tk
from tkinter import messagebox
from tkinter import ttk

try:  # permite ejecutar como script
    from .selenium_abastecimiento import descargar_abastecimiento
    from .config import Config
except ImportError:  # pragma: no cover
    from selenium_abastecimiento import descargar_abastecimiento
    from config import Config

lock = threading.Lock()

# Valor por defecto para el campo "Solicitante"
DEFAULT_SOLICITANTE = "1221 - HERRERA PUENTE WILLIAM"


def ejecutar(entry_fd, entry_fh, entry_sol, entry_aut, btn):
    if not lock.acquire(blocking=False):
        messagebox.showinfo("Proceso en curso", "Ya existe una descarga en ejecución")
        return

    fd = entry_fd.get().strip()
    fh = entry_fh.get().strip()
    sol = entry_sol.get().strip()
    aut = entry_aut.get().strip()
    cfg = Config()
    btn.config(state=tk.DISABLED)

    def tarea():
        try:
            descargar_abastecimiento(
                fd, fh, sol, aut, headless=cfg.abastecimiento_headless
            )
            messagebox.showinfo("Finalizado", "Proceso completado")
        except Exception as exc:
            messagebox.showerror("Error", str(exc))
        finally:
            lock.release()
            btn.config(state=tk.NORMAL)

    threading.Thread(target=tarea, daemon=True).start()


def main():
    root = tk.Tk()
    root.title("Descarga de Abastecimiento")
    root.geometry("580x460")
    root.tk_setPalette(
        background="#F3F4F6",
        foreground="#374151",
        activeBackground="#1D4ED8",
        activeForeground="#FFFFFF",
        highlightColor="#D1D5DB",
    )
    root.configure(bg="#F3F4F6")

    main_frame = tk.Frame(root, bg="#F3F4F6", padx=16, pady=12)
    main_frame.pack(fill="both", expand=True)

    tk.Label(main_frame, text="Descarga de Abastecimiento",
             font=("Segoe UI", 15, "bold"), fg="#111827", bg="#F3F4F6").pack(anchor="w")
    tk.Label(main_frame, text="Descargue ordenes de compra de abastecimiento por rango de fechas.",
             font=("Segoe UI", 10), fg="#6B7280", bg="#F3F4F6").pack(anchor="w", pady=(0, 8))
    ttk.Separator(main_frame, orient="horizontal").pack(fill="x", pady=(0, 10))

    fechas_lf = tk.LabelFrame(main_frame, text="Rango de fechas", padx=12, pady=10,
                               font=("Segoe UI", 10), fg="#374151", bg="#FFFFFF")
    fechas_lf.pack(fill="x", pady=(0, 8))
    fechas_lf.columnconfigure(1, weight=1)

    tk.Label(fechas_lf, text="Fecha inicio:", bg="#FFFFFF").grid(row=0, column=0, sticky="w", pady=4)
    entry_fd = tk.Entry(fechas_lf, width=20)
    entry_fd.grid(row=0, column=1, sticky="w", padx=8, pady=4)
    tk.Label(fechas_lf, text="Formato: dd/mm/aa", font=("Segoe UI", 9),
             fg="#6B7280", bg="#FFFFFF").grid(row=0, column=2, sticky="w")

    tk.Label(fechas_lf, text="Fecha final:", bg="#FFFFFF").grid(row=1, column=0, sticky="w", pady=4)
    entry_fh = tk.Entry(fechas_lf, width=20)
    entry_fh.grid(row=1, column=1, sticky="w", padx=8, pady=4)
    tk.Label(fechas_lf, text="Formato: dd/mm/aa", font=("Segoe UI", 9),
             fg="#6B7280", bg="#FFFFFF").grid(row=1, column=2, sticky="w")

    cfg = Config()
    params_lf = tk.LabelFrame(main_frame, text="Parametros de busqueda", padx=12, pady=10,
                               font=("Segoe UI", 10), fg="#374151", bg="#FFFFFF")
    params_lf.pack(fill="x", pady=(0, 8))
    params_lf.columnconfigure(1, weight=1)

    tk.Label(params_lf, text="Solicitante:", bg="#FFFFFF").grid(row=0, column=0, sticky="w", pady=4)
    solicitantes = cfg.abastecimiento_solicitantes or []
    if DEFAULT_SOLICITANTE not in solicitantes:
        solicitantes.insert(0, DEFAULT_SOLICITANTE)
    sol_var = tk.StringVar(value=DEFAULT_SOLICITANTE)
    entry_sol = ttk.Combobox(params_lf, textvariable=sol_var, values=solicitantes, width=42)
    entry_sol.grid(row=0, column=1, sticky="ew", padx=8, pady=4)

    tk.Label(params_lf, text="Autoriza:", bg="#FFFFFF").grid(row=1, column=0, sticky="w", pady=4)
    aut_var = tk.StringVar()
    entry_aut = ttk.Combobox(params_lf, textvariable=aut_var,
                              values=cfg.abastecimiento_autorizadores or [], width=42)
    entry_aut.grid(row=1, column=1, sticky="ew", padx=8, pady=4)

    tk.Label(params_lf, text="Seleccione los parametros configurados en la seccion de Configuracion.",
             font=("Segoe UI", 9), fg="#6B7280", bg="#FFFFFF").grid(
        row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))

    opciones_lf = tk.LabelFrame(main_frame, text="Opciones", padx=12, pady=10,
                                 font=("Segoe UI", 10), fg="#374151", bg="#FFFFFF")
    opciones_lf.pack(fill="x", pady=(0, 8))

    var_visible = tk.BooleanVar(value=not bool(cfg.headless))

    def actualizar_visible():
        cfg.load()
        cfg.data["headless"] = not var_visible.get()
        cfg.save()

    chk_visible = tk.Checkbutton(
        opciones_lf, text="Mostrar navegador durante la descarga",
        variable=var_visible, command=actualizar_visible,
        bg="#FFFFFF", selectcolor="#059669", anchor="w",
    )
    chk_visible.pack(anchor="w")

    btn_frame = tk.Frame(main_frame, bg="#F3F4F6")
    btn_frame.pack(fill="x", pady=(4, 4))

    btn_ejecutar = tk.Button(
        btn_frame, text="Descargar",
        command=lambda: ejecutar(entry_fd, entry_fh, entry_sol, entry_aut, btn_ejecutar),
        padx=16, pady=4,
    )
    btn_ejecutar.pack(side="left", padx=(0, 8))

    def abrir_config():
        configurar_abastecimiento()
        nuevo = Config()
        if entry_sol.winfo_exists():
            solicitantes = nuevo.abastecimiento_solicitantes or []
            if DEFAULT_SOLICITANTE not in solicitantes:
                solicitantes.insert(0, DEFAULT_SOLICITANTE)
            entry_sol['values'] = solicitantes
            sol_var.set(DEFAULT_SOLICITANTE)
        if entry_aut.winfo_exists():
            entry_aut['values'] = nuevo.abastecimiento_autorizadores or []

    btn_cfg = tk.Button(btn_frame, text="Configurar", command=abrir_config, padx=16, pady=4)
    btn_cfg.pack(side="left")

    status_lbl = tk.Label(main_frame, text="Listo para descargar.",
                          font=("Segoe UI", 9), fg="#6B7280", bg="#F3F4F6")
    status_lbl.pack(anchor="w", pady=(4, 0))

    def center_window(win):
        win.update_idletasks()
        w = win.winfo_width()
        h = win.winfo_height()
        x = (win.winfo_screenwidth() // 2) - (w // 2)
        y = (win.winfo_screenheight() // 2) - (h // 2)
        win.geometry(f"{w}x{h}+{x}+{y}")

    center_window(root)
    root.mainloop()


if __name__ == "__main__":  # pragma: no cover
    main()
