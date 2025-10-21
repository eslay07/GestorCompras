"""Fachada de conveniencia para los servicios de GestorCompras."""
from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

__all__ = [
    "db",
    "email_sender",
    "google_sheets",
    "reassign_bridge",
    "reassign_reporter",
]

_CACHE: dict[str, Any] = {}


def _load(name: str):
    module = import_module(f"{__name__}.{name}")
    _CACHE[name] = module
    globals()[name] = module
    return module


def __getattr__(name: str):  # pragma: no cover - solo para compatibilidad
    if name in __all__:
        return _CACHE.get(name) or _load(name)
    raise AttributeError(f"módulo '{__name__}' no tiene atributo '{name}'")


for _name in list(__all__):
    _load(_name)

if TYPE_CHECKING:  # pragma: no cover - solo para ayudas de tipo
    from . import db, email_sender, google_sheets, reassign_bridge, reassign_reporter
