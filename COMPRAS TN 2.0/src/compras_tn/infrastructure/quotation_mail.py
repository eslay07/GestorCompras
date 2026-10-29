"""Read-only IMAP search adapter for quotation scanning."""
from __future__ import annotations

import imaplib
from datetime import timedelta


def quoted(value):
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"') + '"'


def either(expressions):
    result = expressions[-1]
    for expression in reversed(expressions[:-1]):
        result = f"OR {expression} ({result})"
    return result


class QuotationIMAP:
    def __init__(self, host, port, addresses, start, end, tasks, factory=None):
        self.connection = (factory or imaplib.IMAP4_SSL)(host, port, timeout=30)
        self.addresses, self.start, self.end, self.tasks = addresses, start, end, tasks
        self.email = ""
        self.headers = {}
        self.uids = []

    def user(self, email):
        self.email = email

    def pass_(self, password):
        self.connection.login(self.email, password)
        status, _ = self.connection.select("INBOX", readonly=True)
        if status != "OK":
            raise OSError("No se pudo abrir INBOX en modo lectura.")
        _, validity = self.connection.response("UIDVALIDITY")
        self.validity = (validity[0].decode() if validity and validity[0] else "0")

    def uidl(self):
        matches = set()
        if not self.addresses:
            return b"OK", [], 0
        for index in range(0, len(self.addresses), 40):
            senders = either(["FROM " + quoted(address) for address in self.addresses[index:index + 40]])
            if self.tasks:
                extra = "(" + either(["SUBJECT " + quoted(task) for task in self.tasks]) + ")"
            else:
                # English month abbreviations are required by IMAP regardless of OS locale.
                def date(value):
                    months = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
                    return f"{value.day:02d}-{months[value.month - 1]}-{value.year}"
                extra = "SINCE " + date(self.start) + " BEFORE " + date(self.end + timedelta(days=1))
            status, data = self.connection.uid("SEARCH", None, f"({senders}) {extra}")
            if status != "OK":
                raise OSError("El servidor no pudo buscar solicitudes de proveedores.")
            matches.update((data[0] or b"").split())
        self.uids = sorted(matches, key=int)
        return b"OK", [f"{i} imap-{self.validity}-{uid.decode()}".encode() for i, uid in enumerate(self.uids, 1)], 0

    def fetch(self, uid, section):
        status, data = self.connection.uid("FETCH", uid, section)
        if status != "OK":
            raise OSError("No se pudo leer el correo seleccionado.")
        return [item[1] for item in data if isinstance(item, tuple)]

    def top(self, index, _lines):
        content = b"\r\n".join(self.fetch(self.uids[index - 1], "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE)])"))
        return b"OK", content.split(b"\r\n"), len(content)

    def retr(self, index):
        content = b"\r\n".join(self.fetch(self.uids[index - 1], "(BODY.PEEK[])"))
        return b"OK", content.split(b"\r\n"), len(content)

    def quit(self):
        self.connection.logout()
