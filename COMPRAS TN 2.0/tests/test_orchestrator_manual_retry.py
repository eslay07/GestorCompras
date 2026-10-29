import pytest

from compras_tn.application.workflows import WorkflowEngine
from compras_tn.domain.models import (
    FlowStep, ItemStatus, OperationItem, OperationResult, PurchaseMode,
    TaskRecord, WorkflowDefinition,
)
from compras_tn.infrastructure.workflow_once import WorkflowOnce
from test_application_services import _facade


@pytest.mark.parametrize('state', ['failed', 'cancelled'])
def test_failed_workflow_can_be_claimed_again_but_success_cannot(app_paths, state):
    flow = WorkflowDefinition(name='Adjuntar documentos', mode=PurchaseMode.BIENES)
    first, second = WorkflowOnce(app_paths, flow), WorkflowOnce(app_paths, flow)
    assert first.claim('166573896')
    assert second.seen('166573896')
    assert not second.claim('166573896')
    first.finish('166573896', state)
    assert not second.seen('166573896')
    assert second.claim('166573896')
    assert not first.claim('166573896')
    second.finish('166573896', 'succeeded')
    after_restart = WorkflowOnce(app_paths, flow)
    assert after_restart.seen('166573896')
    assert not after_restart.claim('166573896')


def test_manual_data_reaches_workflow_and_can_update_pending_task(repositories):
    task = TaskRecord(task_number='166573896', origin='manual', purchase_mode=PurchaseMode.BIENES,
                      order_number='377565', supplier='SISEGUSA')
    repositories.enqueue([task])
    repositories.enqueue([task.model_copy(update={'supplier': 'Proveedor corregido'})])
    pending, = repositories.list_pending('manual')
    assert pending.order_number == '377565'
    assert pending.supplier == 'Proveedor corregido'
    flow = WorkflowDefinition(name='Resumen', steps=[FlowStep(action_id='definir_variable',
        params={'nombre': 'resumen', 'valor': 'OC {orden_compra} / {proveedor} / {numero_tarea}'})])
    class Executor:
        def execute(self, action_id, params, context):
            context[params['nombre']] = params['valor']
    context = WorkflowEngine(Executor()).execute(flow, pending)
    assert context['resumen'] == 'OC 377565 / Proveedor corregido / 166573896'


def test_only_successful_tasks_leave_inbox(repositories, tmp_path):
    facade, *_ = _facade(repositories, tmp_path)
    tasks = [TaskRecord(task_number=n, origin='manual', purchase_mode=PurchaseMode.BIENES)
             for n in ('166573896', '166298710')]
    facade.enqueue_tasks(tasks)
    flow = WorkflowDefinition(name='Prueba')
    facade.telcos.execute_workflow = lambda *args, **kwargs: OperationResult.from_items([
        OperationItem(key=tasks[0].task_number, status=ItemStatus.SUCCEEDED),
        OperationItem(key=tasks[1].task_number, status=ItemStatus.FAILED),
    ])
    facade.execute_workflow(flow, tasks, headless=True)
    pending = facade.list_pending_tasks('manual')
    assert [t.task_number for t in pending] == ['166298710']
    facade.telcos.execute_workflow = lambda *args, **kwargs: OperationResult.from_items([
        OperationItem(key=pending[0].task_number, status=ItemStatus.SUCCEEDED)])
    facade.execute_workflow(flow, pending, headless=True)
    assert facade.list_pending_tasks('manual') == []


def test_conflicting_results_keep_task_available(repositories, tmp_path):
    facade, *_ = _facade(repositories, tmp_path)
    task = TaskRecord(task_number='166573896', origin='manual', purchase_mode=PurchaseMode.BIENES)
    facade.enqueue_tasks([task])
    facade.telcos.execute_workflow = lambda *args, **kwargs: OperationResult.from_items([
        OperationItem(key=task.task_number, status=ItemStatus.SUCCEEDED),
        OperationItem(key=task.task_number, status=ItemStatus.FAILED),
    ])
    facade.execute_workflow(WorkflowDefinition(name='Prueba'), [task], headless=True)
    assert [t.task_number for t in facade.list_pending_tasks('manual')] == ['166573896']


