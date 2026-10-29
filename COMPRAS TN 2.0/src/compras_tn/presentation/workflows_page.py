from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from compras_tn.application.task_orders import task_orders, normalize_orders
from compras_tn.presentation.task_orders_dialog import TaskOrdersDialog
from compras_tn.application.workflow_repair import repair_workflow
from compras_tn.application.services import ApplicationFacade
from compras_tn.application.workflows import (
    ACTION_DEFINITIONS,
    ACTION_REGISTRY,
    ActionDefinition,
    validate_workflow,
)
from compras_tn.domain.models import FlowStep, PurchaseMode, TaskRecord, WorkflowDefinition
from compras_tn.presentation.action_reference import OTHER_CONTROLS, REFERENCES, tooltip
from compras_tn.presentation.document_widgets import FileSelectionWidget
from compras_tn.presentation.jobs import JobManager
from compras_tn.presentation.widgets import OperationPanel, ReviewDialog, page_header


def step_data_text(step: FlowStep) -> str:
    if step.action_id == "ejecutar_flujo":
        return str(step.params.get("nombre", "Flujo")) + " · " + str(len(step.params.get("pasos", []))) + " pasos incluidos"
    if step.params.get("modo_archivo") == "tipos":
        return "Tipos: " + ", ".join(step.params.get("tipos_nombres") or step.params.get("tipos_archivo", [])) + " · Carpeta: " + str(step.params.get("carpeta_base", "Configuración"))
    definition = ACTION_REGISTRY.get(step.action_id)
    labels = {p.name: p.label for p in definition.parameters} if definition else {}
    return " · ".join(f"{labels.get(key, key)}: {value}" for key, value in step.params.items() if str(value or "").strip()) or "Sin datos adicionales"


def show_action_reference(definition: ActionDefinition, parent: QWidget, reference=None) -> None:
    dialog = QDialog(parent)
    dialog.setWindowTitle("Así se ve en Telcos · " + definition.label)
    dialog.resize(680, 380)
    layout = QVBoxLayout(dialog)
    title = QLabel(definition.label)
    title.setStyleSheet("font-size: 18px; font-weight: bold;")
    layout.addWidget(title)
    ref = reference or REFERENCES[definition.action_id]
    explanation = QLabel(definition.description + "\n\nDónde está: " + ref.location + "\n" + ref.note)
    explanation.setWordWrap(True)
    layout.addWidget(explanation)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    picture = QLabel()
    picture.setAlignment(Qt.AlignCenter)
    if ref.image and ref.path.is_file():
        pixmap = QPixmap(str(ref.path))
        # Muestra el recorte exacto, ampliado para facilitar su reconocimiento.
        if pixmap.width() < 160 and pixmap.height() < 80:
            pixmap = pixmap.scaled(pixmap.size() * 3, Qt.KeepAspectRatio, Qt.FastTransformation)
        picture.setPixmap(pixmap)
    else:
        picture.setText("Acción del orquestador\nNo tiene un símbolo propio en Telcos." if ref.internal else "Captura no disponible.")
    scroll.setWidget(picture)
    layout.addWidget(scroll, 1)
    source = QLabel("Captura real de Telcos · 13 de octubre de 2026")
    if ref.internal:
        source.setText("Esta acción se realiza dentro del orquestador.")
    layout.addWidget(source)
    close = QPushButton("Cerrar ayuda")
    close.clicked.connect(dialog.accept)
    layout.addWidget(close)
    dialog.exec()


def show_telcos_map(parent: QWidget) -> None:
    dialog = QDialog(parent)
    dialog.setWindowTitle("Mapa de controles de Tareas en Telcos")
    dialog.resize(760, 620)
    layout = QVBoxLayout(dialog)
    explanation = QLabel("Los botones cambian según el estado de la tarea.\nAsignada: Ejecutar. Aceptada: Pausar. Pausada: Reanudar.\nLas capturas muestran lo observado con esta cuenta en el módulo Tareas.")
    explanation.setWordWrap(True)
    layout.addWidget(explanation)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    content = QWidget()
    rows = QVBoxLayout(content)
    for heading, entries in (
        ("Acciones disponibles para crear flujos", [(d, REFERENCES[d.action_id]) for d in ACTION_DEFINITIONS]),
        ("Otros controles: se usan directamente en Telcos", [(ActionDefinition("", label, "", "Referencia visual del control."), ref) for label, ref in OTHER_CONTROLS]),
    ):
        title = QLabel(heading)
        title.setStyleSheet("font-weight: bold; font-size: 16px;")
        rows.addWidget(title)
        for definition, ref in entries:
            row = QHBoxLayout()
            label = QLabel(definition.label)
            label.setWordWrap(True)
            view = QPushButton("Ver símbolo" if not ref.internal else "Ver ayuda")
            view.setProperty("secondary", True)
            if ref.image:
                view.setIcon(QIcon(str(ref.path)))
                view.setIconSize(QSize(36, 28))
            view.clicked.connect(lambda _checked=False, d=definition, r=ref: show_action_reference(d, dialog, r))
            row.addWidget(label, 1)
            row.addWidget(view)
            rows.addLayout(row)
    scroll.setWidget(content)
    layout.addWidget(scroll, 1)
    close = QPushButton("Cerrar mapa")
    close.clicked.connect(dialog.accept)
    layout.addWidget(close)
    dialog.exec()


