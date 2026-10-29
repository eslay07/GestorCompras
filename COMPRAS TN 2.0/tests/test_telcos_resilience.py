from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from compras_tn.application.workflows import WorkflowEngine, WorkflowExecutionError
from compras_tn.domain.models import (
    FlowStep,
    ItemStatus,
    SessionCredentials,
    TaskRecord,
    WorkflowDefinition,
)
from compras_tn.infrastructure.automation.telcos import SeleniumTelcosGateway
from compras_tn.paths import AppPaths


class Settings:
    def __init__(self, retries: int = 2) -> None:
        self.retries = retries

    def get(self, _namespace: str, key: str, default: Any = None) -> Any:
        return self.retries if key == "actua_retries" else default


class Driver:
    current_url = "https://telcos.example/tareas?ticket=redacted"
    title = "Tareas"

    def __init__(self) -> None:
        self.quit_calls = 0

    def save_screenshot(self, destination: str) -> bool:
        Path(destination).write_bytes(b"png")
        return True

    def quit(self) -> None:
        self.quit_calls += 1


def _gateway(tmp_path: Path, retries: int = 2) -> SeleniumTelcosGateway:
    return SeleniumTelcosGateway(
        Settings(retries),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        AppPaths.from_root(tmp_path / "appdata"),
    )


def _credentials() -> SessionCredentials:
    return SessionCredentials(username="user", email="user@example.com", password="secret")


def test_transient_failure_does_not_replay_entire_workflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = _gateway(tmp_path)
    driver = Driver()
    recovered = 0
    attempts = 0

    monkeypatch.setattr(gateway, "_new_authenticated_driver", lambda *_args: driver)

    def recover(*_args: Any) -> Driver:
        nonlocal recovered
        recovered += 1
        return driver

    monkeypatch.setattr(gateway, "_recover_or_replace", recover)

    def execute(
        _self: WorkflowEngine,
        _workflow: WorkflowDefinition,
        task: TaskRecord,
    ) -> dict[str, Any]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise WorkflowExecutionError(
                3,
                "consultar",
                TimeoutError("AJAX lento"),
                context={"pasos_completados": ["abrir_tareas_personales"]},
            )
        return {"task_number": task.task_number, "pasos_completados": ["consultar"]}

    monkeypatch.setattr(WorkflowEngine, "execute", execute)
    result = gateway.execute_workflow(
        _credentials(),
        WorkflowDefinition(name="Flujo", steps=[FlowStep(action_id="consultar")]),
        [TaskRecord(task_number="100")],
        headless=True,
    )

    assert attempts == 1
    assert recovered == 0
    assert result.items[0].status == ItemStatus.FAILED
    diagnostics = result.items[0].payload["diagnosticos_intentos"]
    assert diagnostics[0]["step"] == 3
    assert Path(diagnostics[0]["screenshot"]).is_file()


def test_failure_at_commit_step_is_not_replayed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = _gateway(tmp_path, retries=3)
    driver = Driver()
    attempts = 0
    monkeypatch.setattr(gateway, "_new_authenticated_driver", lambda *_args: driver)

    def execute(
        _self: WorkflowEngine,
        _workflow: WorkflowDefinition,
        _task: TaskRecord,
    ) -> dict[str, Any]:
        nonlocal attempts
        attempts += 1
        raise WorkflowExecutionError(
            4,
            "aceptar_observacion",
            TimeoutError("confirmación no visible"),
            context={
                "pasos_completados": ["reanudar_tarea", "ingresar_observacion"],
            },
        )

    monkeypatch.setattr(WorkflowEngine, "execute", execute)
    result = gateway.execute_workflow(
        _credentials(),
        WorkflowDefinition(
            name="Flujo",
            steps=[FlowStep(action_id="aceptar_observacion")],
        ),
        [TaskRecord(task_number="200")],
        headless=True,
    )

    assert attempts == 1
    assert result.items[0].status == ItemStatus.FAILED
    assert "evitar" in result.items[0].message


