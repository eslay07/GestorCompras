import base64
from types import SimpleNamespace

from gestorcompras.services import email_sender


def test_render_email_string_renders_template():
    template = "Hola {{ name }}"
    result = email_sender.render_email_string(template, {"name": "Mundo"})
    assert "Hola Mundo" == result


def test_send_email_custom_embeds_signature(tmp_path, monkeypatch):
    img = tmp_path / "sig.png"
    img.write_bytes(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/6XK7L8AAAAASUVORK5CYII="))

    sent = {}

    class DummySMTP:
        def __init__(self, *args, **kwargs):
            pass

        def starttls(self):
            pass

        def login(self, *args, **kwargs):
            pass

        def send_message(self, msg):
            sent["msg"] = msg

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            pass

    monkeypatch.setattr(email_sender, "smtplib", SimpleNamespace(SMTP=DummySMTP))

    email_sender.send_email_custom(
        {"address": "a@b", "password": "p"},
        "Asunto",
        "<p>Cuerpo</p>",
        {"email_to": "c@d"},
        signature_path=str(img),
    )

    html_part = sent["msg"].get_body(preferencelist=("html",)).get_content()
    assert "data:image" in html_part
