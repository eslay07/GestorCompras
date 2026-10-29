from types import SimpleNamespace

import pytest

from compras_tn.application.task_orders import task_orders
from compras_tn.domain.models import TaskRecord, PurchaseMode, PurchaseOrderDraft, WorkflowDefinition, FlowStep
from test_application_services import _facade


def task(origin, order='377657', number='166077370'):
    return TaskRecord(task_number=number, origin=origin, purchase_mode=PurchaseMode.BIENES,
                      order_number=order, supplier='Proveedor')


def receipt(facade, number='166077370', order='377657', names=None):
    draft = PurchaseOrderDraft(task_number=number, supplier='Proveedor')
    facade.settings.set('oc_approvals', facade._oc_scope() + order,
        dict(state='synced', number=order, names=names or ['LOCAL COMPLETO'], draft=draft.model_dump(mode='json')))


@pytest.mark.parametrize('origin', ['correo', 'reasignacion', 'correos_masivos', 'descargas', 'carga_oc_automatica'])
def test_every_origin_carries_names_to_inbox_before_any_workflow(repositories, tmp_path, origin):
    facade, *_ = _facade(repositories, tmp_path)
    receipt(facade)
    calls = []
    def read(numbers):
        calls.append(numbers)
        return {'166077370': [dict(order_number='377657', supplier='Proveedor', approvers=['GENERAL COMPLETO']),
                              dict(order_number='377658', supplier='Otro', approvers=['OTRA OC'])]}
    facade.sheets.read_task_orders = read
    facade.enqueue_tasks([task(origin)])
    saved, = repositories.list_pending(origin)
    assert task_orders(saved) == [dict(order_number='377657', supplier='Proveedor',
        approvers=['LOCAL COMPLETO'] if origin == 'descargas' else ['GENERAL COMPLETO'])]
    assert len(calls) == (0 if origin == 'descargas' else 1)


def test_second_order_from_same_origin_is_merged_and_rescan_updates_names(repositories, tmp_path):
    facade, *_ = _facade(repositories, tmp_path)
    rows = [dict(order_number='377657', supplier='Proveedor', approvers=['UNO']),
            dict(order_number='377658', supplier='Proveedor B', approvers=['DOS'])]
    facade.sheets.read_task_orders = lambda numbers: {'166077370': rows}
    second = task('correos_masivos', '377658').model_copy(update={'supplier': 'Proveedor B'})
    facade.enqueue_tasks([task('correos_masivos'), second])
    rows[0]['approvers'] = ['UNO ACTUALIZADO']
    facade.enqueue_tasks([task('correos_masivos')])
    saved, = repositories.list_pending('correos_masivos')
    assert task_orders(saved) == rows


def test_pending_sources_hydrate_locally_without_any_google_request(repositories, tmp_path):
    facade, *_ = _facade(repositories, tmp_path)
    receipt(facade)
    facade.sheets.read_task_orders = lambda numbers: pytest.fail('UI refresh must not access the network')
    repositories.enqueue([task('descargas'), task('correo', '377658')])
    values = facade.list_pending_tasks()
    assert task_orders(values[0])[0]['approvers'] == ['LOCAL COMPLETO']
    assert task_orders(values[1])[0]['approvers'] == []
    assert task_orders(repositories.list_pending('descargas')[0])[0]['approvers'] == ['LOCAL COMPLETO']


def test_cached_names_never_cross_task_or_scope(repositories, tmp_path):
    facade, *_ = _facade(repositories, tmp_path)
    receipt(facade, number='166077371')
    repositories.enqueue([task('descargas')])
    assert task_orders(facade.list_pending_tasks()[0])[0]['approvers'] == []


def test_manual_names_are_preserved_but_other_manual_fields_do_not_block_lookup(repositories, tmp_path):
    facade, *_ = _facade(repositories, tmp_path)
    manual = task('manual')
    repositories.enqueue([manual])
    facade.update_task_orders(manual, [dict(order_number='377657', supplier='Proveedor corregido', approvers=[])])
    facade.sheets.read_task_orders = lambda numbers: {'166077370': [
        dict(order_number='377657', supplier='Proveedor', approvers=['DE GENERAL'])]}
    facade.refresh_workflow_approvers(repositories.list_pending())
    saved, = repositories.list_pending()
    assert saved.payload['orders_edited'] is True
    assert task_orders(saved)[0] == dict(order_number='377657', supplier='Proveedor corregido', approvers=['DE GENERAL'])
    facade.update_task_orders(saved, [dict(order_number='377657', supplier='Proveedor corregido', approvers=['MANUAL'])])
    facade.refresh_workflow_approvers(repositories.list_pending())
    assert task_orders(repositories.list_pending()[0])[0]['approvers'] == ['MANUAL']


def test_enrichment_does_not_replace_other_origin_orders(repositories, tmp_path):
    facade, *_ = _facade(repositories, tmp_path)
    repositories.enqueue([task('correo'), task('descargas', '377658')])
    facade.sheets.read_task_orders = lambda numbers: {'166077370': [
        dict(order_number='377657', supplier='Proveedor', approvers=['UNO']),
        dict(order_number='377658', supplier='Proveedor', approvers=['DOS'])]}
    facade.refresh_workflow_approvers(repositories.list_pending('correo'))
    mail = repositories.list_pending('correo')[0]
    download = repositories.list_pending('descargas')[0]
    assert [r['order_number'] for r in task_orders(mail)] == ['377657']
    assert task_orders(mail)[0]['approvers'] == ['UNO']
    assert [r['order_number'] for r in task_orders(download)] == ['377658']
    assert task_orders(download)[0]['approvers'] == []


