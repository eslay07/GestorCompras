"""Punto de entrada conservado para la antigua opción de Correos Masivos.

Tras revertir la pantalla al flujo clásico de *Solicitud de Despachos*,
se mantiene este alias para no romper referencias existentes.
"""
from gestorcompras.gui.despacho_gui import open_despacho as open

__all__ = ["open"]
