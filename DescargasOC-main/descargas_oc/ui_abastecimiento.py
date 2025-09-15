"""Interfaz para descargar órdenes de compra de Abastecimiento."""
import threading
import tkinter as tk
from tkinter import messagebox

try:  # allow running as script
    from .configurador import configurar
    from .selenium_abastecimiento import descargar_abastecimiento
    from .config import Config
except ImportError:  # pragma: no cover
    from configurador import configurar
    from selenium_abastecimiento import descargar_abastecimiento
    from config import Config

lock = threading.Lock()


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
            descargar_abastecimiento(fd, fh, sol, aut, headless=cfg.headless)
            messagebox.showinfo("Finalizado", "Proceso completado")
        except Exception as exc:
            messagebox.showerror("Error", str(exc))
        finally:
            lock.release()
            btn.config(state=tk.NORMAL)

    threading.Thread(target=tarea, daemon=True).start()


def main():
    root = tk.Tk()
    root.title("Descargas OC - Abastecimiento")

    tk.Label(root, text="Fecha desde (dd/mm/aa):").grid(row=0, column=0, sticky="e")
    entry_fd = tk.Entry(root)
    entry_fd.grid(row=0, column=1, padx=5, pady=2)

    tk.Label(root, text="Fecha hasta (dd/mm/aa):").grid(row=1, column=0, sticky="e")
    entry_fh = tk.Entry(root)
    entry_fh.grid(row=1, column=1, padx=5, pady=2)

    tk.Label(root, text="Solicitante:").grid(row=2, column=0, sticky="e")
    entry_sol = tk.Entry(root, width=40)
    entry_sol.grid(row=2, column=1, padx=5, pady=2)

    tk.Label(root, text="Autoriza:").grid(row=3, column=0, sticky="e")
    entry_aut = tk.Entry(root, width=40)
    entry_aut.grid(row=3, column=1, padx=5, pady=2)

    btn_ejecutar = tk.Button(
        root,
        text="Ejecutar descarga",
        command=lambda: ejecutar(entry_fd, entry_fh, entry_sol, entry_aut, btn_ejecutar),
    )
    btn_ejecutar.grid(row=4, column=0, columnspan=2, pady=10)

    btn_cfg = tk.Button(root, text="Configurar", command=configurar)
    btn_cfg.grid(row=5, column=0, columnspan=2, pady=(0, 10))

    root.mainloop()


if __name__ == "__main__":  # pragma: no cover
    main()
