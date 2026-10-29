from __future__ import annotations

from datetime import datetime
from typing import Any

from PySide6.QtCore import QDate, QDateTime, Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from compras_tn.application.services import ApplicationFacade
from compras_tn.domain.models import (
    DispatchPreview,
    EmailTemplate,
    OperationRequest,
    OperationResult,
    PurchaseMode,
    TaskRecord,
)
from compras_tn.presentation.jobs import JobManager
from compras_tn.presentation.widgets import OperationPanel, page_header


def _tokens(text: str) -> list[str]:
    normalized = text.replace(",", "\n").replace(";", "\n")
    result: list[str] = []
    for line in normalized.splitlines():
        value = line.strip()
        if value and value not in result:
            result.append(value)
    return result


def _check_item(text: str, checked: bool = True) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
    item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
    return item


class TemplateSelector(QComboBox):
    def __init__(self, services: ApplicationFacade, parent: QWidget | None = None):
        super().__init__(parent)
        self.services = services
        self.templates: list[EmailTemplate] = []
        self.refresh()

    def refresh(self) -> None:
        selected = self.currentText()
        self.templates = self.services.list_templates()
        self.clear()
        self.addItems([item.name for item in self.templates])
        if selected:
            index = self.findText(selected)
            if index >= 0:
                self.setCurrentIndex(index)

    def selected(self) -> EmailTemplate:
        if not 0 <= self.currentIndex() < len(self.templates):
            raise ValueError("Debe configurar y seleccionar una plantilla HTML.")
        return self.templates[self.currentIndex()]


