from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from compras_tn.infrastructure.document_files import DEFAULT_ROOT, DEFAULT_TYPES


class DocumentTypeDialog(QDialog):
    def __init__(self, definition=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configurar tipo de documento")
        available = self.screen().availableGeometry()
        self.resize(min(640, int(available.width() * .9)), min(430, int(available.height() * .85)))
        values = definition or {}
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(values.get("name", ""))
        self.words = QLineEdit(", ".join(values.get("words", [])))
        form.addRow("Nombre:", self.name)
        form.addRow("Palabras del nombre:", self.words)
        layout.addLayout(form)
        advanced = QGroupBox("Opciones de archivos")
        advanced.setCheckable(True)
        advanced.setChecked(True)
        options = QWidget()
        fields = QFormLayout(options)
        self.extensions = QLineEdit(", ".join(values.get("extensions", [])))
        self.extensions.setPlaceholderText("Vacío: todos los formatos. Ejemplo: pdf, docx")
        self.copies = QComboBox()
        self.copies.addItem("Subir todos", "all")
        self.copies.addItem("Omitir copias idénticas; conservar la más reciente", "latest_identical")
        self.copies.setCurrentIndex(self.copies.findData(values.get("copies", "all")))
        self.comparison = QComboBox()
        self.comparison.addItem("Archivo exacto", "exact")
        self.comparison.addItem("Contenido leído del PDF (otros formatos: exacto)", "pdf_text")
        self.comparison.setCurrentIndex(self.comparison.findData(values.get("comparison", "exact")))
        for combo in (self.copies, self.comparison):
            combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(16)
        fields.addRow("Formatos:", self.extensions)
        fields.addRow("Copias:", self.copies)
        fields.addRow("Comparar:", self.comparison)
        box = QVBoxLayout(advanced)
        box.addWidget(options)
        advanced.toggled.connect(options.setVisible)
        layout.addWidget(advanced)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Guardar cambios")
        buttons.button(QDialogButtonBox.Cancel).setText("Cancelar")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def value(self):
        return dict(name=self.name.text(), words=self.words.text(),
                    extensions=[x.strip() for x in self.extensions.text().replace(";", ",").split(",") if x.strip()],
                    copies=self.copies.currentData(), comparison=self.comparison.currentData())


class FileSelectionWidget(QWidget):
    def __init__(self, values: dict, services=None, parent=None):
        super().__init__(parent)
        self.services = services
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.mode = QComboBox()
        self.mode.addItem("Elegir un archivo o usar una ruta / alias", "ruta")
        self.mode.addItem("Buscar documentos por tipo en la carpeta de la tarea", "tipos")
        self.mode.setCurrentIndex(1 if values.get("modo_archivo") == "tipos" else 0)
        layout.addWidget(self.mode)
        self.legacy = QWidget()
        row = QHBoxLayout(self.legacy)
        row.setContentsMargins(0, 0, 0, 0)
        self.path = QLineEdit(str(values.get("ruta", "@archivo_tarea")))
        browse = QPushButton("Elegir archivo")
        browse.clicked.connect(self.browse_file)
        row.addWidget(self.path, 1)
        row.addWidget(browse)
        layout.addWidget(self.legacy)
        self.typed = QWidget()
        typed = QVBoxLayout(self.typed)
        typed.setContentsMargins(0, 0, 0, 0)
        typed.addWidget(QLabel("Carpeta general (se incluyen sus subcarpetas):"))
        root_row = QHBoxLayout()
        configured = services.get_setting("automation", "actua_tareas_carpeta_base", "") if services else ""
        self.root = QLineEdit(str(values.get("carpeta_base") or configured or DEFAULT_ROOT))
        root_browse = QPushButton("Elegir carpeta")
        root_browse.clicked.connect(self.browse_root)
        root_row.addWidget(self.root, 1)
        root_row.addWidget(root_browse)
        typed.addLayout(root_row)
        typed.addWidget(QLabel("Marque los tipos. Se aplicarán sus opciones de copias y formatos:"))
        self.checks_box = QWidget()
        self.checks_layout = QVBoxLayout(self.checks_box)
        self.checks_layout.setContentsMargins(0, 0, 0, 0)
        typed.addWidget(self.checks_box)
        self.checks = {}
        self.refresh_types(set(values.get("tipos_archivo", ["cotizacion"])))
        add = QPushButton("Agregar tipo de documento")
        add.setProperty("secondary", True)
        add.setEnabled(services is not None)
        add.clicked.connect(self.add_type)
        typed.addWidget(add, 0, Qt.AlignLeft)
        note = QLabel("El flujo se ejecuta una sola vez por tarea; solo se repite la carga por cada archivo encontrado. Basta con encontrar uno de los tipos marcados. Si no aparece ninguno, esa tarea no inicia.")
        note.setWordWrap(True)
        typed.addWidget(note)
        layout.addWidget(self.typed)
        self.mode.currentIndexChanged.connect(self.update_mode)
        self.update_mode()

    def refresh_types(self, selected):
        while self.checks_layout.count():
            item = self.checks_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.checks = {}
        types = self.services.document_types() if self.services else DEFAULT_TYPES
        self.type_names = {d["id"]: d["name"] for d in types}
        for definition in types:
            row = QHBoxLayout()
            check = QCheckBox(definition["name"] + " — " + ", ".join(definition["words"]))
            check.setChecked(definition["id"] in selected)
            self.checks[definition["id"]] = check
            row.addWidget(check, 1)
            edit = QPushButton("Configurar")
            edit.setEnabled(self.services is not None)
            edit.clicked.connect(lambda _checked=False, d=definition: self.edit_type(d))
            row.addWidget(edit)
            holder = QWidget()
            holder.setLayout(row)
            self.checks_layout.addWidget(holder)

    def update_mode(self, *_args):
        typed = self.mode.currentData() == "tipos"
        self.typed.setVisible(typed)
        self.legacy.setVisible(not typed)

    def browse_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Elegir archivo", self.path.text())
        if path:
            self.path.setText(path)

    def browse_root(self):
        path = QFileDialog.getExistingDirectory(self, "Elegir carpeta general", self.root.text())
        if path:
            self.root.setText(path)

    def add_type(self):
        self.edit_type()

    def edit_type(self, current=None):
        dialog = DocumentTypeDialog(current, self)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            definition = self.services.add_document_type(**dialog.value(), identifier=current["id"] if current else "")
            selected = {key for key, check in self.checks.items() if check.isChecked()}
            self.refresh_types(selected | {definition["id"]})
        except ValueError as exc:
            QMessageBox.warning(self, "Tipo de documento", str(exc))

    def value(self):
        if self.mode.currentData() != "tipos":
            return {"ruta": self.path.text()}
        return {"modo_archivo": "tipos", "carpeta_base": self.root.text(), "tipos_archivo": [key for key, check in self.checks.items() if check.isChecked()], "tipos_nombres": [self.type_names[key] for key, check in self.checks.items() if check.isChecked()]}
