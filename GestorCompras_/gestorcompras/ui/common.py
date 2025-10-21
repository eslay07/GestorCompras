"""Utilidades compartidas para las pantallas de la interfaz."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


def center_window(win: tk.Tk | tk.Toplevel) -> None:
    win.update_idletasks()
    w = win.winfo_width()
    h = win.winfo_height()
    x = (win.winfo_screenwidth() // 2) - (w // 2)
    y = (win.winfo_screenheight() // 2) - (h // 2)
    win.geometry(f"{w}x{h}+{x}+{y}")


def add_hover_effect(btn: ttk.Button) -> None:
    """Añade un estilo alternativo mientras el cursor está sobre el botón."""

    def on_enter(_):
        btn.configure(style="MyButtonHover.TButton")

    def on_leave(_):
        btn.configure(style="MyButton.TButton")

    btn.bind("<Enter>", on_enter)
    btn.bind("<Leave>", on_leave)
