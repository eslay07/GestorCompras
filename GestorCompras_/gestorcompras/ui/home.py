"""Pantalla inicial para seleccionar el flujo de compras."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from gestorcompras.ui.common import add_hover_effect


class HomeScreen(ttk.Frame):
    def __init__(self, master: tk.Misc, on_bienes, on_servicios):
        super().__init__(master, style="MyFrame.TFrame")
        self.master = master
        self._on_bienes = on_bienes
        self._on_servicios = on_servicios
        self._build()

    def _build(self) -> None:
        container = ttk.Frame(self, style="MyFrame.TFrame", padding=40)
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(1, weight=1)

        titulo = ttk.Label(
            container,
            text="¿Qué flujo desea abrir?",
            style="Banner.TLabel",
        )
        titulo.grid(row=0, column=0, pady=(10, 30))

        btn_bienes = ttk.Button(
            container,
            text="COMPRAS BIENES",
            style="MyButton.TButton",
            command=self._on_bienes,
        )
        btn_bienes.grid(row=1, column=0, pady=10, sticky="ew")
        btn_bienes.configure(width=30)
        add_hover_effect(btn_bienes)

        btn_servicios = ttk.Button(
            container,
            text="COMPRAS SERVICIOS",
            style="MyButton.TButton",
            command=self._on_servicios,
        )
        btn_servicios.grid(row=2, column=0, pady=10, sticky="ew")
        btn_servicios.configure(width=30)
        add_hover_effect(btn_servicios)
