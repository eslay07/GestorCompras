from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from compras_tn.application.services import ApplicationFacade
from compras_tn.domain.models import OperationResult, PurchaseOrderDraft
from compras_tn.presentation.jobs import JobManager
from compras_tn.presentation.widgets import OperationPanel, page_header


class PurchaseOrderPreloadPage(QWidget):
    def __init__(
        self,
        services: ApplicationFacade,
        jobs: JobManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.services = services
        self.jobs = jobs
        self.drafts: list[PurchaseOrderDraft] = []
        self._rendering = False
        self.load_job = ""
        self.preload_job = ""
        self.recovery_job = ""
        self.state_job = ""
        layout = QVBoxLayout(self)
        layout.addWidget(
            page_header(
                "Carga de OC automática · Bienes",
                "Lee GENERAL, busca el sobrenombre de la columna E en la base local, usa su RUC "
                "y agrupa por RUC, departamento y solicitante exactos. Doble clic en una orden para revisar "
                "artículos, filas originales y observaciones.",
            )
        )
        actions = QHBoxLayout()
        load = QPushButton("Cargar y validar GENERAL")
        load.clicked.connect(self.load)
        select_all = QPushButton("Seleccionar válidas")
        select_all.setProperty("secondary", True)
        select_all.clicked.connect(lambda: self._set_all(True))
        clear_selection = QPushButton("Quitar selección")
        clear_selection.setProperty("secondary", True)
        clear_selection.clicked.connect(lambda: self._set_all(False))
        self.run_button = QPushButton("Precargar válidas y enviar informe")
        self.run_button.setEnabled(False)
        self.run_button.clicked.connect(self.preload)
        actions.addWidget(load)
        actions.addWidget(select_all)
        actions.addWidget(clear_selection)
        recover = QPushButton("Recuperar…")
        recover.clicked.connect(self.recover_pending)
        actions.addStretch(1)
        self.browser_visible = QCheckBox("Navegador visible")
        self.browser_visible.setChecked(
            bool(services.get_setting("automation", "oc_browser_visible", True))
        )
        actions.addWidget(self.browser_visible)
        layout.addLayout(actions)
        recovery_actions = QHBoxLayout()
        recovery_actions.addWidget(self.run_button)
        recovery_actions.addWidget(recover)
        recovery_actions.addStretch()
        layout.addLayout(recovery_actions)
        self.summary = QLabel("Cargue la hoja para revisar las órdenes antes de abrir NAF.")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.table = QTableWidget(0, 11)
        self.table.setHorizontalHeaderLabels(
            [
                "Cargar",
                "Tareas",
                "Proveedor",
                "RUC",
                "Solicitante NAF",
                "Artículos",
                "Subtotal",
                "Filas",
                "Estado",
                "Resultado NAF",
                "Departamento",
            ]
        )
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemChanged.connect(self._selection_changed)
        self.table.cellDoubleClicked.connect(self.show_detail)
        layout.addWidget(self.table, 1)
        self.panel = OperationPanel(jobs)
        layout.addWidget(self.panel)
        jobs.job_finished.connect(self._finished)
        jobs.job_failed.connect(self._failed)

    def recover_approvers(self):
        if self.panel.has_active_job():
            return
        headless = not self.browser_visible.isChecked()
        job = self.jobs.submit("selenium", lambda progress, cancelled: self.services.recover_approvers(
            headless=headless, progress=progress, cancelled=cancelled))
        self.panel.begin(job, "Recuperando aprobadores de órdenes existentes…", completion_popup=True)

    def load(self) -> None:
        if self.panel.has_active_job():
            return
        self.drafts = []
        self._render()
        self.run_button.setEnabled(False)
        self.load_job = self.jobs.submit(
            "default",
            lambda progress, cancelled: self.services.load_purchase_order_drafts(progress, cancelled),
        )
        self.panel.begin(
            self.load_job,
            "Leyendo y validando la hoja GENERAL…",
            completion_popup=True,
            completion_title="Validación de Google Sheets",
        )

    def preload(self) -> None:
        selected = self._selected_valid_drafts()
        blocked_drafts = [draft for draft in self.drafts if not draft.is_valid]
        blocked = len(blocked_drafts)
        if not self.drafts:
            QMessageBox.warning(self, "Carga de OC", "No existen órdenes para procesar.")
            return
        if not selected and not blocked_drafts:
            QMessageBox.warning(self, "Carga de OC", "Seleccione al menos una orden válida.")
            return
        tasks = len({draft.task_number for draft in selected})
        articles = sum(len(draft.articles) for draft in selected)
        subtotal = sum((draft.subtotal for draft in selected), start=0)
        if selected:
            browser_mode = "visible" if self.browser_visible.isChecked() else "oculto"
            message = (
                f"Se guardarán {len(selected)} órdenes seleccionadas de {tasks} tareas, "
                f"con {articles} artículos "
                f"y subtotal ${subtotal:.2f}.\n"
                f"Órdenes bloqueadas que solo irán al informe: {blocked}.\n\n"
                f"El navegador de NAF se ejecutará en modo {browser_mode}. "
                "Las observaciones mayores a 2000 caracteres se reparten por artículos en órdenes separadas, sin duplicar cantidades. Se guardará una vez cada orden, se enviará a aprobación y se consultarán sus aprobadores pendientes para GENERAL, columna O. ¿Continuar?"
            )
        else:
            message = (
                f"Las {blocked} órdenes están bloqueadas. No se abrirá NAF; se generará y enviará "
                "el informe de errores al usuario conectado. ¿Continuar?"
            )
        if QMessageBox.question(self, "Confirmar precarga de OC", message) != QMessageBox.Yes:
            return
        selected_ids = {id(draft) for draft in selected}
        for row, draft in enumerate(self.drafts):
            if draft.is_valid and id(draft) not in selected_ids:
                self.table.setItem(row, 9, QTableWidgetItem("No seleccionada"))
        drafts_to_process = [*selected, *blocked_drafts]
        headless = not self.browser_visible.isChecked()
        self.services.set_setting(
            "automation", "oc_browser_visible", self.browser_visible.isChecked()
        )
        self.preload_job = self.jobs.submit(
            "selenium",
            lambda progress, cancelled: self.services.preload_purchase_orders(
                drafts_to_process,
                headless=headless,
                progress=progress,
                cancelled=cancelled,
            ),
        )
        self.panel.begin(
            self.preload_job,
            "Precargando órdenes en NAF…",
            completion_popup=True,
            completion_title="Carga de OC automática",
        )

    def _finished(self, job_id: str, result: object) -> None:
        if job_id == self.state_job:
            self.state_job = ""
            self.table.setEnabled(True)
            if isinstance(result, list):
                self.drafts = result
            self._render()
            return
        if job_id == self.recovery_job:
            self.recovery_job = ""
            self.summary.setText('Recuperación terminada. Puede volver a cargar GENERAL.')
            return
        if job_id == self.load_job:
            self.load_job = ""
            if not isinstance(result, list):
                return
            self.drafts = [draft for draft in result if isinstance(draft, PurchaseOrderDraft)]
            self._render()
            return
        if job_id != self.preload_job or not isinstance(result, OperationResult):
            return
        self.preload_job = ""
        by_key = {item.key: item for item in result.items}
        for row, draft in enumerate(self.drafts):
            key = draft.operation_key
            item = by_key.get(key)
            if item is not None:
                requester = str(item.payload.get("requester") or "").strip()
                if requester:
                    self.table.setItem(row, 4, QTableWidgetItem(requester))
                self.table.setItem(row, 9, QTableWidgetItem(item.message))
                if item.payload.get("order_number"):
                    draft.validation_errors.append("OC guardada; recargue GENERAL. No volver a generar.")
                    choice = self.table.item(row, 0)
                    if choice is not None:
                        choice.setCheckState(Qt.Unchecked)
                        choice.setFlags(choice.flags() & ~Qt.ItemIsUserCheckable)
                    self.table.setItem(row, 8, QTableWidgetItem("OC guardada"))
                    state = self.table.cellWidget(row, 8)
                    if state:
                        state.blockSignals(True)
                        state.setCurrentIndex(1)
                        state.setToolTip('OC guardada')
                        state.setEnabled(False)
                        state.blockSignals(False)
        self._set_all(False)
        self.run_button.setEnabled(False)

    def _failed(self, job_id: str, _message: str) -> None:
        if job_id == self.state_job:
            self.state_job = ""
            self.table.setEnabled(True)
            self._render()
            self.summary.setText(_message)
        if job_id == self.recovery_job:
            self.recovery_job = ""
            self.summary.setText("Pendiente de sincronizar o recuperar: " + _message)
        if job_id == self.load_job:
            self.load_job = ""
        if job_id == self.preload_job:
            self.preload_job = ""

    def set_row_state(self, row, enabled):
        if self._rendering or self.panel.has_active_job():
            return
        draft = self.drafts[row]
        self.state_job = self.jobs.submit('default', lambda progress, cancelled:
            self.services.set_purchase_order_enabled(draft, enabled, progress, cancelled))
        self.panel.begin(self.state_job, 'Actualizando estado…')
        self.table.setEnabled(False)

    def recover_pending(self, selected=None):
        if self.panel.has_active_job():
            return
        dialog = QDialog(self)
        dialog.setWindowTitle('Recuperar tareas')
        dialog.resize(760, 360)
        layout = QVBoxLayout(dialog)
        kind = QComboBox()
        kind.addItems(['Órdenes pendientes', 'Aprobadores'])
        layout.addWidget(kind)
        table = QTableWidget(0, 5)
        table.setHorizontalHeaderLabels(['Seleccionar', 'Tareas', 'Proveedor', 'OC', 'Estado'])
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(table, 1)
        actions = QHBoxLayout()
        execute = QPushButton('Ejecutar')
        close = QPushButton('Cerrar')
        actions.addStretch()
        actions.addWidget(execute)
        actions.addWidget(close)
        layout.addLayout(actions)
        entries = []
        def refresh():
            entries[:] = (self.services.pending_oc_recoveries() if kind.currentIndex() == 0
                          else self.services.pending_approval_recoveries())
            table.setRowCount(len(entries))
            for row, receipt in enumerate(entries):
                draft = PurchaseOrderDraft.model_validate(receipt['draft'])
                checkbox = QTableWidgetItem('')
                checkbox.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
                checkbox.setCheckState(Qt.Unchecked)
                table.setItem(row, 0, checkbox)
                for column, value in enumerate([', '.join(draft.task_numbers), draft.supplier,
                    receipt.get('number') or ', '.join(receipt.get('candidates', [])) or 'Pendiente',
                    'Pendiente'], 1):
                    table.setItem(row, column, QTableWidgetItem(value))
            table.resizeColumnsToContents()
        def submit():
            chosen = [receipt for row, receipt in enumerate(entries)
                      if table.item(row, 0).checkState() == Qt.Checked]
            if not chosen:
                return
            if kind.currentIndex() == 0:
                callback = lambda progress, cancelled:self.services.recover_selected_orders(chosen, progress, cancelled)
                resource = 'default'
            else:
                callback = lambda progress, cancelled:self.services.recover_approvers(
                    keys=[receipt['key'] for receipt in chosen], headless=not self.browser_visible.isChecked(),
                    progress=progress, cancelled=cancelled)
                resource = 'selenium'
            self.recovery_job = self.jobs.submit(resource, callback)
            self.run_button.setEnabled(False)
            self.panel.begin(self.recovery_job, 'Recuperando tareas seleccionadas…')
            dialog.accept()
        kind.currentIndexChanged.connect(refresh)
        execute.clicked.connect(submit)
        close.clicked.connect(dialog.reject)
        refresh()
        dialog.exec()

    def _render(self) -> None:
        self._rendering = True
        self.table.setRowCount(len(self.drafts))
        for row, draft in enumerate(self.drafts):
            values = (
                ", ".join(draft.task_numbers),
                draft.supplier,
                draft.ruc or "Sin asociación",
                draft.requester,
                str(len(draft.articles)),
                f"${draft.subtotal:.2f}",
                ", ".join(str(number) for number in draft.source_rows),
                (f"Válida · Parte {draft.split_part}/{draft.split_total}" if draft.split_total > 1 else "Válida") if draft.is_valid else " · ".join(draft.validation_errors),
                "Pendiente" if draft.is_valid else "Bloqueada",
                draft.department,
            )
            choice = QTableWidgetItem("")
            if draft.is_valid:
                choice.setFlags(choice.flags() | Qt.ItemIsUserCheckable)
                choice.setCheckState(Qt.Checked)
            else:
                choice.setFlags(choice.flags() & ~Qt.ItemIsUserCheckable)
                choice.setCheckState(Qt.Unchecked)
            self.table.setItem(row, 0, choice)
            for column, value in enumerate(values, start=1):
                item = QTableWidgetItem(value)
                item.setToolTip(value + ("\nDoble clic para revisar y cambiar el estado del bloqueo." if column == 9 and not draft.is_valid else ""))
                self.table.setItem(row, column, item)
            state = QComboBox()
            state.addItems(['Lista', 'Bloqueada'])
            state.setCurrentIndex(0 if draft.is_valid else 1)
            state.setToolTip(' · '.join(draft.validation_errors))
            state.currentIndexChanged.connect(lambda index, current=row:self.set_row_state(current, index == 0))
            self.table.setCellWidget(row, 8, state)
        self.table.resizeColumnsToContents()
        for column in (2, 4, 7, 8, 9):
            self.table.setColumnWidth(column, min(self.table.columnWidth(column), 320))
        self._rendering = False
        self._update_summary()
        self.run_button.setEnabled(bool(self.drafts))

    def show_detail(self, row: int, _column: int) -> None:
        from compras_tn.infrastructure.automation.purchase_orders import build_observation
        draft = self.drafts[row]
        dialog = QDialog(self)
        dialog.setWindowTitle("Detalle de OC consolidada")
        dialog.resize(850, 650)
        layout = QVBoxLayout(dialog)
        content = QPlainTextEdit()
        content.setReadOnly(True)
        lines = ["ARTÍCULOS PARA NAF"]
        lines.extend(f"{a.code} | Cantidad {a.quantity} | Precio {a.unit_price}" for a in draft.articles)
        lines.append("\nFILAS ORIGINALES")
        lines.extend(f"Tarea {s.task_number} | Fila {a.source_row} | {a.code} | {a.quantity} | {a.unit_price} | {a.source_supplier or s.supplier_reference}"
                     for s in draft.original_drafts for a in s.articles)
        lines.extend(["\nOBSERVACIONES", build_observation(draft)])
        content.setPlainText("\n".join(lines))
        layout.addWidget(content)
        close = QPushButton("Cerrar")
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        dialog.exec()

    def _selected_valid_drafts(self) -> list[PurchaseOrderDraft]:
        return [
            draft
            for row, draft in enumerate(self.drafts)
            if draft.is_valid
            and self.table.item(row, 0) is not None
            and self.table.item(row, 0).checkState() == Qt.Checked
        ]

    def _set_all(self, checked: bool) -> None:
        for row, draft in enumerate(self.drafts):
            if draft.is_valid and self.table.item(row, 0) is not None:
                self.table.item(row, 0).setCheckState(
                    Qt.Checked if checked else Qt.Unchecked
                )
        self._update_summary()

    def _selection_changed(self, item: QTableWidgetItem) -> None:
        if not self._rendering and item.column() == 0:
            self._update_summary()

    def _update_summary(self) -> None:
        selected = self._selected_valid_drafts()
        valid = sum(draft.is_valid for draft in self.drafts)
        articles = sum(len(draft.articles) for draft in selected)
        subtotal = sum((draft.subtotal for draft in selected), start=0)
        self.summary.setText(
            f"{len(self.drafts)} órdenes detectadas: {valid} válidas y "
            f"{len(self.drafts) - valid} bloqueadas. Seleccionadas: {len(selected)}; "
            f"{articles} artículos; subtotal ${subtotal:.2f}."
        )
