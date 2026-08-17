from __future__ import annotations

import tkinter as tk

import pytest

from gestorcompras.gui.app import DemoApplication
from gestorcompras.gui.screens import SCREEN_CLASSES


def test_navigation_between_all_demo_screens() -> None:
    try:
        app = DemoApplication()
    except tk.TclError as exc:
        pytest.skip(f"Interfaz no disponible: {exc}")

    try:
        app.withdraw()
        assert app.active_screen == "login"
        app.enter_demo()
        for screen in SCREEN_CLASSES:
            app.show_screen(screen)
            app.update_idletasks()
            assert app.active_screen == screen
            assert app._content is not None
            assert len(app._content.winfo_children()) == 1
    finally:
        app.destroy()
