from __future__ import annotations

import base64
import email
import html
import imaplib
import re
import smtplib
import socket
import ssl
import threading
import unicodedata
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.policy import default
from email.utils import getaddresses, make_msgid, parsedate_to_datetime
from pathlib import Path
from typing import Any

from compras_tn.application.ports import SettingsRepository
from compras_tn.domain.models import SessionCredentials
from compras_tn.infrastructure.mail_parse import parse_body, parse_goods_body, parse_subject
from compras_tn.infrastructure.orders import extract_task_numbers

TAG_PATTERN = re.compile(r"<[^>]+>")
SMTP_LIMIT = threading.BoundedSemaphore(4)


def decode_header_value(value: str) -> str:
    try:
        return str(make_header(decode_header(value or "")))
    except Exception:
        return value or ""


def message_text(message: email.message.Message, *, preserve_lines: bool = False) -> str:
    parts: list[str] = []
    iterable = message.walk() if message.is_multipart() else [message]
    for part in iterable:
        if part.get_content_disposition() == "attachment":
            continue
        content_type = part.get_content_type()
        if content_type not in {"text/plain", "text/html"}:
            continue
        try:
            value = part.get_content()
        except Exception:
            payload = part.get_payload(decode=True) or b""
            value = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        text = str(value)
        if content_type == "text/html":
            if preserve_lines:
                text = re.sub(r"(?i)<br\s*/?>|</(?:p|div|tr)\s*>", "\n", text)
            text = html.unescape(TAG_PATTERN.sub(" ", text))
        parts.append("\n".join(" ".join(line.split()) for line in text.splitlines())
                     if preserve_lines else " ".join(text.split()))
    return "\n".join(parts)


