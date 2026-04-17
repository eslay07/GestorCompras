"""Escaneo IMAP genérico para extraer datos de correos relacionados a tareas.

Centraliza los helpers de decodificación/parseo que antes vivían en
``modules/reasignacion_gui.ServiciosReasignacion`` y los expone como
funciones independientes reutilizables por cualquier módulo (Actua. Tareas,
Servicios, etc.).
"""
from __future__ import annotations

import email
import hashlib
import html
import imaplib
import logging
import re
import unicodedata
from datetime import datetime
from email.header import decode_header, make_header
from email.message import Message
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

from gestorcompras.core.mail_parse import parse_body, parse_subject, RX_USERMAIL

logger = logging.getLogger(__name__)

IMAP_HOST = "pop.telconet.ec"
IMAP_PORT = 993
DEFAULT_TZ = ZoneInfo("America/Guayaquil")


def decode_header_value(raw: str) -> str:
    try:
        return str(make_header(decode_header(raw)))
    except Exception:
        partes: list[str] = []
        for value, encoding in decode_header(raw):
            if isinstance(value, bytes):
                codec = encoding or "utf-8"
                try:
                    partes.append(value.decode(codec, errors="ignore"))
                except Exception:
                    partes.append(value.decode("utf-8", errors="ignore"))
            else:
                partes.append(value)
        return "".join(partes)


def decode_subject(msg: Message) -> str:
    return decode_header_value(msg.get("Subject", ""))