def test_manual_fields_and_result_refresh(qtbot, tmp_path):
    from conftest import PROJECT_ROOT
    from compras_tn.bootstrap import build_container
    from compras_tn.paths import AppPaths
    from compras_tn.presentation.jobs import JobManager
    from compras_tn.presentation.workflows_page import WorkflowRunner
    container = build_container(app_paths=AppPaths.from_root(tmp_path/'ui'), project_root=PROJECT_ROOT)
    runner = WorkflowRunner(container.services, JobManager(), PurchaseMode.BIENES)
    qtbot.addWidget(runner)
    runner.show()
    runner.source.setCurrentText('manual')
    assert not runner.manual.parentWidget().isHidden()
    runner.manual.setPlainText('166573896\n166298710')
    runner.add_manual()
    assert runner.table.rowCount() == 2
    for task in runner.tasks:
        container.services.update_task_orders(task, [dict(order_number='377565', supplier='SISEGUSA', approvers=['NOMBRE COMPLETO'])])
    runner.refresh()
    assert all(t.order_number == '377565' and t.supplier == 'SISEGUSA' for t in runner.tasks)
    container.services.inbox.consume(['166573896'])
    runner.execution_job = 'completed-job'
    runner._execution_finished('completed-job', None)
    assert [t.task_number for t in runner.tasks] == ['166298710']
    assert runner.table.item(0, 3).text() == '377565'
    runner.close()


def test_new_orders_can_run_without_repeating_previous_orders(app_paths):
    flow = WorkflowDefinition(name='Adjuntar documentos', mode=PurchaseMode.BIENES)
    task = TaskRecord(task_number='163519599', origin='manual', purchase_mode=PurchaseMode.BIENES,
                      order_number='377001', supplier='Proveedor')
    first = WorkflowOnce(app_paths, flow)
    assert first.pending_task(task).order_number == '377001'
    assert first.claim(task.task_number)
    first.finish(task.task_number, 'succeeded')
    second = WorkflowOnce(app_paths, flow)
    expanded = task.model_copy(update={'order_number': '377001, 377002'})
    pending = second.pending_task(expanded)
    assert pending.order_number == '377002'
    assert [row['order_number'] for row in pending.payload['orders']] == ['377002']
    assert second.claim(task.task_number)
    second.finish(task.task_number, 'succeeded')
    assert WorkflowOnce(app_paths, flow).pending_task(expanded) is None


def test_legacy_success_uses_audited_orders_to_release_new_orders(app_paths):
    import json
    import sqlite3
    flow = WorkflowDefinition(name='Adjuntar documentos', mode=PurchaseMode.BIENES)
    task = TaskRecord(task_number='163519599', origin='manual', purchase_mode=PurchaseMode.BIENES,
                      order_number='377001', supplier='Proveedor')
    legacy = WorkflowOnce(app_paths, flow)
    assert legacy.claim(task.task_number)
    legacy.finish(task.task_number, 'succeeded')
    with sqlite3.connect(app_paths.database) as connection:
        connection.execute('CREATE TABLE operation_runs(id INTEGER, kind TEXT, mode TEXT, request_json TEXT)')
        connection.execute('CREATE TABLE operation_items(run_id INTEGER, item_key TEXT, status TEXT)')
        request = json.dumps({'options': {'workflow': flow.name}, 'items': [task.model_dump(mode='json')]})
        connection.execute('INSERT INTO operation_runs VALUES (1,?,?,?)', ('actualizar_tareas','bienes',request))
        connection.execute('INSERT INTO operation_items VALUES (1,?,?)', (task.task_number,'succeeded'))
    pending = WorkflowOnce(app_paths, flow).pending_task(task.model_copy(update={'order_number':'377001, 377002'}))
    assert pending.order_number == '377002'


def test_active_task_blocks_new_order_scope_and_unknown_legacy_stays_blocked(app_paths):
    flow = WorkflowDefinition(name='Adjuntar documentos', mode=PurchaseMode.BIENES)
    task = TaskRecord(task_number='163519599', origin='manual', purchase_mode=PurchaseMode.BIENES,
                      order_number='377002')
    legacy = WorkflowOnce(app_paths, flow)
    assert legacy.claim(task.task_number)
    assert WorkflowOnce(app_paths, flow).pending_task(task) is None
    legacy.finish(task.task_number, 'succeeded')
    assert WorkflowOnce(app_paths, flow).pending_task(task) is None


def test_scope_claim_rechecks_orders_completed_since_preparation(app_paths):
    flow = WorkflowDefinition(name='Adjuntar documentos', mode=PurchaseMode.BIENES)
    task = TaskRecord(task_number='163519599', origin='manual', purchase_mode=PurchaseMode.BIENES,
                      order_number='377001')
    first, second = WorkflowOnce(app_paths, flow), WorkflowOnce(app_paths, flow)
    first.pending_task(task)
    second.pending_task(task.model_copy(update={'order_number':'377001, 377002'}))
    assert first.claim(task.task_number)
    first.finish(task.task_number, 'succeeded')
    assert not second.claim(task.task_number)
    assert second.pending_task(task.model_copy(update={'order_number':'377001, 377002'})).order_number == '377002'
    assert second.claim(task.task_number)
