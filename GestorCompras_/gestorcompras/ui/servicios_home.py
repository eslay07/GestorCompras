"""Menú principal para el flujo de Compras Servicios."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from gestorcompras.modules import correos_masivos_gui, descargas_oc_gui, config_gui, reasignacion_gui
from gestorcompras.ui.common import add_hover_effect


class ServiciosHome(ttk.Frame):
    def __init__(self, master: tk.Misc, email_session: dict[str, str]):
        super().__init__(master, style="MyFrame.TFrame")
        self.master = master
        self.email_session = email_session
        self._build()

    def _build(self) -> None:
        container = ttk.Frame(self, style="MyFrame.TFrame", padding=30)
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=1)

        titulo = ttk.Label(
            container,
            text="Compras Servicios",
            style="Banner.TLabel",
        )
        titulo.grid(row=0, column=0, pady=(10, 30))

        self._add_button(
            container,
            row=1,
            text="Configuraciones",
            command=lambda: config_gui.open(self.master, self.email_session, mode="servicios"),
        )
        self._add_button(
            container,
            row=2,
            text="Correos Masivos",
            command=lambda: correos_masivos_gui.open(self.master, self.email_session),
        )
        self._add_button(
            container,
            row=3,
            text="Descargas OC",
            command=lambda: descargas_oc_gui.open(self.master, self.email_session),
        )
        self._add_button(
            container,
            row=4,
            text="Reasignación de tareas",
            command=lambda: reasignacion_gui.open(self.master, self.email_session, mode="servicios"),
        )

    def _add_button(self, container: ttk.Frame, row: int, text: str, command) -> None:
        btn = ttk.Button(
            container,
            text=text,
            style="MyButton.TButton",
            command=command,
        )
        btn.grid(row=row, column=0, pady=10, sticky="ew")
        btn.configure(width=35)
        add_hover_effect(btn)
