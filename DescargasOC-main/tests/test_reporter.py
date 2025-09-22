from types import SimpleNamespace

import smtplib

from descargas_oc import reporter


class DummyPOP:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.user_called: str | None = None
        self.pass_called: str | None = None
        self.quit_called = False

    def user(self, username):
        self.user_called = username

    def pass_(self, password):
        self.pass_called = password

    def quit(self):
        self.quit_called = True


def _base_cfg(**overrides):
    data = {
        "correo_reporte": "dest@example.com",
        "usuario": "popuser@telconet.ec",
        "password": "pop-pass",
        "pop_server": "pop.telconet.ec",
        "pop_port": 995,
        "smtp_usuario": "smtpuser@example.com",
        "smtp_password": "smtp-pass",
        "smtp_server": "smtp.telconet.ec",
        "smtp_port": 587,
        "smtp_ssl_port": 465,
        "smtp_plain_port": 25,
        "carpeta_analizar": None,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_enviar_reporte_prefers_custom_smtp_credentials(monkeypatch):
    pop_instance = DummyPOP("pop.telconet.ec", 995)
    pop_calls: list[tuple[str, int]] = []

    def fake_pop(host, port):
        pop_calls.append((host, port))
        return pop_instance

    monkeypatch.setattr(reporter.poplib, "POP3_SSL", fake_pop)

    init_calls: list[tuple[str, int]] = []
    login_calls: list[tuple[str, str]] = []
    sent_messages = []

    class DummySMTP:
        def __init__(self, host, port):
            init_calls.append((host, port))

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

        def ehlo(self):
            return None

        def starttls(self):
            return None

        def login(self, username, password):
            login_calls.append((username, password))
            if (username, password) != ("smtpuser@example.com", "smtp-pass"):
                raise smtplib.SMTPAuthenticationError(535, b"bad credentials")

        def send_message(self, message):
            sent_messages.append(message)

    monkeypatch.setattr(reporter.smtplib, "SMTP", DummySMTP)
    monkeypatch.setattr(
        reporter.smtplib,
        "SMTP_SSL",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("SSL fallback not expected")),
    )

    cfg = _base_cfg()

    assert reporter.enviar_reporte(["123"], [], [{"numero": "123"}], cfg)
    assert init_calls == [("smtp.telconet.ec", 587)]
    assert login_calls == [("smtpuser@example.com", "smtp-pass")]
    assert pop_calls == [("pop.telconet.ec", 995)]
    assert pop_instance.user_called == "popuser@telconet.ec"
    assert pop_instance.pass_called == "pop-pass"
    assert pop_instance.quit_called is True
    assert len(sent_messages) == 1


def test_enviar_reporte_retries_with_additional_usernames(monkeypatch):
    pop_instance = DummyPOP("pop.telconet.ec", 995)
    pop_calls: list[tuple[str, int]] = []

    def fake_pop(host, port):
        pop_calls.append((host, port))
        return pop_instance

    monkeypatch.setattr(reporter.poplib, "POP3_SSL", fake_pop)

    init_calls: list[tuple[str, int]] = []
    login_attempts: list[str] = []
    sent_messages = []

    class SequenceSMTP:
        def __init__(self, host, port):
            init_calls.append((host, port))

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

        def ehlo(self):
            return None

        def starttls(self):
            return None

        def login(self, username, password):
            login_attempts.append(username)
            if username != "second@domain.test":
                raise smtplib.SMTPAuthenticationError(535, b"bad")

        def send_message(self, message):
            sent_messages.append(message)

    monkeypatch.setattr(reporter.smtplib, "SMTP", SequenceSMTP)
    monkeypatch.setattr(
        reporter.smtplib,
        "SMTP_SSL",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("SSL fallback not expected")),
    )

    cfg = _base_cfg(smtp_usuario="first", usuario="second@domain.test")

    assert reporter.enviar_reporte(["123"], [], [{"numero": "123"}], cfg)
    assert pop_calls == [("pop.telconet.ec", 995)]
    assert init_calls == [("smtp.telconet.ec", 587), ("smtp.telconet.ec", 587)]
    assert login_attempts == ["first", "second@domain.test"]
    assert len(sent_messages) == 1


def test_enviar_reporte_abastecimiento_incluye_categoria(monkeypatch):
    pop_instance = DummyPOP("pop.telconet.ec", 995)

    def fake_pop(host, port):
        assert (host, port) == ("pop.telconet.ec", 995)
        return pop_instance

    monkeypatch.setattr(reporter.poplib, "POP3_SSL", fake_pop)

    init_calls: list[tuple[str, int]] = []
    login_calls: list[tuple[str, str]] = []
    sent_messages = []

    class DummySMTP:
        def __init__(self, host, port):
            init_calls.append((host, port))

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

        def ehlo(self):
            return None

        def starttls(self):
            return None

        def login(self, username, password):
            login_calls.append((username, password))

        def send_message(self, message):
            sent_messages.append(message)

    monkeypatch.setattr(reporter.smtplib, "SMTP", DummySMTP)
    monkeypatch.setattr(
        reporter.smtplib,
        "SMTP_SSL",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("SSL fallback no esperado")),
    )

    cfg = _base_cfg()
    ordenes = [
        {"numero": "456", "proveedor": "Proveedor Uno", "categoria": "abastecimiento"}
    ]

    resultado = reporter.enviar_reporte(["456"], [], ordenes, cfg, categoria="abastecimiento")

    assert resultado is True
    assert init_calls == [("smtp.telconet.ec", 587)]
    assert login_calls == [("smtpuser@example.com", "smtp-pass")]
    assert pop_instance.quit_called is True
    assert len(sent_messages) == 1

    mensaje = sent_messages[0]
    cuerpo_texto = mensaje.get_body(preferencelist=("plain",)).get_content()
    cuerpo_html = mensaje.get_body(preferencelist=("html",)).get_content()

    assert "Categoría: abastecimiento" in cuerpo_texto
    assert "Categoría" in cuerpo_texto
    assert "Proveedor Uno" in cuerpo_texto
    assert "abastecimiento" in cuerpo_texto

    assert "Categoría" in cuerpo_html
    assert "Proveedor Uno" in cuerpo_html
    assert "abastecimiento" in cuerpo_html
