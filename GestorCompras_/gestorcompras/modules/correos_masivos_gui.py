"""Módulo de compatibilidad para la interfaz de Correos Masivos.

Este archivo mantiene el punto de entrada esperado por el menú de
navegación. Internamente reutiliza la implementación previa ubicada en
:mod:`gestorcompras.gui.despacho_gui` para evitar duplicar lógica.
"""
from gestorcompras.gui.despacho_gui import open_despacho as open

__all__ = ["open"]
