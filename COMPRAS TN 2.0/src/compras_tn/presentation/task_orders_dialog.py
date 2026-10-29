from __future__ import annotations

from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QHeaderView,
                              QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)
from compras_tn.application.task_orders import normalize_orders


class TaskOrdersDialog(QDialog):
    def __init__(self, task_number, rows, suppliers=(), parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Órdenes de la tarea {task_number}")
        available = self.screen().availableGeometry()
        self.resize(min(900, int(available.width() * .9)), min(540, int(available.height() * .85)))
        self.suppliers = list(suppliers)
        layout = QVBoxLayout(self)
        note = QLabel("Agregue una fila por orden. Los aprobadores se separan con comas. Guardar cambios conserva estos datos para el flujo.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["N.º de OC", "Proveedor", "Aprobadores pendientes"])
        self.table.setColumnWidth(0, 110)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        layout.addWidget(self.table, 1)
        for row in rows:
            self.add_row(row)
        if not rows:
            self.add_row()
        actions = QHBoxLayout()
        add = QPushButton("Agregar orden")
        add.clicked.connect(lambda: self.add_row())
        remove = QPushButton("Quitar fila")
        remove.clicked.connect(lambda: self.table.removeRow(self.table.currentRow()) if self.table.currentRow() >= 0 else None)
        actions.addWidget(add)
        actions.addWidget(remove)
        actions.addStretch()
        layout.addLayout(actions)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Guardar cambios")
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def add_row(self, value=None):
        value = value or {}
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(value.get("order_number", "")))
        supplier = QComboBox()
        supplier.setEditable(True)
        supplier.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        supplier.setMinimumContentsLength(8)
        supplier.addItem("")
        supplier.addItems(self.suppliers)
        supplier.setCurrentText(value.get("supplier", ""))
        self.table.setCellWidget(row, 1, supplier)
        self.table.setItem(row, 2, QTableWidgetItem(", ".join(value.get("approvers", []))))

    def value(self):
        return normalize_orders([dict(order_number=self.table.item(row, 0).text(),
            supplier=self.table.cellWidget(row, 1).currentText(), approvers=self.table.item(row, 2).text())
            for row in range(self.table.rowCount())])

    def save(self):
        try:
            self.value()
        except ValueError as exc:
            QMessageBox.warning(self, "Revise los datos", str(exc))
            return
        self.accept()