class StepDialog(QDialog):
    def __init__(
        self,
        definition: ActionDefinition,
        step: FlowStep | None = None,
        parent: QWidget | None = None,
        *, services=None,
    ):
        super().__init__(parent)
        self.definition = definition
        self.setWindowTitle(definition.label)
        self.resize(640, 300)
        available = self.screen().availableGeometry()
        self.resize(min(720, int(available.width() * .9)), min(560, int(available.height() * .85)))
        layout = QVBoxLayout(self)
        description = QLabel(definition.description)
        description.setWordWrap(True)
        layout.addWidget(description)
        reference = QPushButton("Ver símbolo o campo en Telcos")
        reference.setProperty("secondary", True)
        reference.clicked.connect(lambda: show_action_reference(definition, self))
        layout.addWidget(reference)
        form = QFormLayout()
        self.inputs: dict[str, QWidget] = {}
        values = step.params if step else {}
        for parameter in definition.parameters:
            value = values.get(parameter.name, parameter.default)
            if definition.action_id == "seleccionar_archivo" and parameter.name == "ruta":
                widget = FileSelectionWidget(values, services, self)
            elif parameter.kind == "choice":
                widget = QComboBox()
                widget.setEditable(parameter.name == "valor_o_label" or "{" in str(value or ""))
                widget.addItems(parameter.options)
                widget.setCurrentText(str(value or ""))
            elif parameter.name == "texto":
                widget = QPlainTextEdit(str(value or ""))
                widget.setMinimumHeight(100)
                widget.setPlaceholderText("Escriba aquí el texto que se guardará en Telcos")
            else:
                field = QLineEdit(str(value or ""))
                if parameter.kind == "file":
                    row = QWidget()
                    row_layout = QHBoxLayout(row)
                    row_layout.setContentsMargins(0, 0, 0, 0)
                    browse = QPushButton("Elegir…")
                    browse.setProperty("secondary", True)
                    browse.clicked.connect(lambda _checked=False, target=field: self._browse(target))
                    row_layout.addWidget(field, 1)
                    row_layout.addWidget(browse)
                    widget = row
                    self.inputs[parameter.name] = field
                    form.addRow(parameter.label, row)
                    continue
                widget = field
            self.inputs[parameter.name] = widget
            form.addRow(parameter.label, widget)
        if not definition.parameters:
            form.addRow(QLabel("Esta acción no necesita parámetros."))
        form_body = QWidget()
        form_body.setLayout(form)
        form_scroll = QScrollArea()
        form_scroll.setWidgetResizable(True)
        form_scroll.setWidget(form_body)
        layout.addWidget(form_scroll, 1)
        if "texto" in self.inputs:
            data_row = QHBoxLayout()
            data_row.addWidget(QLabel("Insertar un dato:"))
            data = QComboBox()
            data.addItem("Elija un dato para incluir en el texto…", "")
            for key, label in (("numero_tarea", "Número de tarea"), ("proveedor", "Proveedor (manual o importado)"),
                               ("orden_compra", "Orden de compra (manual o importada)"),
                               ("aprobadores", "Aprobadores pendientes de cada OC"),
                               ("telcos_tarea", "Nombre de tarea en Telcos"), ("telcos_estado", "Estado en Telcos"),
                               ("telcos_responsable", "Responsable en Telcos"), ("telcos_observacion", "Observación inicial en Telcos")):
                data.addItem(label, key)
            def insert_data(index):
                key = data.itemData(index)
                if key:
                    self.inputs["texto"].insertPlainText("{" + key + "}")
                    data.setCurrentIndex(0)
            data.activated.connect(insert_data)
            data_row.addWidget(data, 1)
            layout.addLayout(data_row)
            help_text = QLabel("Para usar datos de Telcos, agregue primero el paso Guardar datos de la tarea.")
            help_text.setWordWrap(True)
            layout.addWidget(help_text)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Agregar paso" if step is None else "Guardar cambios")
        buttons.button(QDialogButtonBox.Cancel).setText("Cancelar")
        buttons.accepted.connect(self._accept_valid)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept_valid(self) -> None:
        step = self.value()
        missing = [p.label for p in self.definition.parameters if p.required and not str(step.params.get(p.name, "")).strip()]
        if step.params.get("modo_archivo") == "tipos" and not step.params.get("tipos_archivo"):
            missing.append("Tipos de documentos")
        if missing:
            QMessageBox.warning(self, "Complete los datos", "Falta completar: " + ", ".join(missing))
            return
        self.accept()

    def _browse(self, field: QLineEdit) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Elegir archivo", field.text())
        if path:
            field.setText(path)

    def value(self) -> FlowStep:
        params: dict[str, Any] = {}
        for parameter in self.definition.parameters:
            widget = self.inputs[parameter.name]
            if isinstance(widget, FileSelectionWidget):
                params.update(widget.value())
                continue
            if isinstance(widget, QComboBox):
                value = widget.currentText()
            elif isinstance(widget, QPlainTextEdit):
                value = widget.toPlainText()
            else:
                value = widget.text()  # type: ignore[attr-defined]
            params[parameter.name] = value
        return FlowStep(action_id=self.definition.action_id, params=params)


