from __future__ import annotations

from typing import Any

import pytest

from compras_tn.application.workflows import (
    ACTION_REGISTRY,
    IRREVERSIBLE_ACTIONS,
    PAUSE_REASONS,
    WorkflowEngine,
    WorkflowExecutionError,
    resolve_value,
    validate_workflow,
)
from compras_tn.domain.models import (
    FlowStep,
    ItemStatus,
    JobStatus,
    OperationItem,
    OperationResult,
    PurchaseMode,
    Supplier,
    TaskRecord,
    WorkflowDefinition,
)


class RecordingExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def execute(self, action_id: str, params: dict[str, Any], context: dict[str, Any]) -> None:
        self.calls.append((action_id, params))
        if action_id == "definir_variable":
            context[str(params["nombre"])] = params["valor"]


def test_ruc_is_preserved_as_text() -> None:
    supplier = Supplier(name="Proveedor", ruc="0012345678901", email_primary="a@b.ec")
    assert supplier.ruc == "0012345678901"


def test_operation_result_classifies_success_partial_and_failure() -> None:
    success = OperationItem(key="1", status=ItemStatus.SUCCEEDED)
    failure = OperationItem(key="2", status=ItemStatus.FAILED)
    skipped = OperationItem(key="3", status=ItemStatus.SKIPPED)
    assert OperationResult.from_items([success]).status == JobStatus.SUCCEEDED
    assert OperationResult.from_items([success, failure]).status == JobStatus.PARTIAL
    assert OperationResult.from_items([failure]).status == JobStatus.FAILED
    assert OperationResult.from_items([skipped, failure]).status == JobStatus.PARTIAL
    assert OperationResult.from_items([]).status == JobStatus.SUCCEEDED


def test_action_registry_preserves_all_legacy_identifiers() -> None:
    expected = {
        "abrir_tareas_personales", "ingresar_numero_tarea", "consultar", "filtrar_tareas",
        "seleccionar_tarea", "reanudar_tarea", "ingresar_observacion", "aceptar_observacion",
        "cerrar_mensaje_ok", "abrir_seguimiento", "guardar_seguimiento",
        "abrir_subida_archivo", "seleccionar_archivo", "subir_archivo",
        "cerrar_mensaje_fin_tarea", "abrir_reasignar", "ingresar_departamento",
        "ingresar_empleado", "observacion_reasignacion", "guardar_reasignacion",
        "definir_variable", "capturar_dato", "esperar_elemento", "pausar_tarea",
        "motivo_pausa", "aceptar_pausa",
    }
    assert set(ACTION_REGISTRY) == expected | {'escribir_seguimiento', 'capturar_datos_tarea', 'ver_seguimiento', 'ver_archivos', 'cerrar_panel', 'verificar_estado'}


def test_validation_blocks_missing_dependencies_and_parameters() -> None:
    flow = WorkflowDefinition(
        name="Inválido",
        steps=[FlowStep(action_id="subir_archivo"), FlowStep(action_id="esperar_elemento")],
    )
    errors = validate_workflow(flow)
    assert any("Seleccionar archivo" in error for error in errors)
    assert any("Selector CSS" in error for error in errors)


def test_placeholders_support_nested_lists_without_type_errors() -> None:
    value = resolve_value({"items": ["{numero}", {"name": "{proveedor}"}]}, {"numero": 7, "proveedor": "Árbol"})
    assert value == {"items": ["7", {"name": "Árbol"}]}


def test_placeholders_support_tuples_and_join_collection_values() -> None:
    value = resolve_value(
        ("{numero}", "Adjuntos: {archivos}"),
        {"numero": 7, "archivos": ["uno.pdf", "dos.pdf"]},
    )
    assert value == ("7", "Adjuntos: uno.pdf, dos.pdf")


