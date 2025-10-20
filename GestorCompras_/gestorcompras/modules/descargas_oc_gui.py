"""Punto de entrada reutilizable para la ventana de descargas de OC."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox, ttk

from gestorcompras.ui.common import add_hover_effect, center_window


def _find_descargas_root() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        candidate = (parent / "DescargasOC-main").resolve()
        if candidate.exists():
            return candidate
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
        try:
            subprocess.Popen([sys.executable, str(script)])
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
