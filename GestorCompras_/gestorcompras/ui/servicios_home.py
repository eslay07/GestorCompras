"""Menú principal para el flujo de Compras Servicios."""
from __future__ import annotations

from typing import Callable

import tkinter as tk
from tkinter import ttk

from gestorcompras.modules import correos_masivos_gui, descargas_oc_gui, config_gui, reasignacion_gui
from gestorcompras.ui.common import add_hover_effect


class ServiciosHome(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        email_session: dict[str, str],
        on_back: Callable[[], None] | None = None,
    ):
        super().__init__(master, style="MyFrame.TFrame")
        self.master = master
        self.email_session = email_session
        self._on_back = on_back
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

        if self._on_back is not None:
            back_btn = ttk.Button(
                container,
                text="Volver",
                style="SecondaryButton.TButton",
                command=self._on_back,
            )
            back_btn.grid(row=1, column=0, pady=(0, 20), sticky="ew")
            add_hover_effect(back_btn)
            start_row = 2
        else:
            start_row = 1

        self._add_button(
            container,
            row=start_row,
            text="Configuraciones",
            command=lambda: config_gui.open(self.master, self.email_session, mode="servicios"),
        )
        self._add_button(
            container,
            row=start_row + 1,
            text="Correos Masivos",
            command=lambda: correos_masivos_gui.open(self.master, self.email_session),
        )
        self._add_button(
            container,
            row=start_row + 2,
            text="Descargas OC",
            command=lambda: descargas_oc_gui.open(self.master),
        )
        self._add_button(
            container,
            row=start_row + 3,
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
