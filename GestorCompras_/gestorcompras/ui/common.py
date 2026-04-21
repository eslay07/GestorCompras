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
    def on_enter(_):
        btn.configure(style="MyButtonHover.TButton")

    def on_leave(_):
        btn.configure(style="MyButton.TButton")

    btn.bind("<Enter>", on_enter)
    btn.bind("<Leave>", on_leave)


class ToolTip:
    """Tooltip ligero que aparece al pasar el cursor sobre un widget."""

    def __init__(self, widget: tk.Widget, text: str):
        self.widget = widget
        self.text = text
        self._tip: tk.Toplevel | None = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")

    def _show(self, _event=None) -> None:
        if self._tip or not self.text:
            return
        x = self.widget.winfo_rootx() + 16
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self._tip = tk.Toplevel(self.widget)
        self._tip.wm_overrideredirect(True)
        self._tip.wm_geometry(f"+{x}+{y}")
        lbl = tk.Label(
            self._tip,
            text=self.text,
            justify="left",
            bg="#FFFBEB",
            fg="#374151",
            relief="solid",
            borderwidth=1,
            padx=8,
            pady=4,
            font=("Segoe UI", 10),
            wraplength=300,
        )
        lbl.pack()

    def _hide(self, _event=None) -> None:
        if self._tip:
            self._tip.destroy()
            self._tip = None


def create_tooltip(widget: tk.Widget, text: str) -> ToolTip:
    return ToolTip(widget, text)