class CorporateMailGateway:
    def __init__(self, settings: SettingsRepository):
        self.settings = settings

    def _imap_host(self) -> str:
        host = str(self.settings.get("email", "imap_server", "pop.telconet.ec")).strip()
        # Correct the obsolete default shipped in 2.0; preserve custom servers.
        return "pop.telconet.ec" if host.lower() == "imap.telconet.ec" else host

    @staticmethod
    def _connect_imap(host: str, port: int):
        try:
            return imaplib.IMAP4_SSL(host, port, timeout=30)
        except socket.gaierror as exc:
            raise ConnectionError(
                f"No se pudo resolver el servidor IMAP {host}:{port}. "
                "Revise Servidor IMAP en Configuración y la conexión/DNS de la red corporativa."
            ) from exc

    def validate(self, credentials: SessionCredentials) -> None:
        host = str(self.settings.get("email", "smtp_server", "smtp.telconet.ec"))
        port = int(self.settings.get("email", "smtp_port", 587))
        client = smtplib.SMTP_SSL if port == 465 else smtplib.SMTP
        with SMTP_LIMIT:
            with client(host, port, timeout=20) as server:
                if port != 465:
                    server.ehlo()
                    server.starttls(context=ssl.create_default_context())
                    server.ehlo()
                server.login(credentials.email, credentials.password)

    def validate_inbox(self, credentials: SessionCredentials) -> None:
        host = self._imap_host()
        port = int(self.settings.get("email", "imap_port", 993))
        connection = self._connect_imap(host, port)
        try:
            connection.login(credentials.email, credentials.password)
            status, _data = connection.select("INBOX", readonly=True)
            if status != "OK":
                raise RuntimeError("No se pudo abrir la bandeja de entrada.")
        finally:
            try:
                connection.logout()
            except Exception:
                pass

    def scan_reassignment_tasks(self, *args, **kwargs):
        return self.scan_tasks(*args, **kwargs, legacy_reassignment=True)

    def scan_goods_reassignment_tasks(self, *args, **kwargs):
        return self.scan_tasks(*args, **kwargs, goods_reassignment=True)

    def scan_tasks(
        self,
        credentials: SessionCredentials,
        start: datetime,
        end: datetime,
        subject_contains: str,
        sender: str = "",
        progress: Callable[[int, int, str], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
        legacy_reassignment: bool = False,
        goods_reassignment: bool = False,
    ) -> list[dict[str, Any]]:
        host = self._imap_host()
        port = int(self.settings.get("email", "imap_port", 993))
        start, end = self._aware_range(start, end)
        connection = self._connect_imap(host, port)
        try:
            connection.login(credentials.email, credentials.password)
            status, _data = connection.select("INBOX", readonly=True)
            if status != "OK":
                raise RuntimeError("No se pudo abrir la bandeja de entrada.")
            criteria: list[str] = ["SINCE", start.strftime("%d-%b-%Y")]
            if sender.strip():
                criteria.extend(["FROM", sender.strip()])
            status, data = connection.search(None, *criteria)
            if status != "OK":
                raise RuntimeError("El servidor no devolvió el listado de correos.")
            def normalize_subject(value):
                return " ".join("".join(c for c in unicodedata.normalize("NFKD", value)
                                        if not unicodedata.combining(c)).casefold().split())
            normalized_subject = normalize_subject(subject_contains)
            results: list[dict[str, Any]] = []
            message_ids = list(reversed(data[0].split()))
            total = len(message_ids)
            for index, message_id in enumerate(message_ids, start=1):
                if cancelled and cancelled():
                    break
                if progress:
                    progress(index, total, f"Revisando correo {index} de {total}; {len(results)} encontrados")
                status, content = connection.fetch(message_id, "(BODY.PEEK[])")
                if status != "OK":
                    continue
                raw = next((item[1] for item in content if isinstance(item, tuple)), None)
                if not raw:
                    continue
                message = email.message_from_bytes(raw, policy=default)
                subject = decode_header_value(message.get("Subject", ""))
                if normalized_subject and normalized_subject not in normalize_subject(subject):
                    continue
                try:
                    received = (
                        parsedate_to_datetime(message.get("Date"))
                        if message.get("Date")
                        else None
                    )
                except (TypeError, ValueError, OverflowError):
                    received = None
                if received is None:
                    continue
                if received:
                    if received.tzinfo is None:
                        received = received.replace(tzinfo=start.tzinfo)
                    if not start.astimezone(UTC) <= received.astimezone(UTC) <= end.astimezone(UTC):
                        continue
                body = message_text(message, preserve_lines=legacy_reassignment or goods_reassignment)
                if goods_reassignment:
                    from_value = decode_header_value(message.get("From", ""))
                    if sender.strip() and sender.strip().casefold() not in from_value.casefold():
                        continue
                    seen_tasks: set[tuple[str, str]] = set()
                    for task in parse_goods_body(body):
                        identity = (task["task_number"], task["reasignacion"])
                        if identity in seen_tasks:
                            continue  # multipart/alternative includes the same task twice.
                        seen_tasks.add(identity)
                        results.append({**task, "date": received, "subject": subject,
                                        "sender": from_value, "body": body,
                                        "supplier": ", ".join(dict.fromkeys(d["Proveedor"] for d in task["details"]))})
                    continue
                legacy = parse_body(body, credentials.email) if legacy_reassignment else {}
                if legacy_reassignment and not legacy.get("correo_usuario_encontrado"):
                    continue
                task_numbers = extract_task_numbers(subject, body)
                if legacy_reassignment and not task_numbers:
                    parsed_task = parse_subject(subject)["task_number"]
                    task_numbers = [] if parsed_task == "N/D" else [parsed_task]
                from_value = decode_header_value(message.get("From", ""))
                if sender.strip() and sender.strip().casefold() not in from_value.casefold():
                    continue
                base = {
                        "message_id": decode_header_value(message.get("Message-ID", ""))
                        or message_id.decode(errors="ignore"),
                        "date": received,
                        "subject": subject,
                        "sender": from_value,
                        "task_numbers": task_numbers,
                        "body": body,
                        "supplier": self._extract(body, ("PROVEEDOR", "TALLER")),
                        "mechanic": self._extract(body, ("MECANICO", "MECÁNICO")),
                        "phone": self._extract(body, ("TELEFONO", "TELÉFONO")),
                        **({"supplier": legacy["proveedor"], "mecanico": legacy["mecanico_nombre"],
                            "telefono": legacy["mecanico_telefono"], "inf_vehiculo": legacy["inf_vehiculo"]}
                           if legacy_reassignment else {}),
                    }
                for task_number in task_numbers or [""]:
                    results.append({**base, "task_number": task_number})
                if progress:
                    progress(index, total, f"Revisado correo {index} de {total}")
            return results
        finally:
            try:
                connection.logout()
            except Exception:
                pass

    def send_html(
        self,
        credentials: SessionCredentials,
        to: Sequence[str],
        subject: str,
        html: str,
        attachments: Sequence[Path] = (),
        cc: Sequence[str] = (),
    ) -> None:
        self.send_html_with_text(
            credentials, to, subject, html, "Este mensaje contiene una versión HTML.", attachments, cc
        )

    def send_html_with_text(
        self,
        credentials: SessionCredentials,
        to: Sequence[str],
        subject: str,
        html: str,
        plain_text: str,
        attachments: Sequence[Path] = (),
        cc: Sequence[str] = (),
    ) -> None:
        recipients = self._addresses(to)
        copies = [
            address
            for address in self._addresses(cc)
            if address.casefold() not in {item.casefold() for item in recipients}
        ]
        if not recipients:
            raise ValueError("El correo no tiene destinatarios.")
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = credentials.email
        message["To"] = ", ".join(recipients)
        if copies:
            message["Cc"] = ", ".join(copies)
        message.set_content(plain_text or "Este mensaje contiene una versión HTML.")
        images = []

        def inline_image(match):
            subtype, encoded = match.groups()
            content = base64.b64decode(encoded, validate=True)
            cid = make_msgid()
            images.append((content, subtype.lower(), cid))
            return f'src="cid:{cid[1:-1]}"'

        html = re.sub(
            r'''src=["']data:image/(png|jpeg|gif);base64,([A-Za-z0-9+/=]+)["']''',
            inline_image, html, flags=re.IGNORECASE,
        )
        message.add_alternative(html, subtype="html")
        html_part = message.get_payload()[-1]
        for content, subtype, cid in images:
            html_part.add_related(content, maintype="image", subtype=subtype, cid=cid,
                                  disposition="inline")
        for path in attachments:
            path = Path(path)
            if not path.is_file():
                raise FileNotFoundError(f"No se encontró el adjunto: {path}")
            message.add_attachment(
                path.read_bytes(),
                maintype="application",
                subtype="pdf" if path.suffix.lower() == ".pdf" else "octet-stream",
                filename=path.name,
            )
        host = str(self.settings.get("email", "smtp_server", "smtp.telconet.ec"))
        port = int(self.settings.get("email", "smtp_port", 587))
        client = smtplib.SMTP_SSL if port == 465 else smtplib.SMTP
        with SMTP_LIMIT:
            with client(host, port, timeout=30) as server:
                if port != 465:
                    server.ehlo()
                    server.starttls(context=ssl.create_default_context())
                    server.ehlo()
                server.login(credentials.email, credentials.password)
                server.send_message(message, to_addrs=recipients + copies)

    @staticmethod
    def _extract(body: str, labels: Sequence[str]) -> str:
        choices = "|".join(re.escape(label) for label in labels)
        match = re.search(rf"(?:{choices})\s*[:=-]\s*([^\n|;/]+)", body, re.IGNORECASE)
        return match.group(1).strip() if match else ""

    @staticmethod
    def _addresses(values: Sequence[str]) -> list[str]:
        result: list[str] = []
        for _name, address in getaddresses([str(value) for value in values]):
            normalized = address.strip()
            if "@" not in normalized or any(character.isspace() for character in normalized):
                continue
            if normalized.casefold() not in {item.casefold() for item in result}:
                result.append(normalized)
        return result

    @staticmethod
    def _aware_range(start: datetime, end: datetime) -> tuple[datetime, datetime]:
        local_tz = datetime.now().astimezone().tzinfo
        if start.tzinfo is None:
            start = start.replace(tzinfo=local_tz)
        if end.tzinfo is None:
            end = end.replace(tzinfo=local_tz)
        return start, end
