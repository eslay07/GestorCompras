from __future__ import annotations

import email
import hashlib
import poplib
import re
from collections.abc import Callable, Sequence
from email.policy import default
from email.utils import getaddresses

from sqlalchemy import select

from compras_tn.application.ports import SettingsRepository
from compras_tn.domain.models import ScannedOrderMessage, SessionCredentials, utc_now
from compras_tn.infrastructure.db.database import Database
from compras_tn.infrastructure.db.models import ProcessedMessageRow
from compras_tn.infrastructure.mail import decode_header_value, message_text
from compras_tn.infrastructure.orders import extract_task_numbers

ORDER_PATTERNS = (
    re.compile(r"ORDEN\s+(?:DE\s+)?COMPRA\s*(?:DE\s+)?(?:NO\.?|N[°º]\.?|NÚMERO)?\s*[:#-]?\s*(\d{4,14})\b", re.IGNORECASE),
)
AUTHORIZED = re.compile(r"(?<!no )\bha\s+sido\s+autorizada\s+la\s+" + ORDER_PATTERNS[0].pattern, re.IGNORECASE)
PROVIDER_PATTERN = re.compile(r"PROVEEDOR\s*[:=-]?\s*(.+?)(?=\s+con\s+fecha|\n|$)", re.IGNORECASE)


class PopOrderMailScanner:
    def __init__(self, database: Database, settings: SettingsRepository):
        self.database = database
        self.settings = settings

    def validate(self, credentials: SessionCredentials) -> None:
        host = str(self.settings.get("downloads", "pop_server", "pop.telconet.ec"))
        port = int(self.settings.get("downloads", "pop_port", 995))
        connection = poplib.POP3_SSL(host, port, timeout=30)
        try:
            connection.user(credentials.email)
            connection.pass_(credentials.password)
        finally:
            try:
                connection.quit()
            except Exception:
                pass

    def scan(
        self,
        credentials: SessionCredentials,
        *,
        progress: Callable[[int, int, str], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> list[ScannedOrderMessage]:
        host = str(self.settings.get("downloads", "pop_server", "pop.telconet.ec"))
        port = int(self.settings.get("downloads", "pop_port", 995))
        extra = str(self.settings.get("downloads", "remitente_adicional", ""))
        allowed = {
            address.casefold()
            for _name, address in getaddresses(
                ["naf@telconet.ec", extra.replace(";", ",")]
            )
            if address.strip()
        }
        processed = self._processed_ids()
        connection = poplib.POP3_SSL(host, port, timeout=30)
        try:
            connection.user(credentials.email)
            connection.pass_(credentials.password)
            _response, uidl_lines, _size = connection.uidl()
            account = hashlib.sha256(f"{host.lower()}|{credentials.email.lower()}".encode()).hexdigest()[:20]
            state_key = f"scan_state::{account}"
            state = self.settings.get("downloads", state_key, None)
            if not isinstance(state, dict):
                state = {"cursor": str(self.settings.get("downloads", "last_uidl", "")), "pending": {}}
            pending = state.setdefault("pending", {})
            for uid in list(pending):
                if uid in processed:
                    pending.pop(uid)
            result = [ScannedOrderMessage.model_validate(value) for value in pending.values()]
            lines_with_uid = list(uidl_lines)  # oldest first: advance only after durable inspection
            cursor = state.get("cursor", "")
            positions = [i for i, line in enumerate(lines_with_uid)
                         if line.decode(errors="ignore").split(maxsplit=1)[-1] == cursor]
            if positions:
                lines_with_uid = lines_with_uid[positions[-1] + 1:]
            elif cursor and progress:
                progress(0, len(lines_with_uid), "El último UIDL ya no está en el servidor; recuperando el índice una vez.")
            reviewed = 0

            def checkpoint(uid: str) -> None:
                nonlocal reviewed
                reviewed += 1
                state["cursor"] = uid
                self.settings.set("downloads", state_key, state)

            total = len(lines_with_uid)
            for index, line in enumerate(lines_with_uid, start=1):
                if cancelled and cancelled():
                    break
                if progress:
                    progress(index - 1, total, f"Revisando correo nuevo {index} de {total}")
                parts = line.decode(errors="ignore").split(maxsplit=1)
                if len(parts) != 2:
                    continue
                message_number, uidl = parts
                if uidl in processed or uidl in pending:
                    checkpoint(uidl)
                    if progress and (index == total or index % 100 == 0):
                        progress(index, total, f"Revisados {index} de {total} correos")
                    continue
                try:
                    _response, lines, _size = connection.top(int(message_number), 0)
                    headers_only = True
                except (poplib.error_proto, AttributeError):
                    _response, lines, _size = connection.retr(int(message_number))
                    headers_only = False
                raw = b"\r\n".join(lines)
                message = email.message_from_bytes(raw, policy=default)
                sender = decode_header_value(message.get("From", ""))
                reply_to = decode_header_value(message.get("Reply-To", ""))
                message_addresses = {
                    address.casefold()
                    for _name, address in getaddresses([sender, reply_to])
                    if address.strip()
                }
                if allowed and not (message_addresses & allowed):
                    checkpoint(uidl)
                    continue
                subject = decode_header_value(message.get("Subject", ""))
                if headers_only:
                    _response, lines, _size = connection.retr(int(message_number))
                    message = email.message_from_bytes(b"\r\n".join(lines), policy=default)
                body = message_text(message)
                numbers = list(dict.fromkeys(AUTHORIZED.findall(body)))
                if not numbers:
                    checkpoint(uidl)
                    continue
                provider_match = PROVIDER_PATTERN.search(body)
                provider = provider_match.group(1).strip() if provider_match else ""
                task_numbers = extract_task_numbers(subject, body)
                task = task_numbers[0] if task_numbers else ""
                result.append(
                    ScannedOrderMessage(
                        external_id=uidl,
                        subject=subject,
                        sender=sender,
                        orders=[
                            {
                                "order_number": number,
                                "supplier": provider,
                                "task_number": task,
                                "task_numbers": task_numbers,
                            }
                            for number in numbers
                        ],
                    )
                )
                pending[uidl] = result[-1].model_dump(mode="json")
                checkpoint(uidl)
                if progress:
                    progress(index, total, f"Revisados {index} de {total} correos nuevos")
            if progress:
                progress(reviewed, total, f"{len(result)} correos autorizados pendientes")
            return result
        finally:
            try:
                connection.quit()
            except Exception:
                pass

    def mark_processed(self, external_ids: Sequence[str]) -> None:
        if not external_ids:
            return
        with self.database.session() as session:
            for external_id in external_ids:
                existing = session.scalar(
                    select(ProcessedMessageRow).where(
                        ProcessedMessageRow.source == "descargas_oc",
                        ProcessedMessageRow.external_id == external_id,
                    )
                )
                if existing is None:
                    session.add(
                        ProcessedMessageRow(
                            source="descargas_oc",
                            external_id=external_id,
                            raw_hash="",
                            status="processed",
                            metadata_json="{}",
                            processed_at=utc_now(),
                        )
                    )
        # Escribir el punto de control fuera de la transacción anterior evita
        # dos escritores simultáneos sobre SQLite.
        self.settings.set("downloads", "last_uidl", external_ids[0])

    def _processed_ids(self) -> set[str]:
        with self.database.session() as session:
            return set(
                session.scalars(
                    select(ProcessedMessageRow.external_id).where(
                        ProcessedMessageRow.source == "descargas_oc"
                    )
                ).all()
            )
