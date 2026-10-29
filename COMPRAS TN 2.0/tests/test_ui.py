from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from conftest import PROJECT_ROOT
from PySide6.QtWidgets import QCheckBox, QDialogButtonBox, QMessageBox, QTableWidget

from compras_tn.bootstrap import build_container
from compras_tn.domain.models import (
    DispatchPreview,
    DispatchPreviewItem,
    ItemStatus,
    JobStatus,
    OperationItem,
    OperationResult,
    SessionCredentials,
    TaskRecord,
)
from compras_tn.paths import AppPaths
from compras_tn.presentation.jobs import JobManager
from compras_tn.presentation.main_window import MainWindow
from compras_tn.presentation.operation_pages import DispatchPreviewDialog
from compras_tn.presentation.widgets import OperationPanel
from compras_tn.presentation.workflows_page import WorkflowRunner


def test_old_text_preferences_preserve_visible_browser_across_modules(qtbot, tmp_path):
    from compras_tn.presentation.operation_pages import DownloadsPage, ReassignmentPage
    container = build_container(app_paths=AppPaths.from_root(tmp_path / "settings-data"), project_root=PROJECT_ROOT)
    container.project_root = tmp_path / "isolated-project"
    try:
        for namespace, key, value in (("automation", "actua_headless", "False"), ("downloads", "headless", "0"), ("downloads", "abastecimiento_headless", "false")):
            container.services.set_setting(namespace, key, value)
        window = MainWindow(container)
        qtbot.addWidget(window)
        window._authenticated(SessionCredentials(username="TEST", email="test@example.com", password="test-only"))
        downloads = window.findChild(DownloadsPage)
        assert not downloads.normal_headless.isChecked()
        assert not downloads.supply_headless.isChecked()
        assert all(not page.headless.isChecked() for page in window.findChildren(ReassignmentPage))
        assert all(not page.headless.isChecked() for page in window.findChildren(WorkflowRunner))
    finally:
        container.services.logout()
        container.database.close()


def test_single_window_navigation_and_manual_task_entry(qtbot: Any, tmp_path: Path, monkeypatch: Any) -> None:
    container = build_container(
        app_paths=AppPaths.from_root(tmp_path / "ui-data"),
        project_root=PROJECT_ROOT,
    )
    container.project_root = tmp_path / "isolated-project"
    window = MainWindow(container)
    qtbot.addWidget(window)
    window.show()
    window._authenticated(
        SessionCredentials(username="ANA", email="ana@example.com", password="memory-only")
    )
    assert window.root_stack.currentWidget() is window.shell
    assert len(window.nav_buttons) == 13
    assert sum(b.text() == "Organizador de archivos" for b in window.nav_buttons) == 1
    window.nav_buttons[-1].click()
    assert window.pages.currentIndex() == 12

    runner = window.findChild(WorkflowRunner)
    assert runner is not None
    assert runner.manual.parentWidget().isHidden()
    toggle = next(box for box in runner.findChildren(QCheckBox) if box.text() == "Ingreso manual")
    toggle.setChecked(True)
    assert not runner.manual.parentWidget().isHidden()
    assert runner.source.findData("carga_oc_automatica") >= 0
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[-1]))
    runner.manual.setPlainText("00123\nNO ES TAREA")
    runner.add_manual()
    assert warnings and runner.table.rowCount() == 0
    runner.manual.setPlainText("00123\n00456\n00123\n")
    runner.add_manual()
    assert runner.table.rowCount() == 2
    assert {runner.table.item(row, 1).text() for row in range(2)} == {"00123", "00456"}
    container.services.enqueue_tasks([
        TaskRecord(
            task_number="00123",
            origin="correo",
            purchase_mode=runner.mode,
            order_number="300001",
            supplier="Proveedor enriquecido",
        )
    ])
    runner.refresh()
    assert runner.table.rowCount() == 2
    task_row = next(
        row for row in range(runner.table.rowCount())
        if runner.table.item(row, 1).text() == "00123"
    )
    assert runner.table.item(task_row, 2).text() == "manual / correo"
    assert runner.table.item(task_row, 3).text() == "300001"
    window.close()


