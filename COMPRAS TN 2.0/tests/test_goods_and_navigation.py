from types import SimpleNamespace

import pytest
from selenium.common.exceptions import TimeoutException, WebDriverException
from test_application_services import _facade
from test_telcos_resilience import Driver, _credentials, _gateway

from compras_tn.domain.models import Assignment, ItemStatus, PurchaseMode, TaskRecord
from compras_tn.infrastructure.automation.downloads import OrderPortalPage
from compras_tn.infrastructure.mail_parse import parse_goods_body

BODY = '''Tarea: 162841741
Reasignación a: BODEGA QUITO
Datos relacionados:
- OC 373627 | Proveedor uno | FAC. 001-123 | INGR. 9001
Tarea: 162841742
Reasignación a: BODEGA GUAYAQUIL
Datos relacionados:
- OC 373628 | Proveedor dos | FAC. 001-124 | INGR. 9002
'''


def test_goods_parser_extracts_all_blocks_without_services_notification():
    tasks = parse_goods_body(BODY)
    assert [t["task_number"] for t in tasks] == ["162841741", "162841742"]
    assert tasks[0]["reasignacion"] == "BODEGA QUITO"
    assert tasks[1]["details"][0]["Ingreso"] == "9002"
    assert not parse_goods_body('NOTIFICACION A PROVEEDOR: TAREA: "162841741"')


@pytest.mark.parametrize('separator', ['\n', ' '])
def test_reassignment_received_format_preserves_invoice_pairs(separator):
    body = separator.join([
        'Estimado/a, Tarea: 156827889',
        'Reasignación a: GENERAL',
        'Datos relacionados:',
        '- OC 366885 | PADI | FAC. 3563 | INGR. 511325805',
        '- OC 366885 | PADI | FAC. 3563/3580 | INGR. 511325805/511979805',
        '- OC 366885 | PADI | FAC. 3648 | INGR. 522609005',
        'Tarea: 160118788',
        'Reasignación a: OBRA CIVIL',
        'Datos relacionados:',
        '- OC 370806 | PADI | FAC. 3646 | INGR. 522608405',
    ])
    tasks = parse_goods_body(body)
    assert [t['task_number'] for t in tasks] == ['156827889', '160118788']
    assert len(tasks[0]['details']) == 3
    assert tasks[0]['details'][1]['Factura'] == '3563/3580'
    assert tasks[0]['details'][1]['Ingreso'] == '511325805/511979805'
    assert tasks[1]['reasignacion'] == 'OBRA CIVIL'


def test_goods_resolves_catalog_before_browser(repositories, tmp_path):
    facade, *_ = _facade(repositories, tmp_path)
    tasks = [TaskRecord(task_number=t["task_number"], purchase_mode=PurchaseMode.BIENES, payload=t)
             for t in parse_goods_body(BODY)]
    with pytest.raises(ValueError, match="BODEGA QUITO"):
        facade.reassign_tasks(tasks, "incorrecto", "incorrecto", "Taller", headless=True)
    for key, person in [("BODEGA QUITO", "Persona Quito"), ("BODEGA GUAYAQUIL", "Persona Guayaquil")]:
        repositories.save_assignment(Assignment(subdepartment=key, department=key, person=person))
    result = facade.reassign_tasks(tasks, "incorrecto", "incorrecto", "Taller", headless=True)
    assert all(item.status == ItemStatus.SUCCEEDED for item in result.items)
    assert tasks[0].payload["employee_override"] == "Persona Quito"
    assert tasks[1].payload["employee_override"] == "Persona Guayaquil"


def test_goods_scan_detects_received_subject_and_multipart(repositories, monkeypatch):
    from datetime import datetime
    from email.message import EmailMessage
    from zoneinfo import ZoneInfo

    from compras_tn.infrastructure.mail import CorporateMailGateway

    message = EmailMessage()
    message['From'] = 'omar777j@gmail.com'
    message['To'] = 'usuario_demo@telconet.ec'
    message['Subject'] = '📢 Tareas Completadas - Reasignación Necesaria (JT)'
    message['Date'] = 'Fri, 11 Sep 2026 16:20:00 -0500'
    message.set_content(BODY)
    message.add_alternative('<div>' + BODY.replace('\n', '<br>') + '</div>', subtype='html')
    class Inbox:
        def login(self, *args):
            pass
        def select(self, folder, readonly):
            assert readonly
            return 'OK', []
        def search(self, charset, *criteria):
            assert 'omar777j@gmail.com' in criteria
            return 'OK', [b'1']
        def fetch(self, number, query):
            assert query == '(BODY.PEEK[])'
            return 'OK', [(b'', message.as_bytes())]
        def logout(self):
            pass
    gateway = CorporateMailGateway(repositories)
    monkeypatch.setattr(gateway, '_connect_imap', lambda *a: Inbox())
    zone = ZoneInfo('America/Guayaquil')
    tasks = gateway.scan_goods_reassignment_tasks(
        _credentials(), datetime(2026, 9, 11, tzinfo=zone),
        datetime(2026, 9, 11, 23, 59, 59, tzinfo=zone), '', 'omar777j@gmail.com',
    )
    assert [t['task_number'] for t in tasks] == ['162841741', '162841742']


def test_goods_actions_match_original_receipt_followup_and_reassignment(tmp_path, monkeypatch):
    gateway = _gateway(tmp_path)
    calls = []
    class Page:
        def __getattr__(self, name):
            return lambda *args, **kwargs: calls.append((name, args))
    monkeypatch.setattr(gateway, "_new_authenticated_driver", lambda *a: Driver())
    monkeypatch.setattr(gateway, "_tasks_page", lambda *a: Page())
    payload = parse_goods_body(BODY)[0]
    payload.update(department_override="Bodega Quito", employee_override="Persona Quito")
    task = TaskRecord(task_number=payload["task_number"], purchase_mode=PurchaseMode.BIENES, payload=payload)
    result = gateway.reassign(_credentials(), [task], "NO", "NO", "Taller", headless=True)
    assert result.items[0].status == ItemStatus.SUCCEEDED
    assert ("enter_observation", ("SE RECIBE LA MERCADERIA",)) in calls
    written = [args[1] for name, args in calls if name == "set_text"]
    assert written == ["SE INGRESA LA FACTURA 001-123 CON EL INGRESO 9001", "TRABAJO REALIZADO"]
    assert [args[1] for name, args in calls if name == "select_autocomplete"] == ["Bodega Quito", "Persona Quito"]


def test_naf_connection_failure_has_bounded_retry(tmp_path):
    calls = []
    def fail(url):
        calls.append(url)
        raise WebDriverException("net::ERR_CONNECTION_TIMED_OUT")
    page = OrderPortalPage(SimpleNamespace(get=fail), tmp_path)
    with pytest.raises(TimeoutError, match="dos intentos"):
        page._navigate("https://cas.telconet.ec/cas/login")
    assert len(calls) == 2


def test_click_timeout_does_not_submit_twice(tmp_path):
    scripts = []
    def click():
        raise TimeoutException("renderer")
    page = OrderPortalPage(SimpleNamespace(execute_script=lambda *a: scripts.append(a)), tmp_path)
    with pytest.raises(TimeoutException):
        page._click_element(SimpleNamespace(click=click))
    assert not any(".click()" in str(script) for script in scripts)
