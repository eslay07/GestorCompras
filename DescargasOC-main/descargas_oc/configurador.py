"""Puerta de entrada a la configuración centralizada de Descargas OC."""

from __future__ import annotations

import tkinter as tk


def _abrir_configuracion(section: str | None = None):
    """Abre la ventana de configuración global enfocada en Descargas OC."""

    try:
        from gestorcompras.gui.config_gui import open_config_gui
    except ImportError as exc:  # pragma: no cover - entorno sin módulo principal
        raise SystemExit(
            "El módulo de configuración general no está disponible. "
            "Ejecute la aplicación principal de GestorCompras para ajustar los parámetros."
        ) from exc

    root = tk._get_default_root()  # type: ignore[attr-defined]
    created = False
    if root is None:
        root = tk.Tk()
        root.withdraw()
        created = True

    open_config_gui(root, None, focus_descargas=True, section=section)

    if created:
        root.destroy()


def configurar():
    """Configura la descarga normal de órdenes de compra."""

    _abrir_configuracion(section=None)


def configurar_abastecimiento():
    """Configura los parámetros específicos del flujo de Abastecimiento."""

    _abrir_configuracion(section="abastecimiento")


if __name__ == "__main__":  # pragma: no cover
    configurar()
