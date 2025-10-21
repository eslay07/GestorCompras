"""Fachada de conveniencia para los servicios de GestorCompras."""
from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

__all__ = [
    "db",
    "email_sender",
    "google_sheets",
    "reassign_bridge",
    "reassign_reporter",
]


def _load(name: str):
    module = import_module(f"{__name__}.{name}")
    globals()[name] = module
    return module


for _name in list(__all__):
    _load(_name)

if TYPE_CHECKING:  # pragma: no cover - solo para ayudas de tipo
    from . import db, email_sender, google_sheets, reassign_bridge, reassign_reporter
