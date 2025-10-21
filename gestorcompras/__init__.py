"""Puente de compatibilidad para exponer el paquete real ``GestorCompras_.gestorcompras``.

Este módulo asegura que ``import gestorcompras`` y las importaciones de sus
submódulos (``gestorcompras.services``, ``gestorcompras.gui``, etc.) funcionen
correctamente cuando la aplicación se ejecuta desde scripts raíz como
``COMPRAS.pyw``.
"""

from __future__ import annotations

import importlib
import sys

_BASE_PACKAGE = "GestorCompras_.gestorcompras"


def _bootstrap() -> None:
    """Registra el paquete real y sus submódulos clave en ``sys.modules``."""

    package = importlib.import_module(_BASE_PACKAGE)
    sys.modules[__name__] = package

    # Pre-cargamos los subpaquetes más utilizados para que las importaciones
    # del estilo ``from gestorcompras.services import db`` funcionen aunque el
    # script principal viva fuera del paquete real.
    for subpkg in ("core", "data", "gui", "logic", "modules", "services", "ui"):
        full_name = f"{_BASE_PACKAGE}.{subpkg}"
        module = importlib.import_module(full_name)
        sys.modules[f"{__name__}.{subpkg}"] = module
        setattr(package, subpkg, module)


_bootstrap()

