from __future__ import annotations

import time
from collections import OrderedDict

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from compras_tn.domain.models import ItemStatus, JobStatus, OperationResult
from compras_tn.presentation.jobs import JobManager
from compras_tn.application.task_cycle import WARNING_PREFIX


def page_header(title: str, subtitle: str = "") -> QWidget:
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 8)
    label = QLabel(title)
    label.setObjectName("PageTitle")
    layout.addWidget(label)
    if subtitle:
        description = QLabel(subtitle)
        description.setObjectName("PageSubtitle")
        description.setWordWrap(True)
        layout.addWidget(description)
    return widget


class ReviewDialog(QDialog):
    """Resizable review with scrollable content and permanently visible decisions."""
    def __init__(self, title, summary, headers, rows, accept_label, parent=None, details=""):
        super().__init__(parent)
        self.setWindowTitle(title)
        available = self.screen().availableGeometry()
        self.resize(min(1100, int(available.width() * .9)), min(650, int(available.height() * .85)))
        layout = QVBoxLayout(self)
        label = QLabel(summary)
        label.setWordWrap(True)
        layout.addWidget(label)
        self.table = QTableWidget(len(rows), len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(42)
        for index, values in enumerate(rows):
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                self.table.setItem(index, column, item)
        self.table.resizeColumnsToContents()
        for column in range(len(headers)):
            self.table.setColumnWidth(column, max(90, min(300, self.table.columnWidth(column))))
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)
        if details:
            info = QPlainTextEdit(details)
            info.setReadOnly(True)
            info.setMaximumHeight(115)
            layout.addWidget(info)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText(accept_label)
        self.buttons.button(QDialogButtonBox.Cancel).setText("Cancelar")
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(bool(rows))
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)


