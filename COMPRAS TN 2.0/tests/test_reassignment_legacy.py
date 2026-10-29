from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from types import SimpleNamespace

import pytest
from conftest import PROJECT_ROOT
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox, QScrollArea

from compras_tn.bootstrap import build_container
from compras_tn.domain.models import Assignment, PurchaseMode, SessionCredentials, TaskRecord
from compras_tn.infrastructure.mail import CorporateMailGateway
from compras_tn.paths import AppPaths
from compras_tn.presentation.jobs import JobManager
from compras_tn.presentation.operation_pages import ReassignmentPage


def test_legacy_range_subject_owner_and_provider(repositories, monkeypatch):
    zone = timezone(timedelta(hours=-5))
    start = datetime(2026, 9, 8, 11, 2, tzinfo=zone)
    end = start + timedelta(days=1)
    messages = []
    for when, owner in [(start, "ana@telconet.ec"), (end, "ana@telconet.ec"),
                        (end + timedelta(seconds=1), "ana@telconet.ec"), (start, "otra@telconet.ec")]:
        msg = EmailMessage()
        msg["Subject"] = 'NOTIFICACIÓN A PROVEEDOR: TAREA: "162841741"'
        msg["From"] = "compras@telconet.ec"
        msg["Date"] = when
        msg.set_content(f'Estimados "Proveedor de prueba"\nCoordinando el mantenimiento con "José" (0991234567)\n{owner}')
        messages.append(msg.as_bytes())

    class IMAP:
        def login(self, *_): pass
        def logout(self): pass
        def select(self, *_, **__): return "OK", []
        def search(self, *args):
            assert "SINCE" in args
            return "OK", [b"1 2 3 4"]
        def fetch(self, number, kind):
            assert kind == "(BODY.PEEK[])"
            return "OK", [(b"", messages[int(number) - 1])]

    gateway = CorporateMailGateway(repositories)
    monkeypatch.setattr(gateway, "_connect_imap", lambda *_: IMAP())
    credentials = SessionCredentials(username="ana", email="ana@telconet.ec", password="test-only")
    results = gateway.scan_reassignment_tasks(credentials, start, end, "NOTIFICACION A PROVEEDOR:")
    assert len(results) == 2  # both inclusive endpoints; duplicate emails remain selectable
    assert all(item["task_number"] == "162841741" for item in results)
    assert all(item["supplier"] == "Proveedor de prueba" for item in results)
    assert results[0]["mecanico"] == "José"
    assert results[0]["telefono"] == "0991234567"


@pytest.mark.parametrize("mode", [PurchaseMode.SERVICIOS, PurchaseMode.BIENES])
def test_visible_table_and_selected_only_batch(qtbot, tmp_path, monkeypatch, mode):
    container = build_container(app_paths=AppPaths.from_root(tmp_path / "app"), project_root=PROJECT_ROOT)
    # The UI uses a fake job queue so this test cannot open a corporate browser.
    jobs = JobManager()
    services = SimpleNamespace(get_setting=lambda *args: args[-1], reassign_tasks=lambda *a, **k: captured.append(a[0]))
    services.list_assignments = lambda: [Assignment(subdepartment="BODEGA", department="Departamento de prueba", person="Persona de prueba")]
    captured = []
    callbacks = []
    monkeypatch.setattr(jobs, "submit", lambda kind, callback: callbacks.append(callback) or "execute")
    page = ReassignmentPage(services, jobs, mode)
    qtbot.addWidget(page)
    page.resize(1150, 700)
    page.show()
    page.scan_job = "scan"
    page._scanned("scan", [TaskRecord(task_number=number, origin="reasignacion", purchase_mode=mode,
                                     payload={"reasignacion": "BODEGA", "details": [{"Factura": "123", "Ingreso": "456"}]})
                            for number in ["162841741", "164169364", "162841741"]])
    qtbot.wait(50)
    assert page.table.height() >= 240
    assert page.findChild(QScrollArea) is not None
    if mode == PurchaseMode.BIENES:
        assert not page.department.isVisible()
        assert page.sender.text() == "omar777j@gmail.com"
    page._mark_all(Qt.Unchecked)
    page.table.item(0, 0).setCheckState(Qt.Checked)
    page.table.item(2, 0).setCheckState(Qt.Checked)
    page.department.setText("Departamento de prueba")
    page.employee.setText("Empleado de prueba")
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.Yes)
    page.execute()
    callbacks[-1](lambda *a: None, lambda: False)
    assert [task.task_number for task in captured[0]] == ["162841741"]
    container.database.close()
