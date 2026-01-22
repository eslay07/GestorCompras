"""Lectura centralizada de configuración SMTP desde .env y variables de entorno."""
from __future__ import annotations

import os
from pathlib import Path

_ENV_LOADED = False


def load_env_file(path: Path | None = None) -> None:
    """Carga un archivo .env sin dependencias externas."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    if path is None:
        path = Path(__file__).resolve().parents[2] / ".env"
    if not path.exists():
        _ENV_LOADED = True
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
    _ENV_LOADED = True


def _parse_bool(value: str, default: bool) -> bool:
    if not value:
        return default
    return value.strip().lower() in {"1", "true", "yes", "si", "sí"}


def get_smtp_settings() -> tuple[str, int, bool]:
    """Retorna servidor, puerto y si debe usar STARTTLS."""
    load_env_file()
    server = os.getenv("SMTP_SERVER", "smtp.telconet.ec")
    port_raw = os.getenv("SMTP_PORT", "587")
    try:
        port = int(port_raw)
    except ValueError:
        port = 587
    starttls = _parse_bool(os.getenv("SMTP_STARTTLS", "true"), default=True)
    return server, port, starttls
