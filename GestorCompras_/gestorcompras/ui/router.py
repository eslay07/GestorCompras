"""Ruteo centralizado entre pantallas principales."""
from __future__ import annotations

import tkinter as tk

from gestorcompras.ui.home import HomeScreen
from gestorcompras.ui.bienes_home import BienesMenu
from gestorcompras.ui.servicios_home import ServiciosHome

_container: tk.Misc | None = None
_email_session: dict[str, str] | None = None


def configure(container: tk.Misc, email_session: dict[str, str]) -> None:
    global _container, _email_session
    _container = container
    _email_session = email_session
    open_home()


def _clear_container() -> None:
    if _container is None:
        raise RuntimeError("Router no inicializado")
    for widget in list(_container.winfo_children()):
        widget.destroy()


def open_home() -> None:
    _clear_container()
    screen = HomeScreen(_container, open_bienes_menu, open_servicios_menu)
    screen.pack(fill="both", expand=True)


def open_bienes_menu() -> None:
    if _email_session is None:
        raise RuntimeError("Sesión de correo no inicializada")
    _clear_container()
    BienesMenu(_container, _email_session).pack(fill="both", expand=True)


def open_servicios_menu() -> None:
    if _email_session is None:
        raise RuntimeError("Sesión de correo no inicializada")
    _clear_container()
    ServiciosHome(_container, _email_session).pack(fill="both", expand=True)
