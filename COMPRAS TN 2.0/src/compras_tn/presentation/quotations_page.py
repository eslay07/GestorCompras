from __future__ import annotations

import csv
import re
from datetime import datetime, time

from PySide6.QtCore import QDate, Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QCheckBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from compras_tn.infrastructure.document_files import DEFAULT_ROOT
from compras_tn.infrastructure.quotations import LOCAL_ZONE
from compras_tn.presentation.widgets import OperationPanel, ReviewDialog, page_header


class QuotationsPage(QWidget):
    def __init__(self, services, jobs, parent=None):
        super().__init__(parent)
        self.services, self.jobs = services, jobs
        self.rows = []
        self.scan_job = self.prepare_job = self.save_job = self.review_job = ""
        layout = QVBoxLayout(self)
        layout.addWidget(page_header("Organizador de archivos", "Busque correos, revise sus adjuntos y guarde los seleccionados en la carpeta de cada tarea."))
        root_row = QHBoxLayout()
        root_row.addWidget(QLabel("Carpeta general:"))
        self.root = QLineEdit(str(services.get_setting("quotations", "root", DEFAULT_ROOT)))
        browse = QPushButton("Elegir carpeta")
        browse.setProperty("secondary", True)
        browse.clicked.connect(self.choose_root)
        root_row.addWidget(self.root, 1)
        root_row.addWidget(browse)
        layout.addLayout(root_row)
        dates = QHBoxLayout()
        today = datetime.now(LOCAL_ZONE).date()
        self.start = QDateEdit(QDate(today.year, today.month, today.day))
        self.end = QDateEdit(QDate(today.year, today.month, today.day))
        for widget in (self.start, self.end):
            widget.setCalendarPopup(True)
            widget.setDisplayFormat("dd/MM/yyyy")
        scan = QPushButton("Escanear correo ahora")
        scan.clicked.connect(lambda: self.scan(False))
        dates.addWidget(QLabel("Desde:"))
        dates.addWidget(self.start)
        dates.addWidget(QLabel("Hasta:"))
        dates.addWidget(self.end)
        dates.addWidget(scan)
        local = QPushButton("Elegir archivos locales")
        local.clicked.connect(self.choose_local_files)
        dates.addWidget(local)
        dates.addStretch()
        layout.addLayout(dates)
        manual = QHBoxLayout()
        self.tasks = QPlainTextEdit()
        self.tasks.setMaximumHeight(60)
        self.tasks.setPlaceholderText("Buscar tareas concretas, una por línea. Ejemplo: 164404714")
        manual.addWidget(self.tasks, 1)
        find = QPushButton("Buscar estas tareas")
        find.clicked.connect(lambda: self.scan(True))
        manual.addWidget(find)
        manual_toggle = QCheckBox("Ingreso manual · Buscar tareas concretas")
        manual_body = QWidget()
        manual_body.setLayout(manual)
        manual_body.setVisible(False)
        manual_toggle.toggled.connect(manual_body.setVisible)
        layout.addWidget(manual_toggle)
        layout.addWidget(manual_body)
        note = QLabel("Solo se incluyen solicitudes de cotización de proveedores registrados. La búsqueda manual también revisa correos antiguos y procesados. También puede elegir varios archivos locales; revise su tarea, proveedor y tipo antes de guardar. Nada se guarda en la carpeta general hasta confirmar Guardar seleccionados.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(["Guardar", "Tarea", "Proveedor", "Fecha", "Archivo original", "Tipo", "Proyecto", "Carpeta de destino", "Estado"])
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(44)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setMinimumHeight(180)
        layout.addWidget(self.table, 1)
        actions = QHBoxLayout()
        self.save_button = QPushButton("Guardar seleccionados")
        self.save_button.clicked.connect(self.prepare)
        export = QPushButton("Exportar reporte CSV")
        export.setProperty("secondary", True)
        export.clicked.connect(self.export)
        self.lookup_button = QPushButton("Consultar datos de todos los archivos")
        self.lookup_button.clicked.connect(self.review_local_tasks)
        actions.addWidget(self.lookup_button)
        actions.addWidget(self.save_button)
        actions.addWidget(export)
        select_all = QPushButton("Seleccionar todos")
        clear_all = QPushButton("Quitar selección")
        select_all.setProperty("secondary", True)
        clear_all.setProperty("secondary", True)
        select_all.clicked.connect(lambda: self.set_all_selected(True))
        clear_all.clicked.connect(lambda: self.set_all_selected(False))
        actions.addWidget(select_all)
        actions.addWidget(clear_all)
        actions.addStretch()
        layout.addLayout(actions)
        self.panel = OperationPanel(jobs)
        self.panel.compact()
        layout.addWidget(self.panel)
        jobs.job_finished.connect(self.finished)
        jobs.job_failed.connect(self.failed)

    def showEvent(self, event):
        super().showEvent(event)
        today = datetime.now(LOCAL_ZONE).date()
        for widget in (self.start, self.end):
            widget.setDate(QDate(today.year, today.month, today.day))

    def choose_local_files(self):
        if self.panel.has_active_job():
            return
        paths, _ = QFileDialog.getOpenFileNames(self, "Seleccionar archivos para organizar", "", "Todos los archivos (*)")
        if not paths:
            return
        self.services.set_setting("quotations", "root", self.root.text().strip())
        self.scan_job = self.jobs.submit("scan", lambda progress, cancelled: self.services.scan_local_quotations(paths, progress, cancelled))
        self.panel.begin(self.scan_job, "Identificando archivos locales…")
        self.table.setEnabled(False)
        self.root.setEnabled(False)

    def choose_root(self):
        path = QFileDialog.getExistingDirectory(self, "Carpeta de cotizaciones", self.root.text())
        if path:
            self.root.setText(path)

    def scan(self, manual):
        if self.panel.has_active_job():
            return
        tasks = list(dict.fromkeys(n for n in re.split(r"[\s,;]+", self.tasks.toPlainText().strip()) if n)) if manual else []
        if manual and (not tasks or any(not re.fullmatch(r"[0-9]{6,14}", n) for n in tasks)):
            QMessageBox.warning(self, "Revise las tareas", "Ingrese uno o varios números de tarea válidos, separados por líneas.")
            return
        start = datetime.combine(self.start.date().toPython(), time.min, LOCAL_ZONE)
        end = datetime.combine(self.end.date().toPython(), time.max, LOCAL_ZONE)
        if not manual and start > end:
            QMessageBox.warning(self, "Fechas", "La fecha inicial debe ser anterior a la final.")
            return
        self.services.set_setting("quotations", "root", self.root.text().strip())
        self.scan_job = self.jobs.submit("scan", lambda progress, cancelled: self.services.scan_quotations(start, end, tasks, progress, cancelled))
        self.panel.begin(self.scan_job, "Buscando adjuntos para revisar…")
        self.table.setEnabled(False)
        self.root.setEnabled(False)

    def render(self):
        types = self.services.document_types()
        self.table.setRowCount(len(self.rows))
        for index, row in enumerate(self.rows):
            choice = QTableWidgetItem("")
            choice.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            choice.setCheckState(Qt.Checked if not row.get("error") and row.get("status") != "Ya guardado" else Qt.Unchecked)
            self.table.setItem(index, 0, choice)
            data = [row.get("task_number", ""), row.get("supplier", ""), row.get("received", "")[:16].replace("T", " "), row["original_name"], "", row.get("project", ""), row.get("planned_folder", ""), row.get("error") or row.get("status", "")]
            for column, value in enumerate(data, 1):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                if column != 2:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(index, column, item)
            if row.get("source") == "local":
                task_input = QLineEdit(row.get("task_number", ""))
                task_input.setPlaceholderText("Escriba la tarea")
                task_input.setToolTip("Escriba las tareas de todos los archivos y pulse Consultar datos de todos los archivos.")
                self.table.setCellWidget(index, 1, task_input)
            elif row.get("ambiguous_subject"):
                task_choice = QComboBox()
                task_choice.addItem("Elija una tarea…", "")
                for number in row["task_candidates"]:
                    task_choice.addItem(number, number)
                self.table.setCellWidget(index, 1, task_choice)
            else:
                self.table.removeCellWidget(index, 1)
            kind = QComboBox()
            for definition in types:
                kind.addItem(definition["name"], definition["id"])
            kind.setCurrentIndex(max(0, kind.findData(row["type_id"])))
            self.table.setCellWidget(index, 5, kind)
            if row.get("folder_candidates"):
                folder = QComboBox()
                folder.addItem("Elija una carpeta…", "")
                for path in row["folder_candidates"]:
                    folder.addItem(path, path)
                self.table.setCellWidget(index, 7, folder)
            else:
                self.table.removeCellWidget(index, 7)
        self.fit_columns()

    def fit_columns(self):
        weights = (75, 95, 150, 120, 180, 130, 150, 170, 155)
        available = max(450, self.table.viewport().width() - 4)
        for column, weight in enumerate(weights):
            self.table.setColumnWidth(column, max(40, int(available * weight / sum(weights))))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self.fit_columns)

    def reviewed_row(self, index):
        original = self.rows[index]
        row = dict(original)
        row["supplier"] = self.table.item(index, 2).text().strip()
        if row["supplier"] != original.get("supplier"):
            row["supplier_confirmed"] = True
        row["type_id"] = self.table.cellWidget(index, 5).currentData()
        task = self.table.cellWidget(index, 1)
        if task:
            row["task_number"] = task.text().strip() if isinstance(task, QLineEdit) else task.currentData()
            row["ambiguous_subject"] = not bool(row["task_number"])
        changed_task = row.get('source') == 'local' and row.get('task_number') != original.get('task_number')
        if changed_task:
            row['planned_folder'] = ''
            row.pop('chosen_folder', None)
            row.pop('planned_path', None)
        folder = self.table.cellWidget(index, 7)
        if folder and not changed_task:
            row["chosen_folder"] = folder.currentData()
            row["planned_folder"] = ""
        return row

    def review_local_tasks(self):
        if self.panel.has_active_job():
            return
        rows = [self.reviewed_row(index) for index, row in enumerate(self.rows) if row.get('source') == 'local']
        if not rows:
            QMessageBox.information(self, "Archivos locales", "Primero cargue los archivos locales y escriba sus tareas en la tabla.")
            return
        self.services.set_setting("quotations", "root", self.root.text().strip())
        self.review_job = self.jobs.submit("scan", lambda progress, cancelled:
            self.services.review_local_quotation_tasks(rows, progress, cancelled))
        self.panel.begin(self.review_job, "Consultando datos de todos los archivos en un lote…")
        self.table.setEnabled(False)
        self.root.setEnabled(False)

    def set_all_selected(self, selected):
        if not self.table.isEnabled():
            return
        for index in range(self.table.rowCount()):
            self.table.item(index, 0).setCheckState(Qt.Checked if selected else Qt.Unchecked)

    def selected_rows(self):
        return [self.reviewed_row(index) for index in range(len(self.rows)) if self.table.item(index, 0).checkState() == Qt.Checked]

    def prepare(self):
        if self.panel.has_active_job():
            return
        rows = self.selected_rows()
        if not rows:
            QMessageBox.information(self, "Seleccione archivos", "Marque los adjuntos que desea guardar.")
            return
        self.services.set_setting("quotations", "root", self.root.text().strip())
        self.prepare_job = self.jobs.submit("scan", lambda _progress, _cancelled: self.services.prepare_quotation_save(rows))
        self.panel.begin(self.prepare_job, "Verificando GENERAL y destinos seleccionados…")
        self.table.setEnabled(False)
        self.root.setEnabled(False)

    def finished(self, job_id, result):
        if job_id not in {self.scan_job, self.prepare_job, self.save_job, self.review_job}:
            return
        self.table.setEnabled(True)
        self.root.setEnabled(True)
        if job_id == self.review_job:
            self.review_job = ""
            if self.jobs.state(job_id) == "cancelled":
                return
            updated = {row['identity']: row for row in result}
            self.rows = [updated.get(row['identity'], row) for row in self.rows]
            self.render()
            return
        if job_id == self.prepare_job:
            self.prepare_job = ""
            if self.jobs.state(job_id) == "cancelled":
                return
            updated = {r["identity"]: r for r in result}
            for index, row in enumerate(self.rows):
                if row["identity"] in updated:
                    self.rows[index] = updated[row["identity"]]
                    for column, key in ((6, "project"), (7, "planned_folder"), (8, "status")):
                        self.table.item(index, column).setText(str(self.rows[index].get(key, "")))
            types = {item["id"]: item["name"] for item in self.services.document_types()}
            preview_rows = [(r["task_number"], r["supplier"], types[r["type_id"]], r["original_name"], r["planned_name"], r["planned_folder"], r.get("status", "")) for r in result]
            dialog = ReviewDialog("Confirmar guardado de archivos", f"Archivos seleccionados: {len(result)}. Revise los nombres y destinos. Las carpetas faltantes se crearán en el mes actual al guardar; se conservarán las versiones anteriores.", ["Tarea", "Proveedor", "Tipo", "Archivo original", "Nombre final", "Carpeta de destino", "Estado"], preview_rows, f"Guardar {len(result)} archivos", self)
            if dialog.exec() != QDialog.Accepted:
                return
            self.save_job = self.jobs.submit("scan", lambda progress, cancelled: self.services.save_quotations(result, progress, cancelled))
            self.panel.begin(self.save_job, "Guardando documentos seleccionados…")
            self.table.setEnabled(False)
            self.root.setEnabled(False)
            return
        if job_id == self.scan_job:
            self.scan_job = ""
            self.rows = result
            if not result:
                QMessageBox.information(self, "Búsqueda terminada", "No se encontraron adjuntos para los criterios elegidos.")
        else:
            self.save_job = ""
            by_identity = {r["identity"]: r for r in result}
            self.rows = [by_identity.get(r["identity"], r) for r in self.rows]
            errors = [r for r in result if r.get("error")]
            QMessageBox.information(self, "Resultado del guardado", f"Revisados: {len(result)}. Con error: {len(errors)}. Consulte el estado de cada archivo.")
        self.render()

    def failed(self, job_id, message):
        if job_id in {self.scan_job, self.prepare_job, self.save_job, self.review_job}:
            self.scan_job = self.prepare_job = self.save_job = self.review_job = ""
            self.table.setEnabled(True)
            self.root.setEnabled(True)
            QMessageBox.warning(self, "Organizador de archivos", message)

    def export(self):
        if not self.rows:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Guardar reporte", "cotizaciones.csv", "CSV (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as stream:
                writer = csv.writer(stream)
                writer.writerow(["Tarea", "Proveedor", "Fecha", "Archivo original", "Tipo", "Proyecto", "Destino", "Estado"])
                for index in range(len(self.rows)):
                    row = self.reviewed_row(index)
                    row["type_id"] = next(t["name"] for t in self.services.document_types() if t["id"] == row["type_id"])
                    row["saved_path"] = row.get("saved_path") or row.get("planned_folder", "")
                    values = [row.get(k, "") for k in ("task_number", "supplier", "received", "original_name", "type_id", "project", "saved_path", "status")]
                    writer.writerow(["'" + str(v) if str(v).startswith(("=", "+", "-", "@")) else v for v in values])
        except OSError as exc:
            QMessageBox.warning(self, "Reporte", str(exc))