class OperationPanel(QWidget):
    def __init__(self, jobs: JobManager, parent: QWidget | None = None):
        super().__init__(parent)
        self.jobs = jobs
        self.job_id = ""
        self._started_at = 0.0
        self._job_ids: OrderedDict[str, str] = OrderedDict()
        self._completion_notices: dict[str, tuple[bool, str]] = {}
        self._cycle_warnings = []
        self._cycle_dialog = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.status = QLabel("Listo.")
        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.setProperty("secondary", True)
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel)
        row.addWidget(self.status, 1)
        self.elapsed = QLabel('')
        row.addWidget(self.elapsed)
        self.clock = QTimer(self)
        self.clock.timeout.connect(lambda: self.elapsed.setText(
            f'{int(time.monotonic() - self._started_at)} s' if self._job_ids else ''))
        self.clock.start(1000)
        row.addWidget(self.cancel_button)
        layout.addLayout(row)
        self.cycle_banner = QLabel("Hay pasos anteriores del sistema sin registro. Consulte los detalles del ciclo.")
        self.cycle_banner.setWordWrap(True)
        self.cycle_banner.setStyleSheet("background:#fff3cd;color:#663c00;border:2px solid #d48806;border-radius:6px;padding:10px;font-size:15px;font-weight:bold;")
        self.cycle_banner.hide()
        layout.addWidget(self.cycle_banner)
        self.cycle_details = QPushButton("Ver tareas y procesos pendientes")
        self.cycle_details.clicked.connect(self._show_cycle_details)
        self.cycle_details.hide()
        layout.addWidget(self.cycle_details)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(500)
        self.log.setMinimumHeight(120)
        layout.addWidget(self.log)
        jobs.job_progress.connect(self._progress)
        jobs.job_finished.connect(self._finished)
        jobs.job_failed.connect(self._failed)

    def compact(self):
        self.log.setMinimumHeight(65)
        self.log.setMaximumHeight(100)
        self.log.hide()
        toggle = QPushButton("Mostrar detalles")
        toggle.setProperty("secondary", True)
        toggle.setCheckable(True)
        toggle.toggled.connect(self.log.setVisible)
        toggle.toggled.connect(lambda checked: toggle.setText("Ocultar detalles" if checked else "Mostrar detalles"))
        self.layout().itemAt(0).layout().insertWidget(1, toggle)

    def begin(
        self,
        job_id: str,
        message: str,
        *,
        completion_popup: bool = False,
        completion_title: str = "Proceso",
    ) -> None:
        if not self._job_ids:
            self._started_at = time.monotonic()
            self._cycle_warnings = []
            self.cycle_banner.hide()
            self.cycle_details.hide()
            if self._cycle_dialog:
                self._cycle_dialog.close()
        self._job_ids[job_id] = message
        self._completion_notices[job_id] = (completion_popup, completion_title)
        self.job_id = job_id
        self._show_active_status(message)
        self.cancel_button.setEnabled(True)
        self.progress.setRange(0, 0)
        self.log.appendPlainText(f"[{job_id[:8]}] {message}")

    def cancel(self) -> None:
        if self._job_ids:
            for job_id in list(self._job_ids):
                self.jobs.cancel(job_id)
            self.status.setText("Cancelación solicitada…")
            self.cancel_button.setEnabled(False)

    def has_active_job(self) -> bool:
        return bool(self._job_ids)

    def append(self, message: str) -> None:
        self.log.appendPlainText(message)

    def _progress(self, job_id: str, current: int, total: int, message: str) -> None:
        if job_id not in self._job_ids:
            return
        self.progress.setRange(0, max(1, total))
        self.progress.setValue(current)
        if message.startswith(WARNING_PREFIX):
            self._show_cycle_warning(message)
            self.status.setText("Pasos anteriores pendientes. Consulte los detalles del ciclo.")
        else:
            self.status.setText(message)
        self.log.appendPlainText(f"[{job_id[:8]}] {message}")

    def _finished(self, job_id: str, result: object) -> None:
        if job_id not in self._job_ids:
            return
        self._job_ids.pop(job_id, None)
        show_notice, title = self._completion_notices.pop(job_id, (False, "Proceso"))
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        prefix = f"[{job_id[:8]}]"
        if isinstance(result, OperationResult):
            if WARNING_PREFIX in result.message:
                summary, warning = result.message.split(WARNING_PREFIX, 1)
                self._show_cycle_warning(WARNING_PREFIX + warning)
                self.status.setText(summary.strip() or result.status.value)
            else:
                self.status.setText(result.message or result.status.value)
            for item in result.items:
                self.log.appendPlainText(
                    f"{prefix} [{item.status.value}] {item.key}: {item.message}"
                )
        else:
            state = self.jobs.state(job_id)
            self.status.setText("Proceso cancelado." if state == "cancelled" else "Proceso completado.")
        if show_notice:
            self._show_completion_notice(title, result)
        self._after_completion()

    def _failed(self, job_id: str, message: str) -> None:
        if job_id not in self._job_ids:
            return
        self._job_ids.pop(job_id, None)
        show_notice, title = self._completion_notices.pop(job_id, (False, "Proceso"))
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status.setObjectName("StatusError")
        self.status.setText(message)
        self.log.appendPlainText(f"[{job_id[:8]}] [error] {message}")
        if show_notice:
            QMessageBox.critical(self, f"{title} · Error", f"El proceso no pudo completarse.\n\n{message}")
        self._after_completion()

    def _show_completion_notice(self, title: str, result: object) -> None:
        if not isinstance(result, OperationResult):
            state = self.jobs.state(self.job_id)
            if state == "cancelled":
                QMessageBox.warning(self, f"{title} · Cancelado", "El proceso fue cancelado.")
            else:
                QMessageBox.information(self, f"{title} · Completado", "El proceso finalizó correctamente.")
            return
        succeeded = sum(item.status == ItemStatus.SUCCEEDED for item in result.items)
        skipped = sum(item.status == ItemStatus.SKIPPED for item in result.items)
        failed = sum(item.status in {ItemStatus.FAILED, ItemStatus.NOT_FOUND} for item in result.items)
        summary = f"Correctos: {succeeded}\nCon novedades: {skipped}\nErrores: {failed}"
        if result.report_path:
            summary += f"\n\nReporte: {result.report_path}"
        if result.message:
            summary += f"\n\n{result.message}"
        mail_error = "no se pudo enviar" in result.message.casefold()
        if result.status == JobStatus.CANCELLED:
            QMessageBox.warning(self, f"{title} · Cancelado", summary)
        elif result.status == JobStatus.FAILED:
            QMessageBox.critical(self, f"{title} · Error", summary)
        elif result.status == JobStatus.PARTIAL or failed or skipped or mail_error:
            QMessageBox.warning(self, f"{title} · Con novedades", summary)
        else:
            QMessageBox.information(self, f"{title} · Exitoso", summary)

    def _after_completion(self) -> None:
        self.job_id = next(reversed(self._job_ids), "")
        self.cancel_button.setEnabled(bool(self._job_ids))
        if self._job_ids:
            self._show_active_status(self._job_ids[self.job_id])

    def _show_cycle_warning(self, message):
        if message in self._cycle_warnings:
            return
        self._cycle_warnings.append(message)
        self.cycle_banner.show()
        self.cycle_details.show()

    def _show_cycle_details(self):
        if not self._cycle_warnings:
            return
        if self._cycle_dialog:
            self._cycle_dialog.close()
            self._cycle_dialog.deleteLater()
        dialog = QDialog(self)
        dialog.setWindowTitle("Detalle de pasos anteriores del sistema")
        dialog.resize(780, 440)
        layout = QVBoxLayout(dialog)
        heading = QLabel("¡ATENCIÓN AL CICLO DE LA TAREA!")
        heading.setStyleSheet("background:#fff3cd;color:#663c00;font-size:18px;font-weight:bold;padding:12px;")
        layout.addWidget(heading)
        details = QPlainTextEdit("\n\n".join(self._cycle_warnings))
        details.setReadOnly(True)
        layout.addWidget(details, 1)
        note = QLabel("Registro de la comprobación de pasos anteriores del sistema.")
        layout.addWidget(note)
        close = QPushButton("Cerrar aviso")
        close.clicked.connect(dialog.close)
        layout.addWidget(close)
        self._cycle_dialog = dialog
        dialog.show()

    def _show_active_status(self, message: str) -> None:
        if len(self._job_ids) > 1:
            self.status.setText(f"{len(self._job_ids)} procesos activos · {message}")
        else:
            self.status.setText(message)