class DispatchPreviewDialog(QDialog):
    def __init__(self, preview: DispatchPreview, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Resumen de correos masivos")
        self.resize(1050, 520)
        layout = QVBoxLayout(self)
        summary = QLabel(
            f"Órdenes válidas: {preview.valid_count} · "
            f"Con error: {len(preview.items) - preview.valid_count}. "
            "Revise los destinatarios antes de confirmar."
        )
        summary.setWordWrap(True)
        layout.addWidget(summary)
        table = QTableWidget(len(preview.items), 7)
        table.setHorizontalHeaderLabels(
            ["OC", "Tareas", "Proveedor", "Destinatarios", "CC", "PDF elegido", "Estado"]
        )
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setAlternatingRowColors(True)
        for row, item in enumerate(preview.items):
            modified = ""
            if item.pdf_mtime_ns:
                modified = datetime.fromtimestamp(item.pdf_mtime_ns / 1_000_000_000).strftime(
                    "%d/%m/%Y %H:%M:%S"
                )
            pdf = item.pdf_path or "-"
            if modified:
                pdf += f" · {modified}"
            values = (
                item.order_number,
                " - ".join(item.task_numbers) or "-",
                item.supplier or "-",
                "; ".join(item.recipients) or "-",
                "; ".join(item.cc) or "-",
                pdf,
                "Lista para enviar" if item.valid else f"Error: {item.error}",
            )
            for column, value in enumerate(values):
                table.setItem(row, column, QTableWidgetItem(value))
        table.resizeColumnsToContents()
        for column in (2, 3, 4, 5, 6):
            table.setColumnWidth(column, min(table.columnWidth(column), 260))
        table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(table, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        accept = buttons.button(QDialogButtonBox.Ok)
        noun = "orden válida" if preview.valid_count == 1 else "órdenes válidas"
        accept.setText(f"Enviar {preview.valid_count} {noun}")
        accept.setEnabled(preview.valid_count > 0)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class MassEmailPage(QWidget):
    def __init__(
        self,
        services: ApplicationFacade,
        jobs: JobManager,
        mode: PurchaseMode,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.services = services
        self.jobs = jobs
        self.mode = mode
        self.preview_job = ""
        self._pending_template: EmailTemplate | None = None
        self._pending_grouped = True
        layout = QVBoxLayout(self)
        layout.addWidget(
            page_header(
                f"Correos masivos · {mode.value.title()}",
                "Valida proveedor, PDF y destinatarios antes de enviar; los resultados quedan disponibles para Orquestador Telcos.",
            )
        )
        box = QGroupBox("Órdenes de compra")
        box.setTitle("Ingreso manual · Órdenes de compra")
        box.setCheckable(True)
        body = QWidget()
        form = QFormLayout(body)
        wrapper = QVBoxLayout(box)
        wrapper.addWidget(body)
        box.toggled.connect(body.setVisible)
        self.orders = QPlainTextEdit()
        self.orders.setPlaceholderText("Una OC por línea")
        self.orders.setMaximumHeight(150)
        self.template = TemplateSelector(services)
        self.grouped = QCheckBox("Agrupar por RUC")
        self.grouped.setChecked(True)
        form.addRow("OC", self.orders)
        form.addRow("Plantilla", self.template)
        form.addRow("Envío", self.grouped)
        layout.addWidget(box)
        actions = QHBoxLayout()
        refresh = QPushButton("Actualizar plantillas")
        refresh.setProperty("secondary", True)
        send = QPushButton("Validar y enviar")
        refresh.clicked.connect(self.template.refresh)
        send.clicked.connect(self.run)
        actions.addWidget(send)
        actions.addWidget(refresh)
        actions.addStretch(1)
        layout.addLayout(actions)
        self.panel = OperationPanel(jobs)
        layout.addWidget(self.panel, 1)
        jobs.job_finished.connect(self._prepared)
        jobs.job_failed.connect(self._prepare_failed)

    def run(self) -> None:
        numbers = _tokens(self.orders.toPlainText())
        if not numbers:
            QMessageBox.warning(self, "Correos masivos", "Ingrese al menos una orden de compra.")
            return
        try:
            template = self.template.selected()
        except Exception as exc:
            QMessageBox.warning(self, "Correos masivos", str(exc))
            return
        self._pending_template = template
        self._pending_grouped = self.grouped.isChecked()
        self.preview_job = self.jobs.submit(
            "default",
            lambda progress, cancelled: self.services.prepare_dispatch(
                numbers, progress=progress, cancelled=cancelled
            ),
        )
        self.panel.begin(self.preview_job, "Validando órdenes y destinatarios…")

    def _prepared(self, job_id: str, result: object) -> None:
        if job_id != self.preview_job or not isinstance(result, DispatchPreview):
            return
        self.preview_job = ""
        template = self._pending_template
        if template is None or DispatchPreviewDialog(result, self).exec() != QDialog.Accepted:
            self._pending_template = None
            return
        grouped = self._pending_grouped
        self._pending_template = None
        send_job = self.jobs.submit(
            "email",
            lambda progress, cancelled: self.services.send_prepared_dispatch(
                result,
                template,
                grouped=grouped,
                mode=self.mode,
                progress=progress,
                cancelled=cancelled,
            ),
        )
        self.panel.begin(
            send_job,
            "Enviando órdenes validadas…",
            completion_popup=True,
            completion_title="Correos masivos",
        )

    def _prepare_failed(self, job_id: str, _message: str) -> None:
        if job_id == self.preview_job:
            self.preview_job = ""
            self._pending_template = None


class FollowupsPage(QWidget):
    def __init__(self, services: ApplicationFacade, jobs: JobManager, parent: QWidget | None = None):
        super().__init__(parent)
        self.services = services
        self.jobs = jobs
        self.rows: list[dict[str, Any]] = []
        self.load_job = ""
        layout = QVBoxLayout(self)
        layout.addWidget(
            page_header(
                "Seguimientos · Bienes",
                "Carga las órdenes aprobadas de Google Sheets y genera un resultado individual por correo.",
            )
        )
        actions = QHBoxLayout()
        load = QPushButton("Cargar aprobadas")
        select_all = QPushButton("Seleccionar todas")
        select_all.setProperty("secondary", True)
        load.clicked.connect(self.load)
        select_all.clicked.connect(lambda: self._set_all(True))
        actions.addWidget(load)
        actions.addWidget(select_all)
        actions.addStretch(1)
        self.template = TemplateSelector(services)
        self.attach = QCheckBox("Adjuntar PDF")
        self.attach.setChecked(True)
        actions.addWidget(QLabel("Plantilla:"))
        actions.addWidget(self.template)
        actions.addWidget(self.attach)
        layout.addLayout(actions)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Enviar", "OC", "Tarea", "Proveedor"])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)
        send = QPushButton("Enviar seguimientos seleccionados")
        send.clicked.connect(self.send)
        layout.addWidget(send, 0, Qt.AlignLeft)
        self.panel = OperationPanel(jobs)
        layout.addWidget(self.panel)
        jobs.job_finished.connect(self._loaded)

    def load(self) -> None:
        self.load_job = self.jobs.submit("default", lambda _progress, _cancelled: self.services.load_followups())
        self.panel.begin(self.load_job, "Leyendo Google Sheets…")

    def _loaded(self, job_id: str, result: object) -> None:
        if job_id != self.load_job or not isinstance(result, list):
            return
        self.rows = [row for row in result if isinstance(row, dict)]
        self.table.setRowCount(len(self.rows))
        for index, row in enumerate(self.rows):
            self.table.setItem(index, 0, _check_item(""))
            self.table.setItem(index, 1, QTableWidgetItem(str(row.get("order_number") or "")))
            self.table.setItem(index, 2, QTableWidgetItem(str(row.get("task_number") or "")))
            self.table.setItem(index, 3, QTableWidgetItem(str(row.get("supplier") or "")))
        self.table.resizeColumnsToContents()
        self.load_job = ""

    def _set_all(self, checked: bool) -> None:
        for row in range(self.table.rowCount()):
            self.table.item(row, 0).setCheckState(Qt.Checked if checked else Qt.Unchecked)

    def send(self) -> None:
        selected = [
            raw
            for row, raw in enumerate(self.rows)
            if self.table.item(row, 0).checkState() == Qt.Checked
        ]
        if not selected:
            QMessageBox.warning(self, "Seguimientos", "Seleccione al menos una orden.")
            return
        try:
            template = self.template.selected()
        except Exception as exc:
            QMessageBox.warning(self, "Seguimientos", str(exc))
            return
        if QMessageBox.question(self, "Confirmar", f"¿Enviar {len(selected)} seguimientos?") != QMessageBox.Yes:
            return
        job_id = self.jobs.submit(
            "email",
            lambda progress, cancelled: self.services.send_followups(
                selected,
                template,
                attach_pdf=self.attach.isChecked(),
                progress=progress,
                cancelled=cancelled,
            ),
        )
        self.panel.begin(job_id, "Enviando seguimientos…", completion_popup=True, completion_title="Seguimientos")


class ReassignmentPage(QWidget):
    def __init__(
        self,
        services: ApplicationFacade,
        jobs: JobManager,
        mode: PurchaseMode,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.services = services
        self.jobs = jobs
        self.mode = mode
        self.tasks: list[TaskRecord] = []
        self.scan_job = ""
        self.reassign_job = ""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)
        scroll.setWidget(content)
        outer.addWidget(scroll)
        layout.addWidget(
            page_header(
                f"Reasignación · {mode.value.title()}",
                "Busque notificaciones por fecha, marque las tareas y revise el destino antes de reasignar.",
            )
        )
        filters = QGroupBox("Búsqueda en correo")
        form = QFormLayout(filters)
        now = QDateTime.currentDateTime()
        self.start = QDateTimeEdit(now.addDays(-1))
        self.end = QDateTimeEdit(now)
        self.start.setDisplayFormat("dd/MM/yyyy")
        self.end.setDisplayFormat("dd/MM/yyyy")
        self.start.setCalendarPopup(True)
        self.end.setCalendarPopup(True)
        self.sender = QLineEdit(str(services.get_setting("servicios", "remitente_correo", "")))
        if mode == PurchaseMode.BIENES:
            self.sender.setText(str(services.get_setting("bienes", "remitente_reasignacion", "omar777j@gmail.com")))
        form.addRow("Desde", self.start)
        form.addRow("Hasta", self.end)
        form.addRow("Remitente", self.sender)
        layout.addWidget(filters)
        controls = QHBoxLayout()
        scan = QPushButton("Buscar correos")
        scan.clicked.connect(self.scan)
        controls.addWidget(scan)
        for label, state in (("Marcar todas", Qt.Checked), ("Desmarcar todas", Qt.Unchecked)):
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, value=state: self._mark_all(value))
            controls.addWidget(button)
        controls.addStretch(1)
        layout.addLayout(controls)
        self.count_label = QLabel("Busque correos para cargar el listado de tareas.")
        layout.addWidget(self.count_label)
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["Procesar", "Tarea", "Proveedor", "Remitente", "Asunto", "Fecha", "Resultado", "Reasignación a"])
        self.table.setMinimumHeight(240)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)
        execution = QGroupBox("Destino")
        exec_form = QFormLayout(execution)
        self.department = QLineEdit(str(services.get_setting("servicios", "servicios_departamento", "")))
        self.employee = QLineEdit(str(services.get_setting("servicios", "servicios_usuario", "")))
        self.comment = QLineEdit(str(services.get_setting("servicios", "servicios_reasignacion_msg", 'Taller Asignado "{proveedor}"')))
        self.headless = QCheckBox("Navegador oculto")
        self.headless.setChecked(ApplicationFacade._as_bool(services.get_setting("automation", "actua_headless", True)))
        exec_form.addRow("Departamento", self.department)
        exec_form.addRow("Empleado", self.employee)
        exec_form.addRow("Comentario", self.comment)
        exec_form.addRow("Ejecución", self.headless)
        layout.addWidget(execution)
        if mode == PurchaseMode.BIENES:
            execution.hide()
            layout.addWidget(QLabel("Bienes: destino por Configuración → Asignaciones. Se registra recepción, "
                                    "factura/ingreso y TRABAJO REALIZADO."))
            self.headless.setParent(content)
            layout.addWidget(self.headless)
        execute = QPushButton("Reasignar seleccionadas")
        execute.clicked.connect(self.execute)
        layout.addWidget(execute, 0, Qt.AlignLeft)
        self.panel = OperationPanel(jobs)
        self.panel.log.setMinimumHeight(70)
        self.panel.log.setMaximumHeight(100)
        layout.addWidget(self.panel)
        jobs.job_finished.connect(self._scanned)

    def _mark_all(self, state) -> None:
        for row in range(self.table.rowCount()):
            self.table.item(row, 0).setCheckState(state)

    def scan(self) -> None:
        if self.jobs.has_running_jobs():
            QMessageBox.information(self, "Reasignación", "Espere a que termine la operación en curso.")
            return
        start = self.start.dateTime().toPython().replace(hour=0, minute=0, second=0, microsecond=0)
        end = self.end.dateTime().toPython().replace(hour=23, minute=59, second=59, microsecond=999999)
        if start >= end:
            QMessageBox.warning(self, "Reasignación", "El rango de fechas no es válido.")
            return
        sender = self.sender.text()
        self.scan_job = self.jobs.submit(
            "scan",
            lambda progress, cancelled: self.services.scan_reassignment_mail(
                start,
                end,
                sender,
                self.mode,
                progress=progress,
                cancelled=cancelled,
            ),
        )
        self.panel.begin(self.scan_job, "Buscando correos y tareas…")

    def _scanned(self, job_id: str, result: object) -> None:
        if job_id == self.reassign_job and isinstance(result, OperationResult):
            by_task = {item.key: item for item in result.items}
            for row, task in enumerate(self.tasks):
                if task.task_number in by_task:
                    item = by_task[task.task_number]
                    self.table.setItem(row, 6, QTableWidgetItem(item.message))
                    if item.status.value == "succeeded":
                        self.table.item(row, 0).setCheckState(Qt.Unchecked)
            self.reassign_job = ""
            return
        if job_id != self.scan_job or not isinstance(result, list):
            return
        self.tasks = [item for item in result if isinstance(item, TaskRecord)]
        self.table.setRowCount(len(self.tasks))
        for row, task in enumerate(self.tasks):
            self.table.setItem(row, 0, _check_item(""))
            self.table.setItem(row, 1, QTableWidgetItem(task.task_number))
            self.table.setItem(row, 2, QTableWidgetItem(task.supplier))
            self.table.setItem(row, 3, QTableWidgetItem(str(task.payload.get("sender") or "")))
            self.table.setItem(row, 4, QTableWidgetItem(str(task.payload.get("subject") or "")))
            self.table.setItem(row, 5, QTableWidgetItem(str(task.payload.get("date") or "")))
            self.table.setItem(row, 6, QTableWidgetItem("Pendiente"))
            self.table.setItem(row, 7, QTableWidgetItem(str(task.payload.get("reasignacion", ""))))
        self.table.resizeColumnsToContents()
        for column in (2, 3, 4, 5):
            self.table.setColumnWidth(column, min(self.table.columnWidth(column), 260))
        self.count_label.setText(f"{len(self.tasks)} correos encontrados. Marque las tareas que desea reasignar.")
        self.scan_job = ""

    def execute(self) -> None:
        if self.jobs.has_running_jobs():
            QMessageBox.information(self, "Reasignación", "Espere a que termine la operación en curso.")
            return
        selected = [
            task
            for row, task in enumerate(self.tasks)
            if self.table.item(row, 0).checkState() == Qt.Checked
        ]
        if not selected:
            QMessageBox.warning(self, "Reasignación", "Seleccione al menos una tarea.")
            return
        if self.mode != PurchaseMode.BIENES and (not self.department.text().strip() or not self.employee.text().strip()):
            QMessageBox.warning(self, "Reasignación", "Complete departamento y empleado.")
            return
        unique = {}
        for task in selected:
            unique.setdefault(task.task_number, task)
        duplicate_count = len(selected) - len(unique)
        selected = list(unique.values())
        department, employee, comment = self.department.text().strip(), self.employee.text().strip(), self.comment.text()
        headless = self.headless.isChecked()
        if self.mode == PurchaseMode.BIENES:
            assignments = {item.subdepartment.strip().upper(): item for item in self.services.list_assignments()}
            destinations = []
            for task in selected:
                key = str(task.payload.get("reasignacion", "")).strip().upper()
                target = assignments.get(key)
                if target is None or not target.department or not target.person or not task.payload.get("details"):
                    QMessageBox.warning(self, "Asignaciones de Bienes", f"Revise el destino '{key}' y los datos de factura/ingreso de la tarea {task.task_number}.")
                    return
                destinations.append(f"{task.task_number}: {target.department} / {target.person}")
            employee = "los destinos del catálogo"
            department = "Bienes"
            comment = "SE RECIBE LA MERCADERIA; seguimientos de factura/ingreso; TRABAJO REALIZADO\n" + "\n".join(destinations)
        if QMessageBox.question(self, "Confirmar", f"¿Reasignar {len(selected)} tareas a {employee}, {department}?\n"
                               f"Se omitirán {duplicate_count} selecciones duplicadas.\nComentario: {comment}") != QMessageBox.Yes:
            return
        job_id = self.jobs.submit(
            "selenium",
            lambda progress, cancelled: self.services.reassign_tasks(
                selected,
                department,
                employee,
                comment,
                headless=headless,
                progress=progress,
                cancelled=cancelled,
            ),
        )
        self.reassign_job = job_id
        self.panel.begin(job_id, "Reasignando tareas…", completion_popup=True, completion_title="Reasignación")