def test_startup_failure_returns_a_result_for_every_task(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = _gateway(tmp_path)

    def cannot_login(*_args: Any) -> Driver:
        raise RuntimeError("portal fuera de servicio")

    monkeypatch.setattr(gateway, "_new_authenticated_driver", cannot_login)
    tasks = [TaskRecord(task_number="1"), TaskRecord(task_number="2")]
    result = gateway.execute_workflow(
        _credentials(),
        WorkflowDefinition(name="Flujo", steps=[FlowStep(action_id="consultar")]),
        tasks,
        headless=True,
    )

    assert [item.key for item in result.items] == ["1", "2"]
    assert all(item.status == ItemStatus.FAILED for item in result.items)
    assert all("portal fuera de servicio" in item.message for item in result.items)


def test_retry_classification_rejects_configuration_and_commit_errors() -> None:
    missing_file = WorkflowExecutionError(
        2,
        "seleccionar_archivo",
        FileNotFoundError("orden.pdf"),
        context={"pasos_completados": []},
    )
    commit = WorkflowExecutionError(
        5,
        "subir_archivo",
        TimeoutError("sin confirmación"),
        context={"pasos_completados": ["seleccionar_archivo"]},
    )
    search = WorkflowExecutionError(
        3,
        "consultar",
        TimeoutError("respuesta lenta"),
        context={"pasos_completados": []},
    )

    assert not SeleniumTelcosGateway._can_retry_workflow(missing_file, 1, 3)
    assert not SeleniumTelcosGateway._can_retry_workflow(commit, 1, 3)
    assert SeleniumTelcosGateway._can_retry_workflow(search, 1, 3)


def test_duplicate_tasks_and_second_run_do_not_execute_again(tmp_path, monkeypatch):
    gateway = _gateway(tmp_path)
    driver = Driver()
    calls = []
    monkeypatch.setattr(gateway, "_new_authenticated_driver", lambda *_args: driver)
    monkeypatch.setattr(WorkflowEngine, "execute", lambda _self, _flow, task: calls.append(task.task_number) or {"task_number": task.task_number})
    workflow = WorkflowDefinition(name="Unico", steps=[FlowStep(action_id="consultar")])
    task = TaskRecord(task_number="166573896")
    first = gateway.execute_workflow(_credentials(), workflow, [task, task.model_copy(update={"origin": "correo"})], headless=True)
    assert calls == [task.task_number]
    assert len(first.items) == 1 and first.items[0].status == ItemStatus.SUCCEEDED
    monkeypatch.setattr(gateway, "_new_authenticated_driver", lambda *_args: pytest.fail("No debe abrir navegador para una tarea ya ejecutada"))
    second = gateway.execute_workflow(_credentials(), workflow, [task], headless=True)
    assert len(second.items) == 1 and second.items[0].status == ItemStatus.SKIPPED
    assert calls == [task.task_number]

def test_failed_task_stops_batch_before_resuming_another(tmp_path, monkeypatch):
    gateway = _gateway(tmp_path)
    driver = Driver()
    monkeypatch.setattr(gateway, '_new_authenticated_driver', lambda *_: driver)
    calls = []
    def execute(_self, _workflow, task):
        calls.append(task.task_number)
        raise WorkflowExecutionError(8, 'abrir_subida_archivo', RuntimeError('stale'),
                                     context={'pasos_completados': ['reanudar_tarea']})
    monkeypatch.setattr(WorkflowEngine, 'execute', execute)
    flow = WorkflowDefinition(name='Cargar ordenes', steps=[FlowStep(action_id='consultar')])
    tasks = [TaskRecord(task_number=str(n)) for n in (163826137, 166573896)]
    result = gateway.execute_workflow(_credentials(), flow, tasks, headless=True)
    assert calls == ['163826137']
    assert [item.status for item in result.items] == [ItemStatus.FAILED, ItemStatus.SKIPPED]
    assert 'No iniciada' in result.items[1].message


def test_only_one_orchestrator_may_run_at_a_time(tmp_path, monkeypatch):
    first = _gateway(tmp_path)
    second = _gateway(tmp_path)
    def running(*args, **kwargs):
        with pytest.raises(RuntimeError, match='solo se permite una tarea'):
            second.execute_workflow()
        return 'completed'
    monkeypatch.setattr(first, '_execute_workflow', running)
    assert first.execute_workflow() == 'completed'
    monkeypatch.setattr(second, '_execute_workflow', lambda: 'next')
    assert second.execute_workflow() == 'next'


def test_orchestrator_report_names_flow_even_with_no_items():
    from compras_tn.infrastructure.operation_report import render_operation_report
    from compras_tn.domain.models import OperationRequest, OperationResult, PurchaseMode
    request = OperationRequest(kind='actualizar_tareas', mode=PurchaseMode.BIENES,
                               options={'workflow':'Cargar ordenes <prueba>'})
    report = render_operation_report(request, OperationResult.from_items([], 'Terminado'), 'Orquestador Telcos')
    assert 'Cargar ordenes <prueba>' in report.text
    assert 'Cargar ordenes <prueba>' in report.subject
    assert 'Cargar ordenes &lt;prueba&gt;' in report.html

@pytest.mark.parametrize('continue_batch', [False, True])
def test_workflow_policy_controls_next_task_after_failure(tmp_path, monkeypatch, continue_batch):
    gateway = _gateway(tmp_path)
    monkeypatch.setattr(gateway, '_new_authenticated_driver', lambda *_: Driver())
    calls=[]
    def execute(_self, _flow, task):
        calls.append(task.task_number)
        if task.task_number == '100':
            raise RuntimeError('La tarea sigue activa')
        return {}
    monkeypatch.setattr(WorkflowEngine, 'execute', execute)
    flow=WorkflowDefinition(name='Politica', stop_on_error=not continue_batch, steps=[FlowStep(action_id='consultar')])
    gateway.execute_workflow(_credentials(), flow, [TaskRecord(task_number='100'), TaskRecord(task_number='200')], headless=True)
    assert calls == (['100','200'] if continue_batch else ['100'])


def test_workflow_failure_policy_persists(repositories):
    flow = repositories.save_workflow(WorkflowDefinition(name='Continuar', stop_on_error=False))
    assert flow.stop_on_error is False
    assert repositories.list_workflows()[0].stop_on_error is False
