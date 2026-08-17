"""Genera capturas nuevas y reproducibles de la ventana demostrativa."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from pathlib import Path
import sys
import time

from PIL import ImageGrab

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from gestorcompras.gui.app import create_app  # noqa: E402


CAPTURES = (
    ("01_login_demo.png", "login"),
    ("02_inicio_demo.png", "inicio"),
    ("03_configuracion_demo.png", "configuracion"),
    ("04_correos_demo.png", "correos"),
    ("05_reasignacion_demo.png", "reasignacion"),
    ("06_descargas_demo.png", "descargas"),
    ("07_actualizar_tareas_demo.png", "actualizar_tareas"),
)


def _enable_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def _window_bounds(app) -> tuple[int, int, int, int]:
    app.update_idletasks()
    if sys.platform == "win32":
        hwnd = ctypes.windll.user32.GetAncestor(app.winfo_id(), 2)
        rect = wintypes.RECT()
        extended_frame_bounds = 9
        result = ctypes.windll.dwmapi.DwmGetWindowAttribute(
            hwnd,
            extended_frame_bounds,
            ctypes.byref(rect),
            ctypes.sizeof(rect),
        )
        if result == 0:
            return rect.left, rect.top, rect.right, rect.bottom
        if ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return rect.left, rect.top, rect.right, rect.bottom
    x = app.winfo_rootx()
    y = app.winfo_rooty()
    return x, y, x + app.winfo_width(), y + app.winfo_height()


def _capture(app, destination: Path) -> None:
    app.deiconify()
    app.lift()
    app.attributes("-topmost", True)
    app.update()
    time.sleep(0.25)
    bounds = _window_bounds(app)
    image = ImageGrab.grab(bbox=bounds, all_screens=True)
    image.save(destination, format="PNG", optimize=True)
    app.attributes("-topmost", False)


def main() -> int:
    _enable_dpi_awareness()
    output_dir = PROJECT_ROOT / "docs" / "images"
    output_dir.mkdir(parents=True, exist_ok=True)
    app = create_app()
    try:
        app.geometry("1280x760+40+40")
        app.update()
        for filename, screen in CAPTURES:
            if screen == "login":
                app.show_login()
            else:
                if app.active_screen == "login":
                    app.enter_demo()
                app.show_screen(screen)
            _capture(app, output_dir / filename)
            print(f"Captura generada: docs\\images\\{filename}")
    finally:
        app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