def clean_html(text: str) -> str:
    cleaned = re.sub(r"(?is)<(script|style).*?>.*?</\\1>", " ", text)
    cleaned = re.sub(r"(?is)<br\\s*/?>", "\n", cleaned)
    cleaned = re.sub(r"(?is)</p>", "\n", cleaned)
    cleaned = re.sub(r"(?is)<[^>]+>", " ", cleaned)
    cleaned = html.unescape(cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def extract_text(msg: Message) -> str:
    partes: list[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_disposition() == "attachment":
                continue
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            charset = part.get_content_charset() or "utf-8"
            try:
                texto = payload.decode(charset, errors="ignore")
            except Exception:
                texto = payload.decode("utf-8", errors="ignore")
            if part.get_content_type() == "text/html":
                texto = clean_html(texto)
            partes.append(texto)
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            try:
                texto = payload.decode(charset, errors="ignore")
            except Exception:
                texto = payload.decode("utf-8", errors="ignore")
            if msg.get_content_type() == "text/html":
                texto = clean_html(texto)
            partes.append(texto)
    return "\n".join(filter(None, partes)).strip()


def parse_header_date(msg: Message, tz: ZoneInfo | None = None) -> datetime | None:
    tz = tz or DEFAULT_TZ
    header = msg.get("Date")
    if not header:
        return None
    try:
        dt = parsedate_to_datetime(header)
    except (TypeError, ValueError):
        return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(tz)


def normalize_for_search(value: str | None) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFD", value)
    sin_acentos = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return sin_acentos.upper()


def raw_hash(raw_bytes: bytes) -> str:
    return hashlib.sha256(raw_bytes).hexdigest()


def _extract_emails_from_header(msg: Message) -> list[str]:
    found: list[str] = []
    for hdr in ("To", "Cc"):
        val = msg.get(hdr, "")
        if val:
            decoded = decode_header_value(val)
            found.extend(RX_USERMAIL.findall(decoded))
    return list(dict.fromkeys(found))


def scan_inbox(
    email_session: Dict[str, str],
    desde: datetime,
    hasta: datetime,
    *,
    task_numbers: list[str] | None = None,
    remitente: str = "",
    asunto_contiene: str = "",
    require_user_email: bool = False,
) -> List[Dict[str, Any]]:
    """Escanea la bandeja IMAP y devuelve correos que coinciden con los filtros.

    Parameters
    ----------
    email_session : dict con ``address`` y ``password``.
    desde, hasta : rango de fechas (con tzinfo).
    task_numbers : si se proporcionan, filtra por asuntos que contengan
        alguno de estos números de tarea.
    remitente : filtro opcional por dirección del remitente.
    asunto_contiene : texto libre a buscar en el asunto.
    require_user_email : si True, descarta correos cuyo cuerpo no contenga
        la dirección del usuario logueado (comportamiento original de Servicios).
    """
    address = email_session.get("address", "")
    password = email_session.get("password", "")
    if not address or not password:
        raise ValueError("Credenciales de correo incompletas.")

    usuario = address.split("@")[0]
    tz = desde.tzinfo or DEFAULT_TZ

    task_set = set()
    if task_numbers:
        task_set = {t.strip() for t in task_numbers if t.strip()}

    remitente_busqueda = remitente.strip()
    remitente_normalizado = remitente_busqueda.lower()
    asunto_norm = normalize_for_search(asunto_contiene)

    conexion = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    try:
        conexion.login(address, password)
        conexion.select("INBOX")

        since = desde.strftime("%d-%b-%Y")
        criterios: list[str] = ["SINCE", since]
        if remitente_busqueda:
            criterios.extend(["FROM", remitente_busqueda])

        status, data = conexion.search(None, *criterios)
        if status != "OK":
            raise RuntimeError("No se pudo obtener el listado de correos")

        ids = data[0].split()
        resultados: List[Dict[str, Any]] = []

        for msg_id in reversed(ids):
            status, fetch_data = conexion.fetch(msg_id, "(RFC822)")
            if status != "OK":
                continue
            for response in fetch_data:
                if not isinstance(response, tuple):
                    continue
                raw = response[1]
                msg = email.message_from_bytes(raw)
                subject = decode_subject(msg)
                subject_normalized = normalize_for_search(subject)

                if asunto_norm and asunto_norm not in subject_normalized:
                    continue

                info_tarea = parse_subject(subject)
                task_num = info_tarea.get("task_number", "N/D")

                if task_set and task_num not in task_set:
                    continue

                from_header = decode_header_value(msg.get("From", ""))
                if remitente_normalizado and remitente_normalizado not in from_header.lower():
                    continue

                fecha = parse_header_date(msg, tz)
                if not fecha or not (desde <= fecha <= hasta):
                    continue

                cuerpo = extract_text(msg)
                parsed = parse_body(cuerpo, address)

                if require_user_email and not parsed.get("correo_usuario_encontrado"):
                    logger.debug("Correo descartado (sin email usuario): %s", msg_id)
                    continue

                mensaje_id_str = msg_id.decode() if isinstance(msg_id, bytes) else str(msg_id)
                emails_header = _extract_emails_from_header(msg)

                registro: Dict[str, Any] = {
                    "message_id": mensaje_id_str,
                    "raw_hash": raw_hash(raw),
                    "fecha": fecha,
                    "asunto": subject,
                    "from": from_header,
                    "task_number": task_num,
                    "body": cuerpo,
                    "proveedor": parsed.get("proveedor", "N/D"),
                    "mecanico": parsed.get("mecanico_nombre", "N/D"),
                    "telefono": parsed.get("mecanico_telefono", "N/D"),
                    "inf_vehiculo": parsed.get("inf_vehiculo", "N/D"),
                    "factura": parsed.get("factura", ""),
                    "oc": parsed.get("oc", ""),
                    "ingreso": parsed.get("ingreso", ""),
                    "ruc": parsed.get("ruc", ""),
                    "fecha_orden": parsed.get("fecha_orden", ""),
                    "emails": emails_header,
                }
                resultados.append(registro)
                logger.info(
                    "Correo encontrado: id=%s tarea=%s remitente=%s",
                    mensaje_id_str,
                    task_num,
                    from_header or "(sin remitente)",
                )
        return resultados
    finally:
        try:
            conexion.logout()
        except Exception:
            pass


__all__ = [
    "decode_header_value",
    "decode_subject",
    "clean_html",
    "extract_text",
    "parse_header_date",
    "normalize_for_search",
    "raw_hash",
    "scan_inbox",
]