def test_task_only_import_discovers_exact_order_associations(repositories, tmp_path):
    facade, *_ = _facade(repositories, tmp_path)
    facade.sheets.read_task_orders = lambda numbers: {'166077370': [
        dict(order_number='377657', supplier='Proveedor', approvers=['UNO']),
        dict(order_number='377658', supplier='Proveedor B', approvers=['DOS'])]}
    facade.enqueue_tasks([task('correo', '')])
    saved, = repositories.list_pending()
    assert len(task_orders(saved)) == 2
    assert task_orders(saved)[1]['supplier'] == 'Proveedor B'


def test_general_failure_does_not_prevent_handoff_or_remove_cached_names(repositories, tmp_path):
    facade, *_ = _facade(repositories, tmp_path)
    receipt(facade)
    def fail(numbers): raise ConnectionResetError(10054, 'Connection reset')
    facade.sheets.read_task_orders = fail
    facade.enqueue_tasks([task('correos_masivos')])
    saved, = repositories.list_pending()
    assert task_orders(saved)[0]['approvers'] == ['LOCAL COMPLETO']
    assert '10054' in saved.payload['approvers_sync_error']


def test_orchestrator_source_loads_names_in_background(qtbot, repositories, tmp_path):
    from compras_tn.presentation.jobs import JobManager
    from compras_tn.presentation.workflows_page import WorkflowRunner
    facade, *_ = _facade(repositories, tmp_path)
    repositories.enqueue([task('correo')])
    facade.sheets.read_task_orders = lambda numbers: {'166077370': [
        dict(order_number='377657', supplier='Proveedor', approvers=['NOMBRE COMPLETO'])]}
    runner = WorkflowRunner(facade, JobManager(), PurchaseMode.BIENES)
    qtbot.addWidget(runner)
    runner.source.setCurrentText('correo')
    qtbot.waitUntil(lambda: not runner.approvers_job, timeout=5000)
    assert runner.table.item(0, 5).text() == 'NOMBRE COMPLETO'
    from PySide6.QtCore import Qt
    runner.table.item(0, 0).setCheckState(Qt.Unchecked)
    runner.refresh_approvers(force=True)
    qtbot.waitUntil(lambda: not runner.approvers_job, timeout=5000)
    assert runner.table.item(0, 0).checkState() == Qt.Unchecked


def test_consumed_task_is_not_reopened_by_background_enrichment(repositories, tmp_path):
    facade, *_ = _facade(repositories, tmp_path)
    saved = task('correo')
    repositories.enqueue([saved])
    repositories.consume([saved.task_number])
    facade.sheets.read_task_orders = lambda numbers: {'166077370': [
        dict(order_number='377657', supplier='Proveedor', approvers=['NOMBRE'])]}
    facade.refresh_workflow_approvers([saved])
    assert repositories.list_pending() == []


def test_general_status_reader_transports_column_o_with_each_order():
    from compras_tn.infrastructure.google_sheets import GoogleSheetsGateway
    rows = [
        ['', '', 'TAREA 166077370', '', '', '', '', '', 'S/N', 'SISTEMAS', 'PERSONA', 'PROYECTO'],
        ['', 'COD-1', 'ARTICULO UNO', 1, 'Proveedor', 10, '377657', '', '', '', '', '', '', '', 'APROBADOR UNO, APROBADOR DOS'],
        ['', 'COD-2', 'ARTICULO DOS', 1, 'Proveedor B', 20, '377658', '', '', '', '', '', '', '', 'APROBADOR TRES'],
    ]
    class Sheet:
        def get(self, area, **kw):
            if area == 'A7346:O': return rows
            if area == 'G7346:G7348': return [[''], ['377657'], ['377658']]
            pytest.fail('Unexpected range ' + area)
    gateway = GoogleSheetsGateway(SimpleNamespace(get=lambda ns, key, default=None: default))
    gateway._worksheet = lambda *a, **kw: Sheet()
    state = gateway.read_purchase_task_status()['166077370']
    assert state['ready']
    assert state['orders'] == [dict(order_number='377657', supplier='Proveedor', approvers=['APROBADOR UNO','APROBADOR DOS']),
                               dict(order_number='377658', supplier='Proveedor B', approvers=['APROBADOR TRES'])]


def test_mass_mail_handoff_contains_names_without_executing_a_workflow(repositories, tmp_path):
    from compras_tn.domain.models import EmailTemplate, JobStatus
    facade, mail, *_ = _facade(repositories, tmp_path)
    facade.sheets.read_task_orders = lambda numbers: {'101': [dict(order_number='1', supplier='P', approvers=['NOMBRE COMPLETO'])]}
    result = facade.send_dispatch(['1'], EmailTemplate(name='Prueba', html='Hola'), grouped=False, mode=PurchaseMode.BIENES)
    assert result.status == JobStatus.SUCCEEDED
    assert len(mail.sent) == 1
    queued, = repositories.list_pending('correos_masivos')
    assert task_orders(queued)[0]['approvers'] == ['NOMBRE COMPLETO']


def test_empty_column_o_never_invents_names_and_blocks_dependent_flow(repositories, tmp_path):
    facade, *_ = _facade(repositories, tmp_path)
    facade.sheets.read_task_orders = lambda numbers: {'166077370': [
        dict(order_number='377657', supplier='Proveedor', approvers=[])]}
    facade.enqueue_tasks([task('correo')])
    workflow = WorkflowDefinition(name='Dato', steps=[FlowStep(action_id='definir_variable',
        params={'nombre':'texto', 'valor':'Pendiente {aprobadores}'})])
    result = facade.prepare_workflow_tasks(workflow, repositories.list_pending())
    assert task_orders(result[0]['task'])[0]['approvers'] == []
    assert 'aprobadores' in result[0]['error'] and '377657' in result[0]['error']