def test_pause_catalog_keeps_legacy_reasons_that_were_missing() -> None:
    codes = {reason.split(" - ", 1)[0] for reason in PAUSE_REASONS}
    assert {str(code) for code in range(1619, 1627)} <= codes


def test_irreversible_actions_are_explicit_for_safe_retries() -> None:
    assert {
        "aceptar_observacion",
        "guardar_seguimiento",
        "subir_archivo",
        "guardar_reasignacion",
        "aceptar_pausa",
    } <= IRREVERSIBLE_ACTIONS


def test_workflow_engine_resolves_context_and_default_task_number() -> None:
    executor = RecordingExecutor()
    flow = WorkflowDefinition(
        name="Ejemplo",
        mode=PurchaseMode.BIENES,
        steps=[
            FlowStep(action_id="definir_variable", params={"nombre": "saludo", "valor": "Hola {proveedor}"}),
            FlowStep(action_id="ingresar_numero_tarea", params={"numero": ""}),
        ],
    )
    task = TaskRecord(task_number="98765", supplier="Proveedora", purchase_mode=PurchaseMode.BIENES)
    context = WorkflowEngine(executor).execute(flow, task)
    assert executor.calls[-1][1]["numero"] == "98765"
    assert context["saludo"] == "Hola Proveedora"


def test_workflow_error_contains_step_diagnosis() -> None:
    class Broken:
        def execute(self, action_id: str, params: dict[str, Any], context: dict[str, Any]) -> None:
            raise LookupError("sin resultado")

    flow = WorkflowDefinition(name="Error", steps=[FlowStep(action_id="consultar")])
    with pytest.raises(WorkflowExecutionError, match=r"Paso 1 .*sin resultado") as captured:
        WorkflowEngine(Broken()).execute(flow, TaskRecord(task_number="100"))
    assert isinstance(captured.value.cause, LookupError)
    assert captured.value.context["paso_actual"] == 1
    assert captured.value.context["error_accion"] == "consultar"


def test_workflow_error_records_steps_completed_before_failure() -> None:
    class SecondStepFails(RecordingExecutor):
        def execute(
            self,
            action_id: str,
            params: dict[str, Any],
            context: dict[str, Any],
        ) -> None:
            super().execute(action_id, params, context)
            if action_id == "consultar":
                raise TimeoutError("respuesta lenta")

    flow = WorkflowDefinition(
        name="Diagnóstico",
        steps=[
            FlowStep(
                action_id="definir_variable",
                params={"nombre": "dato", "valor": "ok"},
            ),
            FlowStep(action_id="consultar"),
        ],
    )
    with pytest.raises(WorkflowExecutionError) as captured:
        WorkflowEngine(SecondStepFails()).execute(flow, TaskRecord(task_number="100"))
    assert captured.value.completed_actions == ("definir_variable",)
    assert captured.value.context["dato"] == "ok"


def test_included_flow_expands_snapshot_in_order():
    from compras_tn.application.workflows import expand_workflow, validate_workflow
    from compras_tn.domain.models import FlowStep, WorkflowDefinition
    workflow = WorkflowDefinition(name="Compuesto", steps=[FlowStep(action_id="ejecutar_flujo", params={"nombre": "Abrir", "pasos": [{"action_id": "abrir_tareas_personales", "params": {}}]}), FlowStep(action_id="ingresar_numero_tarea")])
    expanded = expand_workflow(workflow)
    assert [step.action_id for step in expanded.steps] == ["abrir_tareas_personales", "ingresar_numero_tarea"]
    assert not validate_workflow(workflow)
    expanded.steps[0].params["changed"] = True
    assert not workflow.steps[0].params["pasos"][0]["params"]


def test_empty_included_flow_rejected():
    from compras_tn.application.workflows import validate_workflow
    from compras_tn.domain.models import FlowStep, WorkflowDefinition
    assert validate_workflow(WorkflowDefinition(name="Vacio", steps=[FlowStep(action_id="ejecutar_flujo")]))
