from __future__ import annotations

from pathlib import Path
from typing import Any

from compras_tn.domain.models import SessionCredentials
from compras_tn.infrastructure.mail import CorporateMailGateway
from compras_tn.infrastructure.seafile import SeafileHttpGateway


class Settings:
    def __init__(self, values: dict[tuple[str, str], object]):
        self.values = values

    def get(self, namespace: str, key: str, default: object = None) -> object:
        return self.values.get((namespace, key), default)


class SmtpConnection:
    instances: list[SmtpConnection] = []

    def __init__(self, host: str, port: int, timeout: int):
        self.host, self.port, self.timeout = host, port, timeout
        self.started_tls = False
        self.logged_in = False
        self.__class__.instances.append(self)

    def __enter__(self) -> SmtpConnection:
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def ehlo(self) -> None:
        return None

    def starttls(self) -> None:
        self.started_tls = True

    def login(self, username: str, password: str) -> None:
        self.logged_in = bool(username and password)


def test_smtp_contract_uses_ssl_for_port_465(monkeypatch: Any) -> None:
    SmtpConnection.instances.clear()
    monkeypatch.setattr("smtplib.SMTP_SSL", SmtpConnection)
    gateway = CorporateMailGateway(Settings({("email", "smtp_server"): "smtp.test", ("email", "smtp_port"): 465}))
    gateway.validate(SessionCredentials(username="ANA", email="ana@example.com", password="secret"))
    assert SmtpConnection.instances[-1].logged_in
    assert not SmtpConnection.instances[-1].started_tls


class Response:
    def __init__(self, text: str = "", payload: dict[str, str] | None = None):
        self.text = text
        self.status_code = 200
        self.payload = payload or {}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, str]:
        return self.payload


class HttpSession:
    def __init__(self) -> None:
        self.posts: list[tuple[str, dict[str, Any]]] = []

    def post(self, url: str, **kwargs: Any) -> Response:
        self.posts.append((url, kwargs))
        if url.endswith("auth-token/"):
            return Response(payload={"token": "memory-token"})
        return Response("uploaded")

    def get(self, url: str, **kwargs: Any) -> Response:
        return Response("https://upload.example")


def test_seafile_contract_keeps_token_in_memory(monkeypatch: Any, tmp_path: Path) -> None:
    session = HttpSession()
    monkeypatch.setattr(SeafileHttpGateway, "_session", staticmethod(lambda: session))
    gateway = SeafileHttpGateway(Settings({("downloads", "seafile_url"): "https://sea.example"}))
    source = tmp_path / "oc.pdf"
    source.write_bytes(b"pdf")
    result = gateway.upload(
        SessionCredentials(username="ANA", email="ana@example.com", password="secret"),
        source,
        "12345678-1234-1234-1234-123456789abc",
    )
    assert result == "uploaded"
    assert not hasattr(gateway, "token")
