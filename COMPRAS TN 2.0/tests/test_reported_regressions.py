from email.message import EmailMessage
from types import SimpleNamespace

from compras_tn.domain.models import PurchaseMode, SessionCredentials, TaskRecord
from compras_tn.infrastructure.automation.telcos import TasksPage
from compras_tn.infrastructure.mail import CorporateMailGateway
from compras_tn.infrastructure.order_mail import AUTHORIZED, PopOrderMailScanner
from compras_tn.presentation.rich_template import RichTemplateEditor


def notice(body, sender="naf@telconet.ec"):
    msg = EmailMessage()
    msg["From"] = sender
    msg["Subject"] = "SISTEMA NAF: AUTORIZACIÓN COMPLETA DE ORDEN COMPRA NO.373627"
    msg.set_content(body)
    return msg.as_bytes().splitlines()


def test_only_number_in_authorized_clause_is_an_order():
    body = "Ha sido autorizada la orden de compra de No. 373627. TAREA #162841741; orden de compra No. 999999 pendiente."
    assert AUTHORIZED.findall(body) == ["373627"]
    assert not AUTHORIZED.findall("No ha sido autorizada la orden de compra de No. 373627")


class Pop:
    def __init__(self):
        self.messages = [
            notice("antiguo"),
            notice(
                "Se comunica que ha sido autorizada la orden de compra de No. 373627. "
                "TAREA #162841741 / TAREA #162841742 / TAREA #162841741"
            ),
            notice("Orden de compra No. 373628 pendiente de autorización. TAREA #162841741"),
            notice("Mensaje corriente", "persona@example.com"),
        ]
        self.read = []

    def user(self, *_): pass
    def pass_(self, *_): pass
    def quit(self): pass
    def uidl(self):
        return b"OK", [f"{i} uid-{i}".encode() for i in range(1, len(self.messages) + 1)], 0
    def top(self, number, *_):
        lines = self.messages[number - 1]
        end = lines.index(b"")
        return b"OK", lines[:end], 0
    def retr(self, number):
        self.read.append(number)
        return b"OK", self.messages[number - 1], 0


def test_incremental_scan_retains_failed_orders_and_ignores_unapproved(database, repositories, monkeypatch):
    pop = Pop()
    # Exact corporate body shown in the screenshot has "de No.".
    monkeypatch.setattr("compras_tn.infrastructure.order_mail.poplib.POP3_SSL", lambda *a, **k: pop)
    repositories.set("downloads", "last_uidl", "uid-1")
    credentials = SessionCredentials(username="ana", email="ana@telconet.ec", password="test-only")
    scanner = PopOrderMailScanner(database, repositories)
    first = scanner.scan(credentials)
    assert [item.orders[0]["order_number"] for item in first] == ["373627"]
    assert first[0].orders[0]["task_numbers"] == ["162841741", "162841742"]
    assert pop.read == [2, 3]  # old and unrelated mail bodies are not fetched
    pop.read.clear()
    second = PopOrderMailScanner(database, repositories).scan(credentials)
    assert second == first  # failed download survives application restart
    assert pop.read == []
    scanner.mark_processed([first[0].external_id])
    assert scanner.scan(credentials) == []
    assert pop.read == []


def test_cancelled_scan_resumes_without_skipping_mail(database, repositories, monkeypatch):
    pop = Pop()
    monkeypatch.setattr("compras_tn.infrastructure.order_mail.poplib.POP3_SSL", lambda *a, **k: pop)
    repositories.set("downloads", "last_uidl", "uid-1")
    credentials = SessionCredentials(username="ana", email="ana@telconet.ec", password="test-only")
    scanner = PopOrderMailScanner(database, repositories)
    first = scanner.scan(credentials, cancelled=lambda: bool(pop.read))
    assert len(first) == 1
    pop.read.clear()
    assert scanner.scan(credentials) == first
    assert pop.read == [3]


def test_mail_server_matches_legacy_and_preserves_custom(repositories):
    gateway = CorporateMailGateway(repositories)
    assert gateway._imap_host() == "pop.telconet.ec"
    repositories.set("email", "imap_server", "imap.telconet.ec")
    assert gateway._imap_host() == "pop.telconet.ec"
    repositories.set("email", "imap_server", "custom.example.com")
    assert gateway._imap_host() == "custom.example.com"


def test_hidden_header_with_breaks_selects_task_not_parent():
    def header(value):
        return SimpleNamespace(text="", get_attribute=lambda _: value)
    driver = SimpleNamespace(find_elements=lambda *_: [header("No.TareaPadre"), header("No.Tarea")])
    row = SimpleNamespace(find_elements=lambda *_: [SimpleNamespace(text="111111"), SimpleNamespace(text="162841741")])
    assert TasksPage(driver).row_number(row) == "162841741"


def test_dismiss_only_selected_origin_and_mode(repositories):
    tasks = [TaskRecord(task_number="162841741", origin="manual", purchase_mode=PurchaseMode.BIENES),
             TaskRecord(task_number="162841741", origin="correo", purchase_mode=PurchaseMode.SERVICIOS),
             TaskRecord(task_number="164169364", origin="manual", purchase_mode=PurchaseMode.BIENES)]
    repositories.enqueue(tasks)
    repositories.dismiss(tasks[:1])
    remaining = repositories.list_pending()
    assert {(t.task_number, t.origin) for t in remaining} == {("162841741", "correo"), ("164169364", "manual")}


def test_template_preserves_original_and_visual_format(qtbot):
    original = '<p style="color:#123456"><b>Hola {{ proveedor }}</b></p><table><tr><td>OC</td></tr></table>'
    editor = RichTemplateEditor(original)
    qtbot.addWidget(editor)
    assert editor.toPlainText() == original
    editor.tabs.setCurrentIndex(1)
    editor.tabs.setCurrentIndex(0)
    assert editor.toPlainText() == original
    editor.visual.append("Nueva línea")
    result = editor.toPlainText()
    assert "{{ proveedor }}" in result
    assert "#123456" in result
    assert "<table" in result


def test_signature_sent_as_inline_mime_image(repositories, monkeypatch):
    captured = []

    class SMTP:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def ehlo(self): pass
        def starttls(self, **_): pass
        def login(self, *_): pass
        def send_message(self, message, **_): captured.append(message)

    monkeypatch.setattr("compras_tn.infrastructure.mail.smtplib.SMTP", lambda *a, **k: SMTP())
    credentials = SessionCredentials(username="ana", email="ana@telconet.ec", password="test-only")
    CorporateMailGateway(repositories).send_html(
        credentials, ["test@example.com"], "Prueba local",
        '<p style="color:#123456">Hola</p><img src="data:image/png;base64,aW1hZ2U=">',
    )
    parts = list(captured[0].walk())
    image = next(part for part in parts if part.get_content_type() == "image/png")
    body = next(part for part in parts if part.get_content_type() == "text/html").get_content()
    assert image.get_payload(decode=True) == b"image"
    assert f'cid:{image["Content-ID"][1:-1]}' in body
    assert "#123456" in body


def test_signature_inserted_inside_html_body(tmp_path):
    from compras_tn.domain.models import EmailTemplate
    from compras_tn.infrastructure.templates import JinjaTemplateRenderer

    signature = tmp_path / "firma.png"
    signature.write_bytes(b"image")
    result = JinjaTemplateRenderer().render(
        EmailTemplate(name="Firma", html="<html><body>Hola</body></html>", signature_path=str(signature)), {}
    )
    assert result.index("<img") < result.index("</body>")
