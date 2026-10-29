from compras_tn.application.workflow_repair import repair_workflow
from compras_tn.domain.models import FlowStep, WorkflowDefinition, PurchaseMode


def flow(*actions):
    return WorkflowDefinition(name="Prueba", mode=PurchaseMode.BIENES,
        steps=[FlowStep(action_id=action, params={"texto": "Mi observación"} if action == "ingresar_observacion" else {}) for action in actions])


def test_missing_accept_and_confirmation_preserves_original():
    original = flow("ingresar_observacion", "abrir_subida_archivo")
    repaired, advice = repair_workflow(original)
    assert [s.action_id for s in repaired.steps] == ["ingresar_observacion", "aceptar_observacion", "cerrar_mensaje_ok", "abrir_subida_archivo"]
    assert len(original.steps) == 2
    assert repaired.steps[0].params == original.steps[0].params
    assert len(advice) == 3
    assert repair_workflow(repaired)[0].steps == repaired.steps


def test_wrong_pause_accept_replaced_without_losing_reason():
    original = flow("pausar_tarea", "motivo_pausa", "aceptar_observacion", "cerrar_mensaje_fin_tarea")
    original.steps[1].params = {"valor_o_label": "1642"}
    repaired, advice = repair_workflow(original)
    assert repaired.steps[2].action_id == "aceptar_pausa"
    assert repaired.steps[1].params == {"valor_o_label": "1642"}
    assert "paso 3" in advice[0]


def test_upload_confirm_only_once_and_incomplete_draft_never_committed():
    original = flow("subir_archivo", "cerrar_mensaje_ok", "abrir_seguimiento")
    assert repair_workflow(original)[0].steps == original.steps
    draft = flow("ingresar_observacion")
    repaired, advice = repair_workflow(draft)
    assert repaired.steps == draft.steps
    assert advice



def test_editor_repair_applies_only_to_draft(qtbot):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox
    from compras_tn.presentation.workflows_page import WorkflowEditor
    class Services:
        def list_workflows(self, mode): return []
    editor = WorkflowEditor(Services(), PurchaseMode.BIENES, lambda: None)
    qtbot.addWidget(editor)
    editor.steps = flow('ingresar_observacion', 'cerrar_mensaje_ok').steps
    editor.render()
    def apply():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, QDialog)
        button = dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Apply)
        assert button.isEnabled()
        button.click()
    QTimer.singleShot(50, apply)
    editor.review_repair()
    assert [step.action_id for step in editor.steps] == ['ingresar_observacion', 'aceptar_observacion', 'cerrar_mensaje_ok']
