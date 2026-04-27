"""Utilidades centralizadas para resolver credenciales de Telcos."""
from __future__ import annotations

from typing import Mapping


def resolve_telcos_credentials(email_session: Mapping[str, str] | None) -> tuple[str, str]:
    """Devuelve ``(username_normalizado, password)`` a partir de ``email_session``.

    - Acepta alias de usuario: ``username``, ``user``, ``address`` y ``email``
      (además de ``usuario``/``correo`` por compatibilidad).
    - El usuario se normaliza sin dominio y en mayúsculas.
    - Lanza ``ValueError`` con mensajes uniformes cuando faltan datos.
    """

    if not email_session:
        raise ValueError("Credenciales de Telcos incompletas: no existe sesión activa.")

    username_raw = (
        email_session.get("username")
        or email_session.get("user")
        or email_session.get("address")
        or email_session.get("email")
        or email_session.get("usuario")
        or email_session.get("correo")
        or ""
    ).strip()

    username = username_raw.split("@")[0].strip().upper()
    if not username:
        raise ValueError("Credenciales de Telcos incompletas: falta el usuario.")

    password = (
        email_session.get("password")
        or email_session.get("pass")
        or email_session.get("contrasena")
        or ""
    ).strip()
    if not password:
        raise ValueError("Credenciales de Telcos incompletas: falta la contraseña.")

    return username, password
