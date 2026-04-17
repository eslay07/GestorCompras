"""Pantalla de bienvenida que se muestra tras el login."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from gestorcompras import theme


class WelcomeScreen(ttk.Frame):
    def __init__(self, master: tk.Misc, email_session: dict[str, str]):
        super().__init__(master, style="MyFrame.TFrame")
        self._build(email_session)

    def _build(self, email_session: dict[str, str]) -> None:
        container = ttk.Frame(self, style="MyFrame.TFrame", padding=40)
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=1)

        ttk.Label(
            container,
            text="Bienvenido al Gestor de Compras",
            style="Banner.TLabel",
        ).grid(row=0, column=0, pady=(40, 10))

        user = email_session.get("address", "")
        if user:
            ttk.Label(
                container,
                text=user,
                style="MyLabel.TLabel",
                font=("Segoe UI", 11),
                foreground=theme.color_texto,
            ).grid(row=1, column=0, pady=(0, 30))

        hint = ttk.Label(
            container,
            text="Seleccione una opcion en el menu lateral para comenzar.",
            style="MyLabel.TLabel",
            font=("Segoe UI", 12),
            foreground="#6B7280",
        )
        hint.grid(row=2, column=0, pady=(10, 0))

        cards = ttk.Frame(container, style="MyFrame.TFrame")
        cards.grid(row=3, column=0, pady=(40, 0))

        sections = [
            ("Bienes", "Reasignacion, Correos,\nSeguimientos, Descargas,\nActualizar Tareas"),
            ("Servicios", "Reasignacion, Correos,\nDescargas, Actualizar Tareas"),
            ("Configuracion", "Parametros generales\ndel sistema"),
        ]
        for i, (title, desc) in enumerate(sections):
            card = tk.Frame(cards, bg="#F9FAFB", highlightbackground=theme.color_borde,
                            highlightthickness=1, padx=20, pady=16)
            card.grid(row=0, column=i, padx=12)

            tk.Label(card, text=title, font=("Segoe UI", 13, "bold"),
                     bg="#F9FAFB", fg=theme.color_titulos).pack(anchor="w")
            tk.Label(card, text=desc, font=("Segoe UI", 10),
                     bg="#F9FAFB", fg="#6B7280", justify="left").pack(anchor="w", pady=(6, 0))
