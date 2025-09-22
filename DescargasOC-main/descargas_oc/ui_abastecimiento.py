"""Interfaz para descargar órdenes de compra de Abastecimiento."""
import threading
import tkinter as tk
from tkinter import messagebox
from tkinter import ttk

try:  # allow running as script
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
    root.title("Descarga Abastecimiento")
    root.tk_setPalette(
        background="#1e1e1e",
        foreground="#f0f0f0",
        activeBackground="#333333",
        activeForeground="#f0f0f0",
        highlightColor="#555555",
    )
    root.configure(bg="#1e1e1e")

    tk.Label(root, text="Fecha inicio (dd/mm/aa):").grid(row=0, column=0, sticky="e")
    entry_fd = tk.Entry(root)
    entry_fd.grid(row=0, column=1, padx=5, pady=2)

    tk.Label(root, text="Fecha final (dd/mm/aa):").grid(row=1, column=0, sticky="e")
    entry_fh = tk.Entry(root)
    entry_fh.grid(row=1, column=1, padx=5, pady=2)

    cfg = Config()
    tk.Label(root, text="Solicitante:").grid(row=2, column=0, sticky="e")
    solicitantes = cfg.abastecimiento_solicitantes or []
    if DEFAULT_SOLICITANTE not in solicitantes:
        solicitantes.insert(0, DEFAULT_SOLICITANTE)
    sol_var = tk.StringVar(value=DEFAULT_SOLICITANTE)
    entry_sol = ttk.Combobox(
        root,
        textvariable=sol_var,
        values=solicitantes,
        width=40,
    )
    entry_sol.grid(row=2, column=1, padx=5, pady=2)

    tk.Label(root, text="Autoriza:").grid(row=3, column=0, sticky="e")
    aut_var = tk.StringVar()
    entry_aut = ttk.Combobox(
        root,
        textvariable=aut_var,
        values=cfg.abastecimiento_autorizadores or [],
        width=40,
    )
    entry_aut.grid(row=3, column=1, padx=5, pady=2)

    var_visible = tk.BooleanVar(value=not bool(cfg.headless))

    def actualizar_visible():
        cfg.load()
        cfg.data["headless"] = not var_visible.get()
        cfg.save()

    chk_visible = tk.Checkbutton(
        root,
        text="Descarga visible",
        variable=var_visible,
        command=actualizar_visible,
        selectcolor="#00aa00",
    )
    chk_visible.grid(row=4, column=1, sticky="w", padx=5, pady=2)

    btn_ejecutar = tk.Button(
        root,
        text="Descargar",
        command=lambda: ejecutar(entry_fd, entry_fh, entry_sol, entry_aut, btn_ejecutar),
    )
    btn_ejecutar.grid(row=5, column=0, columnspan=2, pady=10)

#<<<<<<< codex/fix-email-scanning-for-descarga-normal-z71yhw
#=======
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

    btn_cfg = tk.Button(root, text="Configurar", command=abrir_config)
    btn_cfg.grid(row=6, column=0, columnspan=2, pady=(0, 10))

#>>>>>>> master
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
