import pytest
from PIL import Image, ImageStat
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QDialogButtonBox, QPlainTextEdit

from compras_tn.application.workflows import ACTION_REGISTRY
from compras_tn.domain.models import PurchaseMode
from compras_tn.presentation.action_reference import REFERENCES
from compras_tn.presentation.workflows_page import StepDialog, WorkflowEditor


class Services:
    def list_workflows(self, _mode):
        return []


def test_every_action_has_an_honest_reference_and_nonblank_capture():
    assert set(REFERENCES) == set(ACTION_REGISTRY)
    for ref in REFERENCES.values():
        if ref.internal:
            assert not ref.image
        else:
            assert ref.path.is_file(), ref.path
            with Image.open(ref.path) as picture:
                assert min(picture.size) >= 18
                assert max(ImageStat.Stat(picture.convert("RGB")).stddev) > 10, ref.path


def test_search_grouping_and_keyboard_selection_keep_reference_help(qtbot):
    editor = WorkflowEditor(Services(), PurchaseMode.BIENES, lambda: None)
    qtbot.addWidget(editor)
    editor.action_search.setText("pausa")
    ids = [editor.actions.item(i).data(Qt.UserRole) for i in range(editor.actions.count())]
    assert "pausar_tarea" in ids
    assert "consultar" not in ids
    # Each category appears only once even when actions were added later to the registry.
    editor.action_search.clear()
    headings = [editor.actions.item(i).text() for i in range(editor.actions.count())
                if editor.actions.item(i).data(Qt.UserRole) is None]
    assert len(headings) == len(set(headings))
    for i in range(editor.actions.count()):
        if editor.actions.item(i).data(Qt.UserRole) == "capturar_datos_tarea":
            editor.actions.setCurrentRow(i)
            break
    assert editor.reference_button.isEnabled()
    assert "telcos_estado" in editor.action_help.text()
    editor.show_technical.setChecked(True)
    assert any(editor.actions.item(i).data(Qt.UserRole) == "capturar_dato"
               for i in range(editor.actions.count()))


def test_observation_data_picker_and_multiline_value(qtbot):
    dialog = StepDialog(ACTION_REGISTRY["ingresar_observacion"])
    qtbot.addWidget(dialog)
    field = dialog.inputs["texto"]
    assert isinstance(field, QPlainTextEdit)
    field.setPlainText("Responsable: ")
    field.moveCursor(field.textCursor().MoveOperation.End)
    picker = dialog.findChild(QComboBox)
    index = picker.findData("telcos_responsable")
    picker.activated.emit(index)
    assert dialog.value().params["texto"] == "Responsable: {telcos_responsable}"
    assert dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Save).text() == "Agregar paso"


@pytest.mark.parametrize("preset", ["Observación", "Adjuntar archivo", "Seguimiento", "Reasignación", "Pausa", "Iniciar y pausar"])
def test_mutating_guides_use_resume_observation_without_redundant_selection(qtbot, monkeypatch, preset):
    from types import SimpleNamespace

    from PySide6.QtWidgets import QDialog

    from compras_tn.domain.models import FlowStep, PurchaseMode
    from compras_tn.presentation import workflows_page
    class Dialog:
        def __init__(self, definition, **kwargs): self.definition = definition
        def setWindowTitle(self, value): pass
        def exec(self): return QDialog.Accepted
        def value(self): return FlowStep(action_id=self.definition.action_id, params={parameter.name: parameter.default or "Prueba" for parameter in self.definition.parameters})
    monkeypatch.setattr(workflows_page, "StepDialog", Dialog)
    editor = workflows_page.WorkflowEditor(SimpleNamespace(list_workflows=lambda *_args: []), PurchaseMode.BIENES, lambda: None)
    qtbot.addWidget(editor)
    editor.preset.setCurrentText(preset)
    editor.create_guided()
    actions = [step.action_id for step in editor.steps]
    assert actions[:7] == ["abrir_tareas_personales", "ingresar_numero_tarea", "consultar", "reanudar_tarea", "ingresar_observacion", "aceptar_observacion", "cerrar_mensaje_ok"]
    assert "seleccionar_tarea" not in actions and "capturar_datos_tarea" not in actions
