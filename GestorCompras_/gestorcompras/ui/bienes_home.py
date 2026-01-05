"""Menú principal para el flujo de Compras Bienes."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from gestorcompras.gui import config_gui, seguimientos_gui
from gestorcompras.modules import correos_masivos_gui, descargas_oc_gui, reasignacion_gui
from gestorcompras.ui.common import add_hover_effect
from gestorcompras import theme

bg_frame = theme.bg_frame
color_texto = theme.color_texto
color_titulos = theme.color_titulos
color_primario = theme.color_primario
color_acento = theme.color_acento


def _button_specs():
    return [
        ("Reasignación de Tareas", "open_reasignacion"),
        ("Correos Masivos", "open_correos_masivos"),
        ("Seguimientos", "open_seguimientos"),
        ("Descargas OC", "open_descargas_oc"),
        ("Cotizador", "open_cotizador"),
        ("Configuración", "open_config"),
        ("Salir", "quit"),
    ]


class BienesMenu(ttk.Frame):
    """Menú existente adaptado para el ruteo desde la pantalla inicial."""

    def __init__(self, master: tk.Misc, email_session: dict[str, str]):
        super().__init__(master, style="MyFrame.TFrame")
        self.master = master
        self.email_session = email_session
        self._banner_colors = [color_primario, color_acento]
        self._color_index = 0
        self._button_widgets: list[ttk.Button] = []
        self._buttons = _button_specs()
        self._build()

    def _build(self) -> None:
        container = ttk.Frame(self, style="MyFrame.TFrame")
        container.pack(fill="both", expand=True)

        self.banner = ttk.Label(container, text="Sistema de automatización - compras")
        self.banner.configure(font=("Segoe UI", 20, "bold"), foreground=color_titulos)
        self.banner.pack(pady=(20, 10))
        self.after(0, self._animate_banner)

        menu_frame = ttk.Frame(container, style="MyFrame.TFrame", padding=20)
        menu_frame.pack(pady=20)
        menu_frame.columnconfigure(0, weight=1)

        lbl_title = ttk.Label(menu_frame, text="Compras Bienes", style="MyLabel.TLabel")
        lbl_title.configure(font=("Segoe UI", 11, "bold"), foreground=color_titulos)
        lbl_title.grid(row=0, column=0, pady=15, sticky="n")

        self.menu_frame = menu_frame
        self._show_button(0)

    def _animate_banner(self) -> None:
        color = self._banner_colors[self._color_index]
        self.banner.configure(foreground=color)
        self._color_index = (self._color_index + 1) % len(self._banner_colors)
        self.after(800, self._animate_banner)

    def _show_button(self, index: int) -> None:
        if index >= len(self._buttons):
            return
        text, method_name = self._buttons[index]
        command = getattr(self, method_name)
        btn = ttk.Button(self.menu_frame, text=text, style="MyButton.TButton", command=command)
        btn.grid(row=index + 1, column=0, padx=20, pady=5, sticky="ew")
        add_hover_effect(btn)
        self._button_widgets.append(btn)
        self.after(120, self._show_button, index + 1)

    # --- Acciones ---
    def open_reasignacion(self) -> None:
        reasignacion_gui.open(self.master, self.email_session, mode="bienes")

    def open_correos_masivos(self) -> None:
        # Alias que mantiene compatibilidad con la UI anterior
        correos_masivos_gui.open(self.master, self.email_session)

    def open_seguimientos(self) -> None:
        seguimientos_gui.open_seguimientos(self.master, self.email_session)

    def open_descargas_oc(self) -> None:
        descargas_oc_gui.open(self.master, self.email_session)

    def open_config(self) -> None:
        config_gui.open_config_gui(self.master, self.email_session)

    def open_cotizador(self) -> None:
        messagebox.showinfo("Cotizador", "Esta opción se encuentra en desarrollo", parent=self.master)

    def quit(self) -> None:
        if isinstance(self.master, tk.Tk):
            self.master.quit()
        else:
            self.master.winfo_toplevel().quit()


__all__ = ["BienesMenu"]
