"""Compatibilidad de menú para abrir la configuración general."""
from __future__ import annotations

import tkinter as tk

from gestorcompras.gui import config_gui as bienes_config


def open(master: tk.Misc, email_session: dict[str, str] | None = None, mode: str = "bienes") -> None:
    """Reutiliza la ventana de configuración existente.

    El flujo de Servicios comparte los mismos parámetros de asignación que
    Compras Bienes, por lo que se delega completamente a la interfaz
    tradicional.
    """

    bienes_config.open_config_gui(master, email_session)


__all__ = ["open"]
