"""Barra lateral de navegacion fija."""
from __future__ import annotations

import tkinter as tk
from gestorcompras import theme

SIDEBAR_WIDTH = 220

_SECTIONS = [
    {
        "header": "BIENES",
        "items": [
            ("bienes_reasignacion", "Reasignacion"),
            ("bienes_correos", "Correos Masivos"),
            ("bienes_seguimientos", "Seguimientos"),
            ("bienes_descargas", "Descargar Ordenes"),
            ("bienes_actua", "Actualizar Tareas"),
        ],
    },
    {
        "header": "SERVICIOS",
        "items": [
            ("servicios_reasignacion", "Reasignacion"),
            ("servicios_correos", "Correos Masivos"),
            ("servicios_descargas", "Descargar Ordenes"),
            ("servicios_actua", "Actualizar Tareas"),
        ],
    },
]

_FOOTER_ITEMS = [
    ("config", "Configuracion"),
    ("logout", "Cerrar Sesion"),
]


class Sidebar(tk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        email_session: dict[str, str],
        on_navigate,
    ):
        super().__init__(master, bg=theme.sidebar_bg, width=SIDEBAR_WIDTH)
        self.pack_propagate(False)
        self._on_navigate = on_navigate
        self._items: dict[str, tk.Frame] = {}
        self._active_id: str | None = None
        self._build(email_session)

    def _build(self, email_session: dict[str, str]) -> None:
        title = tk.Label(
            self, text="Gestor Compras", font=("Segoe UI", 14, "bold"),
            bg=theme.sidebar_bg, fg="#FFFFFF", anchor="w",
        )
        title.pack(fill="x", padx=16, pady=(16, 2))

        user_email = email_session.get("address", "")
        user_lbl = tk.Label(
            self, text=user_email, font=("Segoe UI", 9),
            bg=theme.sidebar_bg, fg=theme.sidebar_text, anchor="w",
        )
        user_lbl.pack(fill="x", padx=16, pady=(0, 12))

        sep = tk.Frame(self, bg=theme.sidebar_hover_bg, height=1)
        sep.pack(fill="x", padx=12, pady=(0, 8))

        for section in _SECTIONS:
            hdr = tk.Label(
                self, text=section["header"], font=("Segoe UI", 9, "bold"),
                bg=theme.sidebar_bg, fg="#94A3B8", anchor="w",
            )
            hdr.pack(fill="x", padx=16, pady=(10, 4))
            for module_id, label in section["items"]:
                self._add_item(module_id, label)

        spacer = tk.Frame(self, bg=theme.sidebar_bg)
        spacer.pack(fill="both", expand=True)

        sep2 = tk.Frame(self, bg=theme.sidebar_hover_bg, height=1)
        sep2.pack(fill="x", padx=12, pady=4)

        for module_id, label in _FOOTER_ITEMS:
            self._add_item(module_id, label)

        pad_bottom = tk.Frame(self, bg=theme.sidebar_bg, height=12)
        pad_bottom.pack(fill="x")

    def _add_item(self, module_id: str, label: str) -> None:
        row = tk.Frame(self, bg=theme.sidebar_bg, cursor="hand2")
        row.pack(fill="x", padx=8, pady=1)

        dot = tk.Canvas(row, width=8, height=8, bg=theme.sidebar_bg, highlightthickness=0)
        dot.pack(side="left", padx=(8, 6), pady=8)
        dot.create_oval(1, 1, 7, 7, fill=theme.sidebar_text, outline="")

        lbl = tk.Label(
            row, text=label, font=("Segoe UI", 11),
            bg=theme.sidebar_bg, fg=theme.sidebar_text, anchor="w",
        )
        lbl.pack(side="left", fill="x", expand=True, pady=6)

        for w in (row, lbl, dot):
            w.bind("<Enter>", lambda _e, r=row, l=lbl, d=dot: self._hover(r, l, d, True))
            w.bind("<Leave>", lambda _e, r=row, l=lbl, d=dot: self._hover(r, l, d, False))
            w.bind("<Button-1>", lambda _e, mid=module_id: self._click(mid))

        self._items[module_id] = row

    def _hover(self, row: tk.Frame, lbl: tk.Label, dot: tk.Canvas, enter: bool) -> None:
        if self._active_id and row is self._items.get(self._active_id):
            return
        bg = theme.sidebar_hover_bg if enter else theme.sidebar_bg
        for w in (row, lbl):
            w.configure(bg=bg)
        dot.configure(bg=bg)

    def _click(self, module_id: str) -> None:
        self.set_active(module_id)
        if self._on_navigate:
            self._on_navigate(module_id)

    def set_active(self, module_id: str) -> None:
        if self._active_id and self._active_id in self._items:
            old = self._items[self._active_id]
            for w in old.winfo_children():
                w.configure(bg=theme.sidebar_bg)
                if isinstance(w, tk.Label):
                    w.configure(fg=theme.sidebar_text)
            old.configure(bg=theme.sidebar_bg)

        self._active_id = module_id
        if module_id in self._items:
            row = self._items[module_id]
            row.configure(bg=theme.sidebar_active_bg)
            for w in row.winfo_children():
                w.configure(bg=theme.sidebar_active_bg)
                if isinstance(w, tk.Label):
                    w.configure(fg="#FFFFFF")
