from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

_SENSITIVE_PARTS = {
    "api_key",
    "auth_token",
    "contrasena",
    "contraseña",
    "password",
    "passwd",
    "refresh_token",
    "secret",
    "smtp_password",
    "token",
    "ticket",
    "cookie",
    "cookies",
}
_LABELED_SECRET = re.compile(
    r"(?i)(\b(?:api[_ -]?key|auth[_ -]?token|contrase(?:n|ñ)a|password|passwd|"
    r"refresh[_ -]?token|secret|smtp[_ -]?password|token|ticket|cookies?)\b\s*[=:]\s*)"
    r"(?:\"[^\"]*\"|'[^']*'|[^\s,;&]+)"
)
_URL_PASSWORD = re.compile(r"(?i)(://[^\s/:@]+:)[^\s/@]+(@)")


def is_sensitive_key(key: object) -> bool:
    normalized = re.sub(r"[^a-z0-9áéíóúüñ]+", "_", str(key).casefold()).strip("_")
    if normalized in _SENSITIVE_PARTS:
        return True
    components = set(normalized.split("_"))
    return bool(components & {"password", "passwd", "secret", "token", "contraseña", "contrasena"})


def sanitize_text(value: object, secrets: Sequence[str] = ()) -> str:
    text = str(value or "")
    for secret in sorted({item for item in secrets if item}, key=len, reverse=True):
        text = text.replace(secret, "***")
    text = _LABELED_SECRET.sub(r"\1***", text)
    return _URL_PASSWORD.sub(r"\1***\2", text)


def sanitize_data(value: Any, secrets: Sequence[str] = ()) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): "***" if is_sensitive_key(key) else sanitize_data(item, secrets)
            for key, item in value.items()
        }
    if isinstance(value, tuple):
        return tuple(sanitize_data(item, secrets) for item in value)
    if isinstance(value, list):
        return [sanitize_data(item, secrets) for item in value]
    if isinstance(value, set):
        return [sanitize_data(item, secrets) for item in sorted(value, key=str)]
    if isinstance(value, str):
        return sanitize_text(value, secrets)
    return value
