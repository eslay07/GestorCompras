"""Punto de entrada reutilizable para la ventana de descargas de OC."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox, ttk

from gestorcompras.ui.common import add_hover_effect, center_window


def _find_descargas_root() -> Path | None:
    """Busca el directorio raíz del módulo Descargas OC."""

    posibles_nombres = ("DescargasOC-main", "DescargasOC")
    for parent in Path(__file__).resolve().parents:
        for nombre in posibles_nombres:
            candidate = (parent / nombre).resolve()
            if (candidate / "descargas_oc").exists():
                return candidate

    # Fallback al directorio de trabajo actual (útil en ejecutables empaquetados)
    cwd = Path.cwd()
    for nombre in posibles_nombres:
        candidate = (cwd / nombre).resolve()
        if (candidate / "descargas_oc").exists():
            return candidate

    return None


def _python_command() -> list[str] | None:
    """Determina el intérprete adecuado para lanzar los scripts auxiliares."""

    if not getattr(sys, "frozen", False):
        return [sys.executable]

    env_override = os.getenv("PYTHON_EXECUTABLE")
    if env_override:
        return [env_override]

    candidatos = [
        "pythonw.exe",
        "python.exe",
        "python3",
        "python",
    ]
    for cand in candidatos:
        found = shutil.which(cand)
        if found:
            return [found]
    return None


_DESCARGAS_ROOT = _find_descargas_root()


def open(master: tk.Misc) -> None:
    """Abre el selector para iniciar los módulos de descargas de OC."""
    option_win = tk.Toplevel(master)
    option_win.title("Descargas OC")
    option_win.transient(master)
    option_win.grab_set()
    center_window(option_win)

    ttk.Label(
        option_win,
        text="Seleccione el tipo de descarga:",
        style="MyLabel.TLabel",
    ).pack(padx=10, pady=10)

    def _launch(script_name: str, error_title: str) -> None:
        if _DESCARGAS_ROOT is None:
            messagebox.showerror(
                "Descargas OC",
                "No se encontró la carpeta 'DescargasOC-main'.",
                parent=option_win,
            )
            return
        script = _DESCARGAS_ROOT / "descargas_oc" / script_name
        python_cmd = _python_command()
        if python_cmd is None:
            messagebox.showerror(
                error_title,
                "No se encontró un intérprete de Python para ejecutar Descargas OC.",
                parent=option_win,
            )
            return
        try:
            subprocess.Popen(
                [*python_cmd, str(script)],
                cwd=str(_DESCARGAS_ROOT),
            )
        except OSError as exc:  # pragma: no cover - errores del SO
            messagebox.showerror(
                error_title,
                (
                    f"No se pudo abrir el módulo {script_name}. "
                    f"Detalle: {exc}"
                ),
                parent=option_win,
            )
            return
        option_win.destroy()

    btn_norm = ttk.Button(
        option_win,
        text="Descarga Normal",
        style="MyButton.TButton",
        command=lambda: _launch("ui.py", "Error"),
    )
    btn_norm.pack(padx=10, pady=5)
    add_hover_effect(btn_norm)

    btn_abast = ttk.Button(
        option_win,
        text="Abastecimiento",
        style="MyButton.TButton",
        command=lambda: _launch("ui_abastecimiento.py", "Error"),
    )
    btn_abast.pack(padx=10, pady=5)
    add_hover_effect(btn_abast)
