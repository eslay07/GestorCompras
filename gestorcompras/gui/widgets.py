"""Componentes visuales reutilizables."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from gestorcompras.gui import theme


def page_header(parent: tk.Misc, title: str, subtitle: str) -> ttk.Frame:
    header = ttk.Frame(parent)
    header.pack(fill="x", pady=(0, 18))
    ttk.Label(header, text=title, style="Title.TLabel").pack(anchor="w")
    ttk.Label(header, text=subtitle, style="Subtitle.TLabel").pack(anchor="w", pady=(3, 0))
    return header


def card(parent: tk.Misc, *, padding: int = 18) -> tk.Frame:
    return tk.Frame(
        parent,
        bg=theme.SURFACE,
        highlightbackground=theme.BORDER,
        highlightthickness=1,
        padx=padding,
        pady=padding,
    )


def label_pair(parent: tk.Misc, label: str, value: str, row: int) -> None:
    tk.Label(
        parent,
        text=label,
        bg=theme.SURFACE,
        fg=theme.MUTED,
        font=("Segoe UI", 9),
        anchor="w",
    ).grid(row=row, column=0, sticky="w", pady=6)
    tk.Label(
        parent,
        text=value,
        bg=theme.SURFACE,
        fg=theme.TEXT,
        font=("Segoe UI", 10, "bold"),
        anchor="e",
    ).grid(row=row, column=1, sticky="e", padx=(30, 0), pady=6)


class MetricCard(tk.Frame):
    def __init__(self, parent: tk.Misc, value: str, label: str, accent: str) -> None:
        super().__init__(
            parent,
            bg=theme.SURFACE,
            highlightbackground=theme.BORDER,
            highlightthickness=1,
            padx=18,
            pady=16,
        )
        tk.Frame(self, bg=accent, width=5, height=46).pack(side="left", fill="y", padx=(0, 14))
        text = tk.Frame(self, bg=theme.SURFACE)
        text.pack(side="left", fill="both", expand=True)
        tk.Label(
            text,
            text=value,
            bg=theme.SURFACE,
            fg=theme.NAVY,
            font=("Segoe UI", 20, "bold"),
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            text,
            text=label,
            bg=theme.SURFACE,
            fg=theme.MUTED,
            font=("Segoe UI", 9),
            anchor="w",
        ).pack(anchor="w")


def status_banner(parent: tk.Misc, variable: tk.StringVar) -> tk.Label:
    return tk.Label(
        parent,
        textvariable=variable,
        bg=theme.ACCENT_SOFT,
        fg="#08745A",
        font=("Segoe UI", 9, "bold"),
        anchor="w",
        padx=12,
        pady=8,
    )
