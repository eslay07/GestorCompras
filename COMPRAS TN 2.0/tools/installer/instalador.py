"""Persistent installer UI; explicit CLI modes are for reproducible verification."""
from __future__ import annotations

import argparse
import json
import os
import queue
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path

from core import Installer


def payload():
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "payload"


def explanation(exc):
    if isinstance(exc, PermissionError):
        return "No se pudo escribir un archivo. Cierre el programa, use una carpeta de su usuario y revise si el antivirus bloqueó el archivo. No necesita contraseña de administrador."
    text = str(exc).casefold()
    if "dll" in text or "0xc000" in text:
        return "No se pudo cargar un componente de Windows. El paquete incluye las librerías nativas; revise los archivos en cuarentena y vuelva a ejecutar el instalador."
    if "timeout" in text or "timed out" in text:
        return "Una comprobación tardó demasiado. El registro identifica el proceso; cierre otras versiones y vuelva a intentar."
    if "espacio" in text:
        return "Libere espacio en la unidad indicada y vuelva a intentar."
    return "Corrija la causa indicada y pulse Instalar / actualizar otra vez. El registro conserva el detalle técnico y el respaldo de la base."


def gui(bundle):
    import tkinter as tk
    from tkinter import messagebox, scrolledtext, ttk
    window = tk.Tk()
    window.title("instalador · COMPRAS TN")
    window.geometry("930x680")
    window.minsize(680, 470)
    frame = ttk.Frame(window, padding=16)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="Instalar o actualizar COMPRAS TN", font=("Segoe UI", 18, "bold")).pack(anchor="w")
    ttk.Label(frame, text="Cierre todas las versiones del programa antes de continuar.\nConserva configuraciones y proveedores existentes; añade los que falten.\nNo importa contraseñas, credenciales de Google ni mensajes del buzón.", wraplength=850).pack(anchor="w", pady=12)
    status = tk.StringVar(value="Listo para instalar. No modifica PATH ni requiere permisos de administrador.")
    ttk.Label(frame, textvariable=status, wraplength=850, font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=12)
    text = scrolledtext.ScrolledText(frame, font=("Consolas", 10), height=18, state="disabled")
    text.pack(fill="both", expand=True)
    messages = queue.Queue()
    running = False
    log_folder = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "ComprasTN/installer-logs"
    logfile = log_folder / (datetime.now().strftime("instalador-%Y%m%d-%H%M%S") + ".log")
    log_error = ""
    try:
        log_folder.mkdir(parents=True, exist_ok=True)
        logfile.touch()
    except OSError as exc:
        log_error = str(exc)
    result = {}

    def log(value):
        messages.put(("log", str(value)))
        try:
            with logfile.open("a", encoding="utf-8") as stream:
                stream.write(str(value) + "\n")
        except OSError as exc:
            messages.put(("log", f"No se pudo escribir el registro: {exc}. El resultado sigue visible en esta ventana."))

    def worker():
        installer = Installer(bundle, log=log)
        try:
            result.update(installer.install())
            messages.put(("done", "INSTALADO CORRECTAMENTE"))
        except Exception as exc:
            detail = f"ERROR EN: {installer.step}\n{type(exc).__name__}: {exc}\n\n{explanation(exc)}"
            log(detail)
            log(traceback.format_exc())
            messages.put(("error", detail))

    def begin():
        nonlocal running
        if running:
            return
        running = True
        install.configure(state="disabled")
        status.set("Instalando… Esta ventana permanecerá abierta al terminar.")
        threading.Thread(target=worker, daemon=False).start()

    def poll():
        nonlocal running
        while not messages.empty():
            kind, value = messages.get_nowait()
            if kind == "log":
                text.configure(state="normal")
                text.insert("end", value + "\n")
                text.see("end")
                text.configure(state="disabled")
            else:
                running = False
                status.set(value if kind == "done" else "NO SE COMPLETÓ LA INSTALACIÓN. Consulte el error y el registro.")
                install.configure(state="normal")
                if kind == "error":
                    messagebox.showerror("Error de instalación", value, parent=window)
        window.after(150, poll)

    def close():
        if running:
            messagebox.showinfo("Instalación en curso", "Espere a que termine para cerrar. No se cerrará automáticamente.", parent=window)
        else:
            window.destroy()

    buttons = ttk.Frame(frame)
    buttons.pack(fill="x", pady=(14, 0))
    install = ttk.Button(buttons, text="Instalar / actualizar", command=begin)
    install.pack(side="left")
    ttk.Button(buttons, text="Abrir registro", command=lambda: os.startfile(logfile)).pack(side="left", padx=8)
    ttk.Button(buttons, text="Cerrar", command=close).pack(side="right")
    log("Registro: " + str(logfile))
    if log_error:
        log("No se pudo preparar el registro: " + log_error)
    window.protocol("WM_DELETE_WINDOW", close)
    window.after(150, poll)
    window.mainloop()


def main():
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, default=payload())
    parser.add_argument("--verify-package", action="store_true")
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--program", type=Path)
    parser.add_argument("--data", type=Path)
    parser.add_argument("--no-shortcuts", action="store_true")
    parser.add_argument("--skip-smoke", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.verify_package or args.install:
        lines = []
        def log(value):
            lines.append(str(value))
            if sys.stdout:
                print(value, flush=True)
        installer = Installer(args.bundle, args.program, log)
        try:
            if args.data:
                os.environ["COMPRAS_TN_DATA_DIR"] = str(args.data.resolve())
            output = installer.verify() if args.verify_package else installer.install(smoke=not args.skip_smoke, shortcuts=not args.no_shortcuts)
            report = {"success": True, "result": output, "log": lines}
        except Exception as exc:
            report = {"success": False, "step": installer.step, "error": str(exc), "traceback": traceback.format_exc(), "log": lines}
        if args.report:
            args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        return 0 if report["success"] else 1
    gui(args.bundle)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, f"No se pudo abrir el instalador:\n{type(exc).__name__}: {exc}", "instalador", 0x10)
        raise
