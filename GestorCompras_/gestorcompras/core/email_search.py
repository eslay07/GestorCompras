"""Búsqueda y extracción de correos para el flujo de Servicios."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email import message_from_bytes
from email.message import Message
from email.utils import parsedate_to_datetime
from typing import Dict, Iterable

try:  # pragma: no cover - dependencia opcional
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover
    BeautifulSoup = None  # type: ignore

try:  # pragma: no cover
    from imapclient import IMAPClient
except ImportError:  # pragma: no cover
    class IMAPClient:  # type: ignore
        def __init__(self, *_args, **_kwargs):
            raise RuntimeError("imapclient no está instalado")

from gestorcompras.core.mail_parse import parse_body, parse_subject


def _extract_text(msg: Message) -> str:
    if msg.is_multipart():
        parts: list[str] = []
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain":
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                parts.append(payload.decode(part.get_content_charset() or "utf-8", "ignore"))
            elif ctype == "text/html":
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                html = payload.decode(part.get_content_charset() or "utf-8", "ignore")
                if BeautifulSoup is not None:
                    parts.append(BeautifulSoup(html, "html.parser").get_text("\n"))
                else:  # pragma: no cover - degradación cuando bs4 no está disponible
                    parts.append(html)
        return "\n".join(parts).strip()
    body = msg.get_payload(decode=True)
    if body:
        return body.decode(msg.get_content_charset() or "utf-8", "ignore").strip()
    return ""


def _normalize_window(dt_from: datetime, dt_to: datetime) -> tuple[datetime, datetime]:
    if dt_from.tzinfo is None or dt_to.tzinfo is None:
        raise ValueError("Las fechas deben incluir información de zona horaria")
    if dt_from > dt_to:
        raise ValueError("La fecha inicial no puede ser mayor que la final")
    return dt_from, dt_to


def search_messages_imap(
    host: str,
    user: str,
    password: str,
    folder: str,
    dt_from: datetime,
    dt_to: datetime,
    subject_contains: str,
    correo_usuario: str,
) -> Iterable[Dict[str, object]]:
    dt_from, dt_to = _normalize_window(dt_from, dt_to)
    subject_token = subject_contains.lower()
    # IMAP BEFORE usa la fecha límite excluyente
    date_limit = (dt_to + timedelta(days=1)).date()

    with IMAPClient(host) as srv:
        srv.login(user, password)
        srv.select_folder(folder)
        ids = srv.search([u"SINCE", dt_from.date(), u"BEFORE", date_limit])
        if not ids:
            return
        fetched = srv.fetch(ids, ["ENVELOPE", "RFC822"])
        for msgid, data in fetched.items():
            msg = message_from_bytes(data[b"RFC822"])
            subject = str(msg.get("Subject", ""))
            if subject_token not in subject.lower():
                continue
            raw_date = msg.get("Date")
            if not raw_date:
                continue
            parsed_date = parsedate_to_datetime(raw_date)
            if parsed_date.tzinfo is None:
                parsed_date = parsed_date.replace(tzinfo=timezone.utc)
            parsed_date = parsed_date.astimezone(dt_from.tzinfo)
            if not (dt_from <= parsed_date <= dt_to):
                continue
            body = _extract_text(msg)
            parsed_body = parse_body(body, correo_usuario)
            if not parsed_body["correo_usuario_encontrado"]:
                continue
            task_data = parse_subject(subject)
            yield {
                "message_id": str(msgid),
                "date": parsed_date,
                "subject": subject,
                "task_number": task_data.get("task_number", "N/D"),
                "body": body,
                **parsed_body,
            }


def search_messages_owa(*args, **kwargs):  # pragma: no cover - pendiente
    raise NotImplementedError("Pendiente implementar la integración con OWA")


__all__ = [
    "search_messages_imap",
    "search_messages_owa",
]
