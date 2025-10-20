from datetime import datetime, timedelta
from email.message import EmailMessage
from zoneinfo import ZoneInfo

import pytest

from gestorcompras.core import email_search


class FakeIMAPClient:
    def __init__(self, host):
        self.host = host
        self._messages = {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def login(self, user, password):
        assert user == "user"
        assert password == "pass"

    def select_folder(self, folder):
        assert folder == "INBOX"

    def search(self, criteria):
        return list(self._messages)

    def fetch(self, ids, _):
        return {i: {b"RFC822": self._messages[i]} for i in ids}


@pytest.fixture(autouse=True)
def patch_imap(monkeypatch):
    fake = FakeIMAPClient("host")
    tz = ZoneInfo("America/Guayaquil")
    base = datetime(2024, 4, 1, 10, 0, tzinfo=tz)

    def make_msg(idx, dt, body):
        msg = EmailMessage()
        msg["Subject"] = f"NOTIFICACION A PROVEEDOR: TAREA: \"14295968{idx}\""
        msg["Date"] = dt.strftime("%a, %d %b %Y %H:%M:%S %z")
        msg.set_content(body)
        return msg.as_bytes()

    fake._messages = {
        1: make_msg(1, base, "Estimados \"Proveedor\" user@telconet.ec\ncoordinando el mantenimiento con \"Nombre (0999999999)\"\n\"OT 1\""),
        2: make_msg(2, base - timedelta(hours=5), "Sin coincidencias"),
    }

    monkeypatch.setattr(email_search, "IMAPClient", lambda host: fake)
    return fake


def test_filtra_por_ventana_horaria(patch_imap):
    tz = ZoneInfo("America/Guayaquil")
    dt_from = datetime(2024, 4, 1, 9, 0, tzinfo=tz)
    dt_to = datetime(2024, 4, 1, 11, 0, tzinfo=tz)

    results = list(
        email_search.search_messages_imap(
            "host",
            "user",
            "pass",
            "INBOX",
            dt_from,
            dt_to,
            "NOTIFICACION A PROVEEDOR:",
            "user@telconet.ec",
        )
    )
    assert len(results) == 1
    assert results[0]["task_number"].startswith("14295968")


def test_excluye_sin_correo_usuario(patch_imap):
    tz = ZoneInfo("America/Guayaquil")
    dt_from = datetime(2024, 4, 1, 0, 0, tzinfo=tz)
    dt_to = datetime(2024, 4, 1, 12, 0, tzinfo=tz)

    results = list(
        email_search.search_messages_imap(
            "host",
            "user",
            "pass",
            "INBOX",
            dt_from,
            dt_to,
            "NOTIFICACION A PROVEEDOR:",
            "otro@telconet.ec",
        )
    )
    assert results == []
