"""Sistema visual sobrio para la aplicación de portafolio."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

BACKGROUND = "#F4F7FB"
SURFACE = "#FFFFFF"
SURFACE_SOFT = "#F8FAFC"
NAVY = "#102A43"
NAVY_SOFT = "#243B53"
PRIMARY = "#2563EB"
PRIMARY_SOFT = "#DBEAFE"
ACCENT = "#0F9D7A"
ACCENT_SOFT = "#D1FAE5"
WARNING = "#C47F17"
WARNING_SOFT = "#FEF3C7"
TEXT = "#1F2937"
MUTED = "#64748B"
BORDER = "#DCE3EC"
DANGER = "#B42318"


def configure_styles(root: tk.Tk) -> None:
    root.configure(bg=BACKGROUND)
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")

    style.configure("TFrame", background=BACKGROUND)
    style.configure("Surface.TFrame", background=SURFACE)
    style.configure("Soft.TFrame", background=SURFACE_SOFT)
    style.configure("TLabel", background=BACKGROUND, foreground=TEXT, font=("Segoe UI", 10))
    style.configure("Surface.TLabel", background=SURFACE, foreground=TEXT, font=("Segoe UI", 10))
    style.configure("Muted.TLabel", background=BACKGROUND, foreground=MUTED, font=("Segoe UI", 10))
    style.configure("Title.TLabel", background=BACKGROUND, foreground=NAVY, font=("Segoe UI", 23, "bold"))
    style.configure("Subtitle.TLabel", background=BACKGROUND, foreground=MUTED, font=("Segoe UI", 10))
    style.configure(
        "Primary.TButton",
        background=PRIMARY,
        foreground="#FFFFFF",
        borderwidth=0,
        focusthickness=0,
        font=("Segoe UI", 10, "bold"),
        padding=(18, 10),
    )
    style.map("Primary.TButton", background=[("active", "#1D4ED8")])
    style.configure(
        "Secondary.TButton",
        background=SURFACE,
        foreground=NAVY,
        bordercolor=BORDER,
        borderwidth=1,
        focusthickness=0,
        font=("Segoe UI", 10, "bold"),
        padding=(16, 9),
    )
    style.map("Secondary.TButton", background=[("active", SURFACE_SOFT)])
    style.configure(
        "Treeview",
        background=SURFACE,
        fieldbackground=SURFACE,
        foreground=TEXT,
        borderwidth=0,
        rowheight=34,
        font=("Segoe UI", 9),
    )
    style.configure(
        "Treeview.Heading",
        background="#EAF0F7",
        foreground=NAVY,
        relief="flat",
        font=("Segoe UI", 9, "bold"),
        padding=(8, 8),
    )
    style.map("Treeview", background=[("selected", PRIMARY_SOFT)], foreground=[("selected", NAVY)])
    style.configure("TCombobox", padding=7, fieldbackground=SURFACE)
    style.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor="#E2E8F0", borderwidth=0)