class DownloadsPage(QWidget):
    def __init__(
        self,
        services: ApplicationFacade,
        jobs: JobManager,
        mode: PurchaseMode,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.services = services
        self.jobs = jobs
        self.mode = mode
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.scan_now)
        layout = QVBoxLayout(self)
        layout.addWidget(
            page_header(
                f"Descargas OC · {mode.value.title()}",
                "Descarga manual o desde correo. Un mensaje se registra como procesado solo al finalizar o clasificarse cada orden.",
            )
        )
        tabs = QTabWidget()
        tabs.addTab(self._normal_tab(), "Normal")
        tabs.addTab(self._supply_tab(), "Abastecimiento")
        from compras_tn.presentation.transfers_page import TransfersPage
        tabs.addTab(TransfersPage(services, jobs), "Telcodrive · Subidas")
        layout.addWidget(tabs)
        self.panel = OperationPanel(jobs)
        layout.addWidget(self.panel, 1)

    def _normal_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        form = QFormLayout()
        self.orders = QPlainTextEdit()
        self.orders.setMaximumHeight(100)
        self.orders.setPlaceholderText("OC manual, una por línea")
        self.normal_headless = QCheckBox("Navegador oculto")
        self.normal_headless.setChecked(ApplicationFacade._as_bool(self.services.get_setting("downloads", "headless", True)))
        form.addRow("Órdenes", self.orders)
        form.addRow("Ejecución", self.normal_headless)
        layout.addLayout(form)
        actions = QHBoxLayout()
        manual = QPushButton("Descargar manual")
        scan = QPushButton("Escanear correo ahora")
        self.schedule = QPushButton("Iniciar escaneo programado")
        scan.setProperty("secondary", True)
        self.schedule.setCheckable(True)
        self.schedule.setProperty("secondary", True)
        manual.clicked.connect(self.manual_download)
        scan.clicked.connect(self.scan_now)
        self.schedule.toggled.connect(self.toggle_schedule)
        actions.addWidget(manual)
        actions.addWidget(scan)
        actions.addWidget(self.schedule)
        actions.addStretch(1)
        layout.addLayout(actions)
        return tab

    def _supply_tab(self) -> QWidget:
        tab = QWidget()
        form = QFormLayout(tab)
        today = QDate.currentDate()
        self.supply_start = QDateEdit(today.addDays(-7))
        self.supply_end = QDateEdit(today)
        self.supply_start.setCalendarPopup(True)
        self.supply_end.setCalendarPopup(True)
        self.requester = QComboBox()
        self.authorizer = QComboBox()
        requesters = self.services.get_setting("downloads", "abastecimiento_solicitantes", [])
        authorizers = self.services.get_setting("downloads", "abastecimiento_autorizadores", [])
        self.requester.setEditable(True)
        self.authorizer.setEditable(True)
        self.requester.addItems(requesters if isinstance(requesters, list) else _tokens(str(requesters)))
        self.authorizer.addItem("")
        self.authorizer.lineEdit().setPlaceholderText("Sin filtro de autorizador")
        self.authorizer.addItems([value for value in (
            authorizers if isinstance(authorizers, list) else _tokens(str(authorizers))
        ) if str(value).strip()])
        self.supply_headless = QCheckBox("Navegador oculto")
        self.supply_headless.setChecked(
            ApplicationFacade._as_bool(self.services.get_setting("downloads", "abastecimiento_headless", True))
        )
        run = QPushButton("Descargar abastecimiento")
        run.clicked.connect(self.supply_download)
        form.addRow("Desde", self.supply_start)
        form.addRow("Hasta", self.supply_end)
        form.addRow("Solicitante", self.requester)
        form.addRow("Autorizador", self.authorizer)
        form.addRow("Ejecución", self.supply_headless)
        form.addRow(run)
        return tab

    def manual_download(self) -> None:
        numbers = _tokens(self.orders.toPlainText())
        if not numbers:
            QMessageBox.warning(self, "Descargas", "Ingrese al menos una OC.")
            return
        request = OperationRequest(
            kind="descarga_normal",
            mode=self.mode,
            items=[{"order_number": number} for number in numbers],
            options={"headless": self.normal_headless.isChecked(), "source": "manual"},
        )
        self._submit(request, "Descargando órdenes…")

    def scan_now(self) -> None:
        if self.panel.has_active_job():
            return
        job_id = self.jobs.submit(
            "scan_selenium",
            lambda progress, cancelled: self.services.scan_and_download_orders(
                self.mode,
                headless=self.normal_headless.isChecked(),
                progress=progress,
                cancelled=cancelled,
            ),
        )
        self.panel.begin(job_id, "Escaneando correo y descargando órdenes…", completion_popup=True, completion_title="Descargas OC")

    def toggle_schedule(self, enabled: bool) -> None:
        if enabled:
            seconds = max(60, int(self.services.get_setting("downloads", "scan_interval", 900)))
            self.timer.start(seconds * 1000)
            self.schedule.setText(f"Detener escaneo ({seconds}s)")
        else:
            self.timer.stop()
            self.schedule.setText("Iniciar escaneo programado")

    def stop_schedule(self) -> None:
        self.timer.stop()
        if self.schedule.isChecked():
            self.schedule.setChecked(False)

    def supply_download(self) -> None:
        if self.supply_start.date() > self.supply_end.date():
            QMessageBox.warning(self, "Abastecimiento", "El rango de fechas no es válido.")
            return
        request = OperationRequest(
            kind="descarga_abastecimiento",
            mode=self.mode,
            options={
                "start_date": self.supply_start.date().toString("dd/MM/yyyy"),
                "end_date": self.supply_end.date().toString("dd/MM/yyyy"),
                "requester": self.requester.currentText().strip(),
                "authorizer": self.authorizer.currentText().strip(),
                "headless": self.supply_headless.isChecked(),
                "download_folder": self.services.get_setting(
                    "downloads", "abastecimiento_carpeta_descarga", ""
                ),
            },
        )
        self._submit(request, "Descargando órdenes de abastecimiento…")

    def _submit(self, request: OperationRequest, message: str) -> None:
        job_id = self.jobs.submit(
            "selenium",
            lambda progress, cancelled: self.services.download_orders(
                request, progress=progress, cancelled=cancelled
            ),
        )
        self.panel.begin(job_id, message, completion_popup=True, completion_title="Descargas OC")
