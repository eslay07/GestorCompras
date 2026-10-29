from __future__ import annotations

import json

from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from compras_tn.domain.models import ItemStatus, OperationItem, OperationResult
from compras_tn.presentation.widgets import OperationPanel


class TransfersPage(QWidget):
    def __init__(self, services, jobs):
        super().__init__()
        self.services, self.jobs = services, jobs
        self.queue = getattr(services.seafile, 'delivery', None)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('Los PDFs locales se conservan. Reintentar solo vuelve a subir; no descarga OCs.'))
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(['Tarea', 'Archivo local', 'Destino', 'Estado', 'Detalle'])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)
        actions = QHBoxLayout()
        for label, callback in [('Actualizar', self.refresh), ('Resolver tarea/destino', self.resolve),
                                ('Reintentar pendientes', self.retry)]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            actions.addWidget(button)
        layout.addLayout(actions)
        self.panel = OperationPanel(jobs)
        layout.addWidget(self.panel)
        jobs.job_finished.connect(lambda *_: self.refresh())
        self.refresh()

    def refresh(self):
        self.rows = self.queue.list(False) if self.queue else []
        self.table.setRowCount(len(self.rows))
        for i, row in enumerate(self.rows):
            for j, field in enumerate(('task_number', 'pdf_path', 'remote_dir', 'status', 'message')):
                self.table.setItem(i, j, QTableWidgetItem(str(row[field])))

    def resolve(self):
        if self.jobs.has_running_jobs():
            return
        index = self.table.currentRow()
        if index < 0:
            return
        row = self.rows[index]
        candidates = json.loads(row['candidates'])
        if candidates:
            chosen, ok = QInputDialog.getItem(self, 'Destino de tarea', 'Seleccione la carpeta:', candidates, 0, False)
            if ok:
                self.queue.update(row['id'], remote_dir=chosen, status='pending', message='Destino elegido')
        elif row['status'] == 'review':
            number, ok = QInputDialog.getText(self, 'Número de tarea', 'Número correcto del PDF:')
            if ok and number.isdigit() and 4 <= len(number) <= 14:
                self.queue.update(row['id'], task_number=number, remote_dir='', status='pending', message='Tarea revisada')
        else:
            QMessageBox.information(self, 'Revisión', 'Un archivo diferente con el mismo nombre no se sobrescribe. Revise el destino en Telcodrive antes de reintentar.')
        self.refresh()

    def retry(self):
        if not self.queue or self.panel.has_active_job():
            return
        credentials = self.services.credentials
        def run(progress, cancelled):
            rows = self.queue.retry(credentials, progress, cancelled)
            return OperationResult.from_items([
                OperationItem(key=str(row['id']), status=ItemStatus.SUCCEEDED if row['status'] in
                    {'uploaded', 'identical'} else ItemStatus.PENDING, message=row['message']) for row in rows
            ], 'Revisión de subidas finalizada')
        self.panel.begin(
            self.jobs.submit('selenium', run),
            'Verificando subidas pendientes…',
            completion_popup=True,
            completion_title='Telcodrive',
        )