class WorkflowEditor(QWidget):
    def __init__(
        self,
        services: ApplicationFacade,
        mode: PurchaseMode,
        changed: Callable[[], None],
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.services = services
        self.mode = mode
        self.changed = changed
        self.setStyleSheet("QListWidget, QLineEdit, QTableWidget { font-size: 14px; } QPushButton { min-height: 32px; }")
        self.current_id: int | None = None
        self.steps: list[FlowStep] = []
        layout = QVBoxLayout(self)
        workflow_row = QHBoxLayout()
        self.selector = QComboBox()
        self.name = QLineEdit()
        self.name.setPlaceholderText("Nombre del flujo")
        new = QPushButton("Nuevo")
        save = QPushButton("Guardar")
        delete = QPushButton("Eliminar")
        new.setProperty("secondary", True)
        delete.setProperty("danger", True)
        new.clicked.connect(self.new)
        save.clicked.connect(self.save)
        delete.clicked.connect(self.delete)
        self.selector.currentIndexChanged.connect(self.load_selected)
        workflow_row.addWidget(QLabel("Flujo:"))
        workflow_row.addWidget(self.selector, 1)
        workflow_row.addWidget(self.name, 1)
        workflow_row.addWidget(new)
        workflow_row.addWidget(save)
        workflow_row.addWidget(delete)
        layout.addLayout(workflow_row)
        policy_row = QHBoxLayout()
        policy_row.addWidget(QLabel("Si una tarea falla o queda activa:"))
        self.failure_policy = QComboBox()
        self.failure_policy.addItem("Detener el lote para revisar", True)
        self.failure_policy.addItem("Continuar con la siguiente tarea", False)
        self.failure_policy.setToolTip("Siempre una tarea a la vez. Continuar no pausa tareas automáticamente ni evita las restricciones de Telcos.")
        policy_row.addWidget(self.failure_policy, 1)
        layout.addLayout(policy_row)
        cycle_row = QHBoxLayout()
        cycle_row.addWidget(QLabel("Etapa del ciclo de compras:"))
        self.cycle_stage = QComboBox()
        self.cycle_stage.addItem("Reconocer por el nombre del flujo", 0)
        from compras_tn.application.task_cycle import STAGES
        for number in (5, 7, 9):
            self.cycle_stage.addItem(f"{number}. {STAGES[number]}", number)
        self.cycle_stage.addItem("Fuera del ciclo de compras", -1)
        self.cycle_stage.setToolTip("Solo genera advertencias si faltan etapas anteriores; no bloquea la tarea.")
        cycle_row.addWidget(self.cycle_stage, 1)
        layout.addLayout(cycle_row)
        presets = QHBoxLayout()
        self.preset = QComboBox()
        self.preset.addItems(['Observación', 'Seguimiento', 'Adjuntar archivo', 'Reasignación', 'Pausa', 'Iniciar y pausar', 'Consultar datos', 'Ver historial', 'Ver archivos'])
        guided = QPushButton('Crear con guía')
        guided.clicked.connect(self.create_guided)
        presets.addWidget(QLabel('Proceso guiado:'))
        presets.addWidget(self.preset)
        presets.addWidget(guided)
        telcos_map = QPushButton("Ver mapa de Telcos")
        telcos_map.setProperty("secondary", True)
        telcos_map.clicked.connect(lambda: show_telcos_map(self))
        presets.addWidget(telcos_map)
        repair = QPushButton("Revisar y reparar flujo")
        repair.clicked.connect(self.review_repair)
        layout.addLayout(presets)
        repair_row = QHBoxLayout()
        repair_row.addWidget(repair)
        repair_help = QLabel("Indica qué acción falta y dónde colocarla. Revise los cambios antes de guardar.")
        repair_help.setWordWrap(True)
        repair_row.addWidget(repair_help, 1)
        layout.addLayout(repair_row)
        splitter = QSplitter()
        actions_box = QGroupBox("Registro de acciones")
        actions_layout = QVBoxLayout(actions_box)
        self.actions = QListWidget()
        self.actions.setIconSize(QSize(36, 28))
        self.actions.setSpacing(3)
        self.actions.setMinimumWidth(350)
        self.action_search = QLineEdit()
        self.action_search.setPlaceholderText("Buscar acción: pausa, archivo…")
        self.action_search.setClearButtonEnabled(True)
        self.show_technical = QCheckBox("Mostrar opciones técnicas")
        self.action_search.textChanged.connect(self.populate_actions)
        self.show_technical.toggled.connect(self.populate_actions)
        actions_layout.addWidget(QLabel("1. Elija una acción.  2. Agregue el paso."))
        actions_layout.addWidget(self.action_search)
        actions_layout.addWidget(self.show_technical)
        self.actions.currentItemChanged.connect(self.describe_action)
        self.action_help = QLabel("Seleccione una acción. Use Ver símbolo para reconocerla en Telcos.")
        self.action_help.setWordWrap(True)
        self.action_help.setMinimumHeight(64)
        self.reference_button = QPushButton("Ver símbolo en Telcos")
        self.reference_button.setProperty("secondary", True)
        self.reference_button.setEnabled(False)
        self.reference_button.clicked.connect(self.view_selected_reference)
        self.populate_actions()
        add = QPushButton("Agregar paso →")
        add.clicked.connect(self.add_step)
        self.actions.doubleClicked.connect(lambda _index: self.add_step())
        actions_layout.addWidget(self.actions, 1)
        actions_layout.addWidget(self.action_help)
        actions_layout.addWidget(self.reference_button)
        actions_layout.addWidget(add)
        include = QPushButton("Agregar flujo existente como paso")
        include.clicked.connect(self.add_existing_flow)
        actions_layout.addWidget(include)
        steps_box = QGroupBox("Pasos del flujo")
        steps_layout = QVBoxLayout(steps_box)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Paso", "Qué hará", "Datos del paso"])
        self.table.setColumnWidth(0, 60)
        self.table.setColumnWidth(1, 250)
        self.table.setWordWrap(False)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.doubleClicked.connect(lambda _index: self.edit_step())
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setDefaultSectionSize(42)
        step_actions = QHBoxLayout()
        edit = QPushButton("Editar")
        up = QPushButton("Subir")
        down = QPushButton("Bajar")
        remove = QPushButton("Quitar")
        for button in (edit, up, down):
            button.setProperty("secondary", True)
        remove.setProperty("danger", True)
        edit.clicked.connect(self.edit_step)
        up.clicked.connect(lambda: self.move(-1))
        down.clicked.connect(lambda: self.move(1))
        remove.clicked.connect(self.remove_step)
        step_actions.addWidget(edit)
        step_actions.addWidget(up)
        step_actions.addWidget(down)
        step_actions.addWidget(remove)
        step_actions.addStretch(1)
        steps_layout.addWidget(self.table, 1)
        steps_layout.addLayout(step_actions)
        splitter.addWidget(actions_box)
        splitter.addWidget(steps_box)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([430, 850])
        layout.addWidget(splitter, 1)
        self.validation = QLabel()
        self.validation.setWordWrap(True)
        layout.addWidget(self.validation)
        self.refresh_flows()

    def populate_actions(self, *_args) -> None:
        selected = self.actions.currentItem()
        selected_id = selected.data(Qt.UserRole) if selected else None
        self.actions.clear()
        query = self.action_search.text().strip().casefold()
        technical = {"capturar_dato", "esperar_elemento", "definir_variable"}
        categories = dict.fromkeys(item.category for item in ACTION_DEFINITIONS)
        for category_name in categories:
            definitions = [d for d in ACTION_DEFINITIONS if d.category == category_name
                           and (self.show_technical.isChecked() or d.action_id not in technical)
                           and (not query or query in f"{d.label} {d.category} {d.description}".casefold())]
            if not definitions:
                continue
            category = QListWidgetItem(category_name)
            category.setFlags(Qt.NoItemFlags)
            font = category.font()
            font.setBold(True)
            category.setFont(font)
            self.actions.addItem(category)
            for definition in definitions:
                item = QListWidgetItem(definition.label)
                item.setData(Qt.UserRole, definition.action_id)
                item.setToolTip(tooltip(definition.action_id, definition.description))
                item.setSizeHint(QSize(320, 42))
                ref = REFERENCES[definition.action_id]
                if ref.image:
                    item.setIcon(QIcon(str(ref.path)))
                self.actions.addItem(item)
                if definition.action_id == selected_id:
                    self.actions.setCurrentItem(item)
        if self.actions.count() == 0:
            item = QListWidgetItem("No hay coincidencias. Pruebe otra palabra.")
            item.setFlags(Qt.NoItemFlags)
            self.actions.addItem(item)

    def describe_action(self, item, _previous=None) -> None:
        action_id = item.data(Qt.UserRole) if item else None
        self.reference_button.setEnabled(bool(action_id))
        if action_id:
            definition = ACTION_REGISTRY[action_id]
            ref = REFERENCES[action_id]
            self.action_help.setText(definition.description + "\n" + ref.location)
        else:
            self.action_help.setText("Seleccione una acción para ver su ayuda.")

    def view_selected_reference(self) -> None:
        item = self.actions.currentItem()
        if item and item.data(Qt.UserRole):
            show_action_reference(ACTION_REGISTRY[item.data(Qt.UserRole)], self)

    def refresh_flows(self, select_id: int | None = None) -> None:
        self.flows = self.services.list_workflows(self.mode.value)
        self.selector.blockSignals(True)
        self.selector.clear()
        self.selector.addItem("— Nuevo flujo —")
        for flow in self.flows:
            self.selector.addItem(flow.name)
        index = 0
        if select_id is not None:
            index = next((i + 1 for i, item in enumerate(self.flows) if item.id == select_id), 0)
        self.selector.setCurrentIndex(index)
        self.selector.blockSignals(False)
        self.load_selected(index)

    def create_guided(self):
        sequences = {
            'Observación': ['reanudar_tarea', 'ingresar_observacion', 'aceptar_observacion', 'cerrar_mensaje_ok'],
            'Seguimiento': ['abrir_seguimiento', 'escribir_seguimiento', 'guardar_seguimiento', 'cerrar_mensaje_ok'],
            'Adjuntar archivo': ['abrir_subida_archivo', 'seleccionar_archivo', 'subir_archivo', 'cerrar_mensaje_ok'],
            'Reasignación': ['abrir_reasignar', 'ingresar_departamento', 'ingresar_empleado',
                            'observacion_reasignacion', 'guardar_reasignacion', 'cerrar_mensaje_ok'],
            'Consultar datos': ['capturar_datos_tarea'],
            'Ver historial': ['ver_seguimiento', 'cerrar_panel'],
            'Ver archivos': ['ver_archivos', 'cerrar_panel'],
            'Pausa': ['pausar_tarea', 'motivo_pausa', 'aceptar_pausa', 'cerrar_mensaje_ok'],
            'Iniciar y pausar': ['reanudar_tarea', 'ingresar_observacion', 'aceptar_observacion', 'cerrar_mensaje_ok',
                      'pausar_tarea', 'motivo_pausa', 'aceptar_pausa', 'cerrar_mensaje_ok'],
        }
        name = self.preset.currentText()
        steps = [FlowStep(action_id=action) for action in
                 ['abrir_tareas_personales', 'ingresar_numero_tarea', 'consultar']]
        actions = sequences[name]
        if name in {'Seguimiento', 'Adjuntar archivo', 'Reasignación', 'Pausa'}:
            actions = ['reanudar_tarea', 'ingresar_observacion', 'aceptar_observacion', 'cerrar_mensaje_ok', *actions]
        elif name in {'Consultar datos', 'Ver historial', 'Ver archivos'}:
            steps.append(FlowStep(action_id='seleccionar_tarea'))
        for action in actions:
            definition = ACTION_REGISTRY[action]
            if definition.parameters:
                dialog = StepDialog(definition, parent=self, services=self.services)
                dialog.setWindowTitle(f'{name} · {definition.label}')
                if dialog.exec() != QDialog.Accepted:
                    return
                steps.append(dialog.value())
            else:
                steps.append(FlowStep(action_id=action))
        self.current_id = None
        self.name.setText(name)
        self.steps = steps
        self.render()

    def load_selected(self, index: int) -> None:
        if not 1 <= index <= len(self.flows):
            self.new()
            return
        flow = self.flows[index - 1]
        self.current_id = flow.id
        self.name.setText(flow.name)
        self.failure_policy.setCurrentIndex(0 if flow.stop_on_error else 1)
        stage = int(self.services.get_setting("workflow_cycle", str(flow.id), 0))
        self.cycle_stage.setCurrentIndex(max(0, self.cycle_stage.findData(stage)))
        self.steps = [step.model_copy(deep=True) for step in flow.steps]
        self.render()

    def new(self) -> None:
        self.current_id = None
        self.name.clear()
        self.failure_policy.setCurrentIndex(0)
        self.cycle_stage.setCurrentIndex(0)
        self.steps = []
        self.render()

    def add_existing_flow(self):
        from PySide6.QtWidgets import QInputDialog
        flows = [flow for flow in self.services.list_workflows(self.mode.value) if flow.id != self.current_id and flow.enabled]
        if not flows:
            QMessageBox.information(self, "Flujos", "Primero guarde otro flujo para poder incluirlo.")
            return
        labels = [f"{flow.name} (#{flow.id})" for flow in flows]
        label, accepted = QInputDialog.getItem(self, "Agregar flujo como paso", "Elija un flujo. Se incluye una copia de sus pasos actuales:", labels, 0, False)
        if accepted:
            flow = flows[labels.index(label)]
            self.steps.append(FlowStep(action_id="ejecutar_flujo", params={"nombre": flow.name, "flujo_id": flow.id, "pasos": [step.model_dump(mode="json") for step in flow.steps]}))
            self.render(len(self.steps) - 1)

    def add_step(self) -> None:
        item = self.actions.currentItem()
        action_id = str(item.data(Qt.UserRole) or "") if item else ""
        if not action_id:
            return
        definition = ACTION_REGISTRY[action_id]
        dialog = StepDialog(definition, parent=self, services=self.services)
        if dialog.exec() == QDialog.Accepted:
            self.steps.append(dialog.value())
            self.render(len(self.steps) - 1)

    def edit_step(self) -> None:
        row = self.table.currentRow()
        if not 0 <= row < len(self.steps):
            return
        step = self.steps[row]
        if step.action_id == "ejecutar_flujo":
            QMessageBox.information(self, "Flujo incluido", "Conserva una copia de los pasos. Para actualizarla, quite el paso y agregue nuevamente el flujo.")
            return
        dialog = StepDialog(ACTION_REGISTRY[step.action_id], step, self, services=self.services)
        if dialog.exec() == QDialog.Accepted:
            self.steps[row] = dialog.value()
            self.render(row)

    def move(self, delta: int) -> None:
        row = self.table.currentRow()
        target = row + delta
        if not (0 <= row < len(self.steps) and 0 <= target < len(self.steps)):
            return
        self.steps[row], self.steps[target] = self.steps[target], self.steps[row]
        self.render(target)

    def remove_step(self) -> None:
        row = self.table.currentRow()
        if 0 <= row < len(self.steps):
            self.steps.pop(row)
            self.render(min(row, len(self.steps) - 1))

    def render(self, selected: int = -1) -> None:
        self.table.setRowCount(len(self.steps))
        for row, step in enumerate(self.steps):
            definition = ACTION_REGISTRY.get(step.action_id)
            self.table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
            action_item = QTableWidgetItem(definition.label if definition else ("Flujo: " + step.params.get("nombre", "") if step.action_id == "ejecutar_flujo" else step.action_id))
            if definition:
                ref = REFERENCES[definition.action_id]
                if ref.image:
                    action_item.setIcon(QIcon(str(ref.path)))
                action_item.setToolTip(tooltip(definition.action_id, definition.description))
            self.table.setItem(row, 1, action_item)
            self.table.setItem(
                row,
                2,
                QTableWidgetItem(step_data_text(step)),
            )
        if selected >= 0:
            self.table.selectRow(selected)
        flow = self.value()
        errors = validate_workflow(flow)
        try:
            _, recommendations = repair_workflow(flow)
        except ValueError:
            recommendations = []
        if recommendations:
            errors.append("Revise la secuencia con «Revisar y reparar flujo».")
        self.validation.setObjectName("StatusError" if errors else "StatusSuccess")
        self.validation.setText("\n".join(errors) if errors else "Flujo válido.")

    def value(self) -> WorkflowDefinition:
        return WorkflowDefinition(
            id=self.current_id,
            name=self.name.text() or "Flujo sin nombre",
            mode=self.mode,
            steps=self.steps,
            stop_on_error=bool(self.failure_policy.currentData()),
        )

    def review_repair(self) -> None:
        try:
            proposal, advice = repair_workflow(self.value())
        except ValueError as exc:
            QMessageBox.warning(self, "Reparador de flujo", str(exc))
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Revisar y reparar flujo")
        dialog.resize(820, 540)
        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        problems = validate_workflow(proposal)
        text.setPlainText("\n\n".join(advice or ["No se detectaron correcciones de secuencia conocidas."])
            + ("\n\nPendiente de completar:\n" + "\n".join(problems) if problems else "")
            + "\n\nLa revisión no comprueba la conexión con Telcos. Un error de navegador desconectado requiere revisar la sesión."
            + "\n\nAplicar cambia el borrador. Revise los pasos y pulse Guardar. No ejecuta la tarea ni repite archivos enviados.")
        layout.addWidget(text)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Apply).setText("Aplicar al borrador")
        buttons.button(QDialogButtonBox.StandardButton.Apply).setEnabled(proposal.steps != self.steps)
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.steps = proposal.steps
            self.render()

    def save(self) -> None:
        flow = self.value()
        if not self.name.text().strip():
            QMessageBox.warning(self, "Flujos", "Escriba un nombre para el flujo.")
            return
        try:
            saved = self.services.save_workflow(flow)
            self.services.set_setting("workflow_cycle", str(saved.id), int(self.cycle_stage.currentData()))
        except Exception as exc:
            QMessageBox.critical(self, "Flujo inválido", str(exc))
            self.validation.setObjectName("StatusError")
            self.validation.setText(str(exc))
            return
        self.refresh_flows(saved.id)
        self.changed()
        QMessageBox.information(self, "Flujos", "Flujo guardado.")

    def delete(self) -> None:
        if self.current_id is None:
            return
        if QMessageBox.question(self, "Eliminar flujo", "¿Eliminar el flujo seleccionado?") != QMessageBox.Yes:
            return
        self.services.delete_workflow(self.current_id)
        self.refresh_flows()
        self.changed()