def test_job_manager_progress_and_safe_cancellation(qtbot: Any) -> None:
    manager = JobManager()
    release = threading.Event()
    results: list[OperationResult] = []
    manager.job_finished.connect(lambda _job_id, result: results.append(result))

    def callback(progress: Any, cancelled: Any) -> OperationResult:
        progress(1, 2, "iniciado")
        release.wait(2)
        status = JobStatus.CANCELLED if cancelled() else JobStatus.SUCCEEDED
        return OperationResult(status=status)

    job_id = manager.submit("default", callback)
    qtbot.waitUntil(manager.has_running_jobs, timeout=1000)
    manager.cancel(job_id)
    release.set()
    qtbot.waitUntil(lambda: not manager.has_running_jobs(), timeout=3000)
    assert results[0].status == JobStatus.CANCELLED


def test_operation_panel_only_shows_one_requested_completion_popup(
    qtbot: Any, monkeypatch: Any
) -> None:
    manager = JobManager()
    panel = OperationPanel(manager)
    qtbot.addWidget(panel)
    calls: list[tuple[str, str, str]] = []
    for method, kind in (("information", "information"), ("warning", "warning"), ("critical", "critical")):
        monkeypatch.setattr(
            QMessageBox,
            method,
            lambda _parent, title, message, level=kind: calls.append((level, title, message)),
        )
    panel.begin(
        "operational",
        "Procesando…",
        completion_popup=True,
        completion_title="Descargas OC",
    )
    panel._finished(
        "operational",
        OperationResult.from_items([
            OperationItem(key="1", status=ItemStatus.SUCCEEDED, message="Correcto")
        ]),
    )
    panel.begin(
        "partial", "Procesando…", completion_popup=True, completion_title="Descargas OC"
    )
    panel._finished(
        "partial",
        OperationResult.from_items([
            OperationItem(key="1", status=ItemStatus.SUCCEEDED),
            OperationItem(key="2", status=ItemStatus.FAILED),
        ]),
    )
    panel.begin(
        "failed", "Procesando…", completion_popup=True, completion_title="Descargas OC"
    )
    panel._finished(
        "failed",
        OperationResult.from_items([
            OperationItem(key="2", status=ItemStatus.FAILED),
        ]),
    )
    panel.begin(
        "cancelled", "Procesando…", completion_popup=True, completion_title="Descargas OC"
    )
    panel._finished(
        "cancelled",
        OperationResult(status=JobStatus.CANCELLED, message="Cancelado"),
    )
    panel.begin("background", "Cargando…")
    panel._finished("background", [1, 2, 3])

    assert [kind for kind, _title, _message in calls] == [
        "information", "warning", "critical", "warning"
    ]
    assert calls[0][1] == "Descargas OC · Exitoso"


def test_dispatch_preview_dialog_lists_recipients_and_errors(qtbot: Any) -> None:
    preview = DispatchPreview(
        items=[
            DispatchPreviewItem(
                order_number="373627",
                valid=True,
                task_numbers=["19558554854", "19558554855"],
                supplier="Proveedor",
                recipients=["ventas@example.com"],
                cc=["compras@example.com"],
                pdf_path="C:/OC/373627.pdf",
                pdf_mtime_ns=1_700_000_000_000_000_000,
            ),
            DispatchPreviewItem(order_number="373628", error="No se encontró el PDF."),
        ]
    )
    dialog = DispatchPreviewDialog(preview)
    qtbot.addWidget(dialog)

    table = dialog.findChild(QTableWidget)
    buttons = dialog.findChild(QDialogButtonBox)

    assert table is not None and table.rowCount() == 2
    assert table.item(0, 1).text() == "19558554854 - 19558554855"
    assert table.item(0, 3).text() == "ventas@example.com"
    assert "No se encontró el PDF" in table.item(1, 6).text()
    assert buttons is not None
    assert buttons.button(QDialogButtonBox.Ok).text() == "Enviar 1 orden válida"

