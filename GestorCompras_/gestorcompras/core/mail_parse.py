"""Utilidades para normalizar y extraer datos de los correos de Servicios."""
from __future__ import annotations

import re
import unicodedata

RX_TAREA_SUBJECT = re.compile(r'TAREA:\s*["“”]?(\d{6,11})["“”]?', re.I)
RX_PROVEEDOR = re.compile(r'Estimados\s+"([^"]+)"', re.I)
RX_MECANICO = re.compile(r'coordinando el mantenimiento con\s+"([^"(]+?)\s*\(([^)]+)\)\.?', re.I)
RX_OT_LINE = re.compile(r'"\s*([^"\n]*OT[^"\n]+)\s*"', re.I)
RX_USERMAIL = re.compile(r'[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}', re.I)

_MOJI = {
    "Ã¡": "á",
    "Ã©": "é",
    "Ã­": "í",
    "Ã³": "ó",
    "Ãº": "ú",
    "Ã±": "ñ",
    "Ã‘": "Ñ",
}


def _norm_quotes(s: str) -> str:
    return s.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")


def _fix_mojibake(s: str) -> str:
    for bad, good in _MOJI.items():
        s = s.replace(bad, good)
    return s


def _norm(s: str | None) -> str:
    if not s:
        return ""
    return unicodedata.normalize("NFC", _fix_mojibake(_norm_quotes(s)))


def _digits_only(s: str) -> str:
    return "".join(ch for ch in s if ch.isdigit())


def parse_subject(subject: str | None) -> dict[str, str]:
    s = _norm(subject)
    match = RX_TAREA_SUBJECT.search(s)
    task = match.group(1) if match else "N/D"
    return {"task_number": task}


def parse_body(body_text: str | None, correo_usuario: str) -> dict[str, object]:
    body = _norm(body_text)
    proveedor = "N/D"
    proveedor_match = RX_PROVEEDOR.search(body)
    if proveedor_match:
        proveedor = proveedor_match.group(1).strip()

    mecanico_nombre = "N/D"
    mecanico_telefono = "N/D"
    mecanico_match = RX_MECANICO.search(body)
    if mecanico_match:
        mecanico_nombre = mecanico_match.group(1).strip()
        mecanico_telefono = _digits_only(mecanico_match.group(2)) or "N/D"

    inf_vehiculo = "N/D"
    ot_match = RX_OT_LINE.search(body)
    if ot_match:
        inf_vehiculo = ot_match.group(1).strip()

    correo_usuario_encontrado = False
    if correo_usuario:
        correo_usuario_encontrado = correo_usuario.lower() in body.lower()
    else:
        correo_usuario_encontrado = bool(RX_USERMAIL.search(body))

    return {
        "proveedor": proveedor or "N/D",
        "mecanico_nombre": mecanico_nombre or "N/D",
        "mecanico_telefono": mecanico_telefono or "N/D",
        "inf_vehiculo": inf_vehiculo or "N/D",
        "correo_usuario_encontrado": correo_usuario_encontrado,
    }


__all__ = [
    "parse_subject",
    "parse_body",
    "RX_TAREA_SUBJECT",
    "RX_PROVEEDOR",
    "RX_MECANICO",
    "RX_OT_LINE",
    "RX_USERMAIL",
]
