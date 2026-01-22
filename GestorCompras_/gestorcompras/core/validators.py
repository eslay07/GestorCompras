"""Validaciones y normalización de datos de entrada."""
from __future__ import annotations

import re

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_email(value: str) -> bool:
    """Retorna True si el correo cumple un formato básico válido."""
    return bool(EMAIL_RE.match(value or ""))


def normalize_emails(raw: str) -> tuple[list[str], list[str]]:
    """Normaliza correos separados por ';' o ',' y retorna válidos e inválidos."""
    if not raw:
        return [], []
    parts = re.split(r"[;,]+", raw)
    valid: list[str] = []
    invalid: list[str] = []
    seen: set[str] = set()
    for part in parts:
        email = part.strip()
        if not email:
            continue
        if email.lower() in seen:
            continue
        seen.add(email.lower())
        if validate_email(email):
            valid.append(email)
        else:
            invalid.append(email)
    return valid, invalid
