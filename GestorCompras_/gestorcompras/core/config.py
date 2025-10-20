"""Manejo centralizado de configuración para la aplicación."""
from __future__ import annotations

from configparser import ConfigParser
from pathlib import Path
from threading import RLock
from typing import Any

_CONFIG_LOCK = RLock()
_PARSER = ConfigParser()
_LOADED = False

CONFIG_PATH = (Path(__file__).resolve().parents[1] / "services" / "data" / "config.ini")
CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

_DEFAULTS = {
    "auth": {
        "correo_usuario": "",
    },
    "servicios": {
        "cadena_asunto_fija": "NOTIFICACION A PROVEEDOR:",
        "zona_horaria": "America/Guayaquil",
    },
}


def _save_locked() -> None:
    with CONFIG_PATH.open("w", encoding="utf-8") as fh:
        _PARSER.write(fh)


def _ensure_loaded() -> None:
    global _LOADED
    if _LOADED:
        return
    with _CONFIG_LOCK:
        if _LOADED:
            return
        if CONFIG_PATH.exists():
            _PARSER.read(CONFIG_PATH, encoding="utf-8")
        for section, options in _DEFAULTS.items():
            if not _PARSER.has_section(section):
                _PARSER.add_section(section)
            for key, value in options.items():
                if not _PARSER.has_option(section, key):
                    _PARSER.set(section, key, value)
        _save_locked()
        _LOADED = True


def save() -> None:
    """Persiste la configuración en disco."""
    with _CONFIG_LOCK:
        _save_locked()


def get(section: str, option: str, fallback: Any | None = None) -> Any:
    _ensure_loaded()
    if _PARSER.has_option(section, option):
        return _PARSER.get(section, option)
    return fallback


def set_value(section: str, option: str, value: Any) -> None:
    _ensure_loaded()
    with _CONFIG_LOCK:
        if not _PARSER.has_section(section):
            _PARSER.add_section(section)
        _PARSER.set(section, option, str(value))
        save()


def get_servicios_config() -> dict[str, str]:
    _ensure_loaded()
    return {key: _PARSER.get("servicios", key) for key in _DEFAULTS["servicios"]}


def get_user_email() -> str:
    return get("auth", "correo_usuario", fallback="")


def set_user_email(email: str) -> None:
    set_value("auth", "correo_usuario", email)