class AliasEditor(QWidget):
    def __init__(
        self,
        services: ApplicationFacade,
        changed: Callable[[], None],
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.services = services
        self.changed = changed
        layout = QVBoxLayout(self)
        text = QLabel(
            "Defina un alias por línea con el formato nombre=ruta. En los flujos se usa como @nombre. "
            "@archivo_tarea es un alias reservado que busca el archivo por el contexto de la tarea."
        )
        text.setWordWrap(True)
        layout.addWidget(text)
        self.aliases = QPlainTextEdit()
        layout.addWidget(self.aliases, 1)
        save = QPushButton("Guardar alias")
        save.clicked.connect(self.save)
        layout.addWidget(save, 0, Qt.AlignLeft)
        self.load()

    def load(self) -> None:
        settings = self.services.list_settings("automation")
        rows = [
            f"{key.split('::', 1)[1]}={value}"
            for key, value in sorted(settings.items())
            if key.startswith("actua_file_alias::") and value
        ]
        self.aliases.setPlainText("\n".join(rows))

    def save(self) -> None:
        parsed: dict[str, str] = {}
        errors: list[str] = []
        for number, line in enumerate(self.aliases.toPlainText().splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            if "=" not in line:
                errors.append(f"Línea {number}: falta '='.")
                continue
            alias, path = (part.strip() for part in line.split("=", 1))
            if not alias or alias == "archivo_tarea":
                errors.append(f"Línea {number}: alias inválido.")
            elif not path:
                errors.append(f"Línea {number}: falta la ruta.")
            elif "{" not in path and not Path(path).is_file():
                errors.append(f"Línea {number}: no existe el archivo indicado.")
            else:
                parsed[alias.casefold()] = path
        if errors:
            QMessageBox.warning(self, "Alias", "\n".join(errors))
            return
        previous = self.services.list_settings("automation")
        for key in previous:
            if key.startswith("actua_file_alias::"):
                self.services.set_setting("automation", key, "")
        for alias, path in parsed.items():
            self.services.set_setting("automation", f"actua_file_alias::{alias}", path)
        self.changed()
        QMessageBox.information(self, "Alias", "Alias guardados.")


class WorkflowRunner(QWidget):
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
        self._task_variants: dict[str, list[TaskRecord]] = {}
        self.mail_scan_job = ""
        self.oc_scan_job = ""
        self.execution_job = ""
        layout = QVBoxLayout(self)
        guide = QLabel('1. Seleccione tareas de la bandeja.  2. Elija el flujo creado en el editor. '
                       '3. Revise sus datos y archivos.  4. Confirme el resumen. '
                       '5. Consulte los resultados por tarea y paso. Una tarea finalizada puede no admitir cambios.')
        guide.setWordWrap(True)
        layout.addWidget(guide)
        controls = QHBoxLayout()
        self.workflow = QComboBox()
        self.source = QComboBox()
        self.source.addItems(["Todas", "manual", "correo", "reasignacion", "correos_masivos", "descargas"])
        self.source.addItem("Carga de OC automática", "carga_oc_automatica")
        self.source.currentIndexChanged.connect(lambda _index: self.refresh_approvers(force=True))
        refresh = QPushButton("Actualizar bandeja")
        import_mail = QPushButton("Importar correo (7 días)")
        refresh.setProperty("secondary", True)
        import_mail.setProperty("secondary", True)
        refresh.clicked.connect(lambda _checked=False: self.refresh_approvers(force=True))
        import_mail.clicked.connect(self.import_mail)
        controls.addWidget(QLabel("Flujo:"))
        controls.addWidget(self.workflow, 1)
        controls.addWidget(QLabel("Origen:"))
        controls.addWidget(self.source)
        layout.addLayout(controls)
        imports = QHBoxLayout()
        imports.addWidget(refresh)
        imports.addWidget(import_mail)
        update_oc = QPushButton("Sincronizar origen")
        update_oc.clicked.connect(self.import_oc)
        imports.addWidget(update_oc)
        imports.addStretch()
        layout.addLayout(imports)
        toggle_manual = QCheckBox("Ingreso manual")
        layout.addWidget(toggle_manual)
        manual_panel = QWidget()
        manual_layout = QVBoxLayout(manual_panel)
        manual = QHBoxLayout()
        manual_layout.addLayout(manual)
        self.manual = QPlainTextEdit()
        self.manual.setMaximumHeight(75)
        self.manual.setPlaceholderText("Una tarea por renglón\n164448987\n161516364")
        add = QPushButton("Agregar tareas")
        add.clicked.connect(self.add_manual)
        manual.addWidget(self.manual, 1)
        manual.addWidget(add)
        manual_layout.addWidget(QLabel("Después puede editar órdenes, proveedores y aprobadores desde las celdas de la tabla."))
        layout.addWidget(manual_panel)
        manual_panel.setVisible(False)
        toggle_manual.toggled.connect(manual_panel.setVisible)
        self.source.currentTextChanged.connect(lambda text: toggle_manual.setChecked(text == "manual"))
        self.table = QTableWidget(0, 6)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setHorizontalHeaderLabels(["Ejecutar", "Tarea", "Origen", "OC", "Proveedor", "Aprobadores"])
        self.table.cellDoubleClicked.connect(self.edit_task_orders)
        manual_help = QLabel("Ingreso manual: basta el número de tarea. Edite las OC, proveedores y aprobadores haciendo doble clic en sus celdas.\nPuede incluirlos en un paso con «Insertar un dato» al editar el flujo.")
        manual_help.setWordWrap(True)
        layout.addWidget(manual_help)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setMinimumHeight(180)
        self.table.verticalHeader().setDefaultSectionSize(38)
        layout.addWidget(self.table, 1)
        actions = QHBoxLayout()
        self.headless = QCheckBox("Navegador oculto")
        self.headless.setChecked(ApplicationFacade._as_bool(services.get_setting("automation", "actua_headless", True)))
        run = QPushButton("Ejecutar flujo")
        run.clicked.connect(self.execute)
        actions.addWidget(run)
        remove = QPushButton("Eliminar seleccionadas del listado")
        remove.clicked.connect(self.remove_selected)
        actions.addWidget(remove)
        actions.addWidget(self.headless)
        actions.addStretch(1)
        layout.addLayout(actions)
        self.panel = OperationPanel(jobs)
        self.panel.compact()
        layout.addWidget(self.panel)
        self.file_validation_job = ""
        self.approvers_job = ""
        jobs.job_failed.connect(self._files_validation_failed)
        jobs.job_finished.connect(self._files_validated)
        jobs.job_finished.connect(self._data_validated)
        jobs.job_finished.connect(self._mail_imported)
        jobs.job_finished.connect(self._execution_finished)
        jobs.job_failed.connect(self._execution_failed)
        jobs.job_failed.connect(self._oc_failed)
        jobs.job_finished.connect(self._approvers_ready)
        jobs.job_failed.connect(self._approvers_failed)
        self.refresh_workflows()
        self.refresh()

    def _execution_finished(self, job_id, result):
        if job_id == getattr(self, "data_validation_job", ""):
            self.data_validation_job = ""
        if job_id == self.execution_job:
            self.execution_job = ""
            self.refresh()

    def _execution_failed(self, job_id, message):
        self._execution_finished(job_id, None)

    def remove_selected(self) -> None:
        if self.jobs.has_running_jobs():
            QMessageBox.warning(self, "Bandeja", "Espere a que termine la operación en curso.")
            return
        selected = sorted({index.row() for index in self.table.selectionModel().selectedRows()})
        if not selected:
            QMessageBox.information(self, "Bandeja", "Seleccione filas con Ctrl o Shift para eliminarlas del listado.")
            return
        if QMessageBox.question(self, "Quitar tareas del listado", f"¿Eliminar {len(selected)} tareas seleccionadas del listado?") != QMessageBox.Yes:
            return
        variants = [
            variant
            for row in selected
            for variant in self._task_variants.get(
                self.tasks[row].task_number, [self.tasks[row]]
            )
        ]
        self.services.dismiss_tasks(variants)
        self.refresh()

    def refresh_workflows(self) -> None:
        selected_id = self.current_workflow().id if self.workflow.count() else None
        self.workflows = self.services.list_workflows(self.mode.value)
        self.workflow.clear()
        for flow in self.workflows:
            self.workflow.addItem(flow.name)
        if selected_id:
            index = next((i for i, item in enumerate(self.workflows) if item.id == selected_id), 0)
            self.workflow.setCurrentIndex(index)

    def current_workflow(self) -> WorkflowDefinition:
        index = self.workflow.currentIndex()
        if not 0 <= index < len(getattr(self, "workflows", [])):
            raise ValueError("Debe crear y seleccionar un flujo válido.")
        from compras_tn.application.workflows import expand_workflow
        return expand_workflow(self.workflows[index])

    def refresh_approvers(self, *, force=False):
        self.refresh()
        if self.panel.has_active_job() or self.jobs.has_running_jobs():
            return
        pending = [task for task in self.tasks if force or not task_orders(task)
                   or any(not order["approvers"] for order in task_orders(task))]
        if not pending:
            return
        self.approvers_job = self.jobs.submit("scan", lambda _p, _c: self.services.refresh_workflow_approvers(pending))
        self.panel.begin(self.approvers_job, "Actualizando aprobadores de las tareas en GENERAL…")

    def _approvers_ready(self, job_id, result):
        if job_id != self.approvers_job:
            return
        self.approvers_job = ""
        self.refresh()
        errors = list(dict.fromkeys(task.payload.get("approvers_sync_error", "") for task in result if task.payload.get("approvers_sync_error")))
        if errors:
            self.panel.status.setText("No se pudieron completar todos los aprobadores: " + " ".join(errors))
        else:
            missing = sum(not task_orders(task) or any(not order["approvers"] for order in task_orders(task)) for task in result)
            if missing:
                self.panel.status.setText(f"{missing} tareas todavía tienen aprobadores por completar en GENERAL (O) o en la tabla de órdenes.")

    def _approvers_failed(self, job_id, message):
        if job_id == self.approvers_job:
            self.approvers_job = ""

    def refresh(self) -> None:
        selections = {self.table.item(row, 1).text(): self.table.item(row, 0).checkState()
                      for row in range(self.table.rowCount())
                      if self.table.item(row, 1) and self.table.item(row, 0)}
        origin = self.source.currentData() or self.source.currentText()
        pending = self.services.list_pending_tasks(None if origin == "Todas" else origin)
        filtered = [
            task
            for task in pending
            if task.purchase_mode in {self.mode, PurchaseMode.GENERAL}
            and (origin == 'Todas' or task.origin == origin)
        ]
        self._task_variants = {}
        for task in filtered:
            number = task.task_number.strip()
            if number:
                self._task_variants.setdefault(number, []).append(task)
        self.tasks = [
            self._merge_task_variants(variants)
            for variants in self._task_variants.values()
        ]
        self.table.setRowCount(len(self.tasks))
        for row, task in enumerate(self.tasks):
            choice = QTableWidgetItem("")
            choice.setFlags(choice.flags() | Qt.ItemIsUserCheckable)
            choice.setCheckState(selections.get(task.task_number, Qt.Checked))
            self.table.setItem(row, 0, choice)
            self.table.setItem(row, 1, QTableWidgetItem(task.task_number))
            origins = " / ".join(
                dict.fromkeys(
                    "Carga de OC automática" if variant.origin == "carga_oc_automatica" else variant.origin
                    for variant in self._task_variants.get(task.task_number, [task])
                )
            )
            self.table.setItem(row, 2, QTableWidgetItem(origins))
            self.table.setItem(row, 3, QTableWidgetItem(task.order_number))
            self.table.setItem(row, 4, QTableWidgetItem(task.supplier))
            names = ", ".join(dict.fromkeys(name for order in task_orders(task) for name in order["approvers"]))
            self.table.setItem(row, 5, QTableWidgetItem(names or "Por completar"))
            for column in (3, 4, 5):
                item = self.table.item(row, column)
                item.setToolTip(item.text() + "\nDoble clic para editar todas las órdenes de esta tarea")
            if not names:
                self.table.item(row, 5).setToolTip("No hay aprobadores disponibles en la bandeja. Actualizar bandeja consulta GENERAL, columna O. Si siguen faltando, complete su captura en Carga de OC automática o ingréselos en la tabla de órdenes.")
        self.table.resizeColumnsToContents()

    def _merge_task_variants(self, variants: list[TaskRecord]) -> TaskRecord:
        best = max(
            variants,
            key=lambda task: (
                task.purchase_mode == self.mode,
                bool(task.order_number),
                bool(task.supplier),
                len(task.payload),
            ),
        )
        payload: dict[str, Any] = {}
        for task in variants:
            payload.update({
                key: value
                for key, value in task.payload.items()
                if value not in (None, "", [], {})
            })
        payload["origins"] = list(dict.fromkeys(task.origin for task in variants))
        edited = next((task for task in variants if task.payload.get("orders_edited")), None)
        orders = task_orders(edited) if edited else normalize_orders([order for task in variants for order in task_orders(task)])
        payload["orders"] = orders
        payload["order_numbers"] = [order["order_number"] for order in orders if order["order_number"]]
        payload["suppliers"] = list(dict.fromkeys(order["supplier"] for order in orders if order["supplier"]))
        order_number = ""
        supplier = ""
        return best.model_copy(
            update={
                "order_number": ", ".join(payload["order_numbers"]) or order_number,
                "supplier": ", ".join(payload["suppliers"]) or supplier,
                "payload": payload,
            }
        )

    def edit_task_orders(self, row, column):
        if column not in (3, 4, 5) or self.jobs.has_running_jobs():
            return
        task = self.tasks[row]
        suppliers = [supplier.name for supplier in self.services.list_suppliers()]
        dialog = TaskOrdersDialog(task.task_number, task_orders(task), suppliers, self)
        if dialog.exec() == QDialog.Accepted:
            self.services.update_task_orders(task, dialog.value())
            self.refresh()

    def add_manual(self) -> None:
        values = self.manual.toPlainText() if isinstance(self.manual, QPlainTextEdit) else self.manual.text()
        numbers = []
        for part in values.replace(",", "\n").replace(";", "\n").splitlines():
            number = part.strip()
            if number and number not in numbers:
                numbers.append(number)
        if not numbers:
            return
        invalid = [number for number in numbers if not re.fullmatch(r"[0-9]{1,14}", number)]
        if invalid:
            QMessageBox.warning(self, "Ingreso manual", "Corrija estas entradas (solo números, hasta 14 dígitos):\n" + "\n".join(invalid))
            return
        self.services.enqueue_tasks(
            [TaskRecord(task_number=number, origin="manual", purchase_mode=self.mode,
                        order_number="", supplier="") for number in numbers]
        )
        self.manual.clear()
        self.refresh()

    def import_mail(self) -> None:
        end = datetime.now().astimezone()
        start = end - timedelta(days=7)
        sender = str(self.services.get_setting("servicios", "remitente_correo", ""))
        self.mail_scan_job = self.jobs.submit(
            "scan",
            lambda _progress, _cancelled: self.services.scan_workflow_mail(
                start, end, sender, self.mode
            ),
        )
        self.panel.begin(self.mail_scan_job, "Buscando tareas en los correos de los últimos 7 días…")

    def import_oc(self) -> None:
        if self.panel.has_active_job():
            return
        origin = self.source.currentData() or self.source.currentText()
        label = self.source.currentText()
        self.oc_scan_job = self.jobs.submit("scan", lambda progress, cancelled:
            self.services.synchronize_workflow_origin(origin, self.mode, progress, cancelled))
        self.panel.begin(self.oc_scan_job, f"Sincronizando origen: {label}…", completion_popup=True)

    def _mail_imported(self, job_id: str, result: object) -> None:
        if job_id == self.oc_scan_job:
            self.oc_scan_job = ""
            self.refresh()
            return
        if job_id != self.mail_scan_job or not isinstance(result, list):
            return
        self.mail_scan_job = ""
        self.source.setCurrentText("correo")
        self.refresh()

    def _oc_failed(self, job_id: str, _message: str) -> None:
        if job_id == self.oc_scan_job:
            self.oc_scan_job = ""
            self.refresh()

    def execute(self) -> None:
        if self.panel.has_active_job():
            return
        selected = [
            task
            for row, task in enumerate(self.tasks)
            if self.table.item(row, 0).checkState() == Qt.Checked
        ]
        if not selected:
            QMessageBox.warning(self, "Orquestador Telcos", "Seleccione al menos una tarea.")
            return
        try:
            workflow = self.current_workflow()
            errors = validate_workflow(workflow)
            if errors:
                raise ValueError("\n".join(errors))
        except Exception as exc:
            QMessageBox.warning(self, "Orquestador Telcos", str(exc))
            return
        self._data_workflow = workflow.model_copy(deep=True)
        self.data_validation_job = self.jobs.submit("scan", lambda _p, _c: self.services.prepare_workflow_tasks(workflow, selected))
        self.panel.begin(self.data_validation_job, "Comprobando órdenes y aprobadores…")

    def _data_validated(self, job_id, result):
        if job_id != getattr(self, "data_validation_job", ""):
            return
        self.data_validation_job = ""
        prepared_by_number = {entry["task"].task_number: entry["task"] for entry in result}
        for row, task in enumerate(self.tasks):
            if task.task_number in prepared_by_number:
                self.tasks[row] = prepared_by_number[task.task_number]
                names = ", ".join(dict.fromkeys(name for order in task_orders(self.tasks[row]) for name in order["approvers"]))
                self.table.item(row, 5).setText(names)
        rejected = [entry for entry in result if entry["error"]]
        if rejected:
            QMessageBox.warning(self, "Complete los datos antes de ejecutar", "\n\n".join(entry["error"] for entry in rejected))
        selected = [entry["task"] for entry in result if not entry["error"]]
        if not selected:
            return
        workflow = self._data_workflow
        if any(step.action_id == "seleccionar_archivo" and step.params.get("modo_archivo") == "tipos" for step in workflow.steps):
            self._pending_file_workflow = workflow.model_copy(deep=True)
            self._validate_file_tasks(selected)
            return
        details = "\n".join(f"{i}. {ACTION_REGISTRY[step.action_id].label}: {step_data_text(step)}" for i, step in enumerate(workflow.steps, 1))
        dialog = ReviewDialog("Confirmar ejecución", f"Flujo: {workflow.name}. Revise las {len(selected)} tareas antes de ejecutar.", ["Tarea", "OC", "Proveedor", "Origen"], [(task.task_number, task.order_number, task.supplier, task.origin) for task in selected], "Ejecutar flujo", self, details)
        if dialog.exec() != QDialog.Accepted:
            return
        job_id = self.jobs.submit(
            "selenium",
            lambda progress, cancelled: self.services.execute_workflow(
                workflow,
                selected,
                headless=self.headless.isChecked(),
                progress=progress,
                cancelled=cancelled,
            ),
        )
        self.execution_job = job_id
        self.panel.begin(job_id, "Ejecutando flujo por lote…", completion_popup=True, completion_title="Orquestador Telcos")

    def _validate_file_tasks(self, tasks):
        workflow = self._pending_file_workflow
        self.file_validation_job = self.jobs.submit("scan", lambda progress, cancelled: self.services.prepare_workflow_files(workflow, tasks, progress, cancelled))
        self.panel.begin(self.file_validation_job, "Validando documentos antes de iniciar las tareas…")

    def _files_validation_failed(self, job_id, message):
        if job_id == self.file_validation_job:
            self.file_validation_job = ""
            QMessageBox.warning(self, "No se inició ningún flujo", message)

    def _files_validated(self, job_id, result):
        if job_id != self.file_validation_job or not isinstance(result, list):
            return
        self.file_validation_job = ""
        if self.jobs.state(job_id) == "cancelled":
            return
        choices = [r for r in result if r.get("choices")]
        if choices:
            dialog = QDialog(self)
            dialog.setWindowTitle("Elija la carpeta de cada tarea")
            dialog.resize(860, 250)
            layout = QVBoxLayout(dialog)
            layout.addWidget(QLabel("No se ha iniciado ninguna tarea. Seleccione la carpeta correcta:"))
            form = QFormLayout()
            selectors = []
            for row in choices:
                combo = QComboBox()
                combo.addItem("Seleccione una carpeta…", "")
                for path in row["choices"]:
                    combo.addItem(path, path)
                form.addRow("Tarea " + row["task"].task_number, combo)
                selectors.append((row, combo))
            layout.addLayout(form)
            buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            buttons.button(QDialogButtonBox.Ok).setText("Validar carpetas elegidas")
            buttons.button(QDialogButtonBox.Cancel).setText("Cancelar")
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            layout.addWidget(buttons)
            if dialog.exec() != QDialog.Accepted:
                return
            for row, combo in selectors:
                if not combo.currentData():
                    QMessageBox.warning(self, "Carpeta pendiente", "Seleccione una carpeta para cada tarea.")
                    return
                payload = dict(row["task"].payload)
                payload["document_folder_choices"] = {**payload.get("document_folder_choices", {}), str(row["step"]): combo.currentData()}
                row["task"] = row["task"].model_copy(update={"payload": payload})
            self._validate_file_tasks([r["task"] for r in result])
            return
        rejected = [r for r in result if r["error"]]
        if rejected:
            QMessageBox.warning(self, "Estas tareas no iniciarán", "\n\n".join(f"Tarea {r['task'].task_number}: {r['error']}" for r in rejected))
        valid = [r["task"] for r in result if not r["error"]]
        if not valid:
            return
        workflow = self._pending_file_workflow
        preview_rows = [(task.task_number, Path(file["path"]).name, file["path"]) for task in valid for manifest in task.payload["document_file_manifests"].values() for file in manifest["files"]]
        details = "\n".join(f"{i}. {ACTION_REGISTRY[step.action_id].label}: {step_data_text(step)}" for i, step in enumerate(workflow.steps, 1))
        omitted = [(task.task_number, file["path"], file["reason"], file["kept_path"])
                   for task in valid for manifest in task.payload["document_file_manifests"].values() for file in manifest.get("omitted", [])]
        if omitted:
            details += "\n\nCopias omitidas:\n" + "\n".join(f"Tarea {task}: {path} — {reason}. Conservado: {kept}" for task, path, reason, kept in omitted)
        dialog = ReviewDialog("Confirmar envío de archivos a Telcos", f"Flujo: {workflow.name}. Tareas: {len(valid)}. Archivos verificados: {len(preview_rows)}. Revise el listado antes de ejecutar.", ["Tarea", "Archivo", "Ruta del archivo"], preview_rows, "Ejecutar y enviar archivos", self, details)
        if dialog.exec() != QDialog.Accepted:
            return
        workflow = self._pending_file_workflow
        headless = self.headless.isChecked()
        job = self.jobs.submit("selenium", lambda progress, cancelled: self.services.execute_workflow(workflow, valid, headless=headless, progress=progress, cancelled=cancelled))
        self.execution_job = job
        self.panel.begin(job, "Ejecutando tareas con documentos verificados…", completion_popup=True, completion_title="Orquestador Telcos")


class WorkflowsPage(QWidget):
    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, lambda: self.runner.refresh_approvers(force=True))

    def __init__(
        self,
        services: ApplicationFacade,
        jobs: JobManager,
        mode: PurchaseMode,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.services = services
        self.mode = mode
        layout = QVBoxLayout(self)
        layout.addWidget(
            page_header(
                f"Orquestador Telcos · {mode.value.title()}",
                "Elija un proceso con guía, revise sus pasos y ejecútelo con el número de tarea. Puede reconocer cada acción con Ver símbolo.",
            )
        )
        tabs = QTabWidget()
        self.runner = WorkflowRunner(services, jobs, mode)
        self.editor = WorkflowEditor(services, mode, self.runner.refresh_workflows)
        self.aliases = AliasEditor(services, lambda: self.editor.render())
        tabs.addTab(self.runner, "Ejecutar")
        editor_scroll = QScrollArea()
        editor_scroll.setWidgetResizable(True)
        editor_scroll.setFrameShape(QScrollArea.NoFrame)
        editor_scroll.setWidget(self.editor)
        tabs.addTab(editor_scroll, "Editor visual")
        tabs.addTab(self.aliases, "Alias de archivos")
        layout.addWidget(tabs, 1)
