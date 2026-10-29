from types import SimpleNamespace

import pytest

from compras_tn.application.task_cycle import STAGES, TaskCycle, WARNING_PREFIX, request_stage
from compras_tn.domain.models import (ItemStatus, OperationItem, OperationRequest,
                                      OperationResult, PurchaseMode, TaskRecord, WorkflowDefinition)
from test_application_services import _facade


def request(stage, orders=('377745',), task='163519599'):
    return OperationRequest(kind='actualizar_tareas', options={'cycle_stage': stage},
        items=[{'task_number': task, 'order_number': ', '.join(orders)}])


def record(repositories, stage, orders=('377745',), status=ItemStatus.SUCCEEDED):
    req = request(stage, orders)
    run = repositories.start(req)
    repositories.finish(run, OperationResult.from_items([
        OperationItem(key='163519599', status=status)]))


def test_cycle_recognizes_existing_workflow_names():
    for name, stage in [('Subir cotizaciones y actualizar seguimiento de oc', 5),
                        ('Firma de órdenes', 7), ('cargar orden y solicitar despacho', 9)]:
        assert request_stage(OperationRequest(kind='actualizar_tareas', options={'workflow': name})) == stage
    assert STAGES[10] == 'Reasignar tareas completas'


def test_complete_prior_history_has_no_warning(repositories):
    for stage in range(3, 10):
        record(repositories, stage)
    assert TaskCycle(repositories).warnings(request(10)) == ''


def test_partial_orders_do_not_mark_new_orders_as_processed(repositories):
    for stage in range(3, 7):
        record(repositories, stage)
    warning = TaskCycle(repositories).warnings(request(7, ('377745', '377746')))
    assert 'OC 377745:' not in warning
    assert 'OC 377746:' in warning
    assert '4. Cargar órdenes' in warning
    assert '5. Subir cotizaciones' in warning
    assert '6. Descargar órdenes' in warning
    assert '3. Organizar' not in warning  # Organizer belongs to the task folder.


@pytest.mark.parametrize('status', [ItemStatus.FAILED, ItemStatus.SKIPPED])
def test_failed_or_skipped_previous_stage_still_warns(repositories, status):
    record(repositories, 3)
    record(repositories, 4, status=status)
    assert '4. Cargar órdenes' in TaskCycle(repositories).warnings(request(5))


def test_warning_does_not_prevent_workflow_and_is_in_result(repositories, tmp_path):
    facade, *_ = _facade(repositories, tmp_path)
    events = []
    task = TaskRecord(task_number='163519599', order_number='377746')
    result = facade.execute_workflow(WorkflowDefinition(name='Firma de órdenes'), [task],
        headless=True, progress=lambda *args: events.append(args))
    assert result.items[0].status == ItemStatus.SUCCEEDED
    assert WARNING_PREFIX in result.message
    assert any(e[2].startswith(WARNING_PREFIX) for e in events)
    assert '3. Organizar' not in result.message


def test_history_failure_is_advisory_and_workflow_still_runs(repositories, tmp_path, monkeypatch):
    facade, *_ = _facade(repositories, tmp_path)
    monkeypatch.setattr(repositories, 'cycle_successes', lambda: (_ for _ in ()).throw(OSError('historial no disponible')))
    result = facade.execute_workflow(WorkflowDefinition(name='Firma de órdenes'),
        [TaskRecord(task_number='163519599', order_number='377746')], headless=True)
    assert result.items[0].status == ItemStatus.SUCCEEDED
    assert WARNING_PREFIX not in result.message


def test_manual_steps_are_reminders_not_automatic_completion(repositories):
    warning = TaskCycle(repositories).warnings(OperationRequest(kind='organizar_cotizaciones',
        items=[{'task_number':'163519599'}]))
    assert warning == ''


def test_old_organizer_history_is_used(repositories):
    import json
    from sqlalchemy import text
    row = {'task_number':'163519599', 'status':'Guardado', 'saved_path':'C:/prueba/cotizacion.pdf', 'error':''}
    with repositories.database.session() as session:
        session.execute(text('INSERT INTO quotation_attachments(identity,account,payload) VALUES (:id,:account,:payload)'),
            {'id':'cycle-test', 'account':'test', 'payload':json.dumps(row)})
    assert TaskCycle(repositories).warnings(OperationRequest(kind='precarga_oc_bienes',
        items=[{'task_number':'163519599'}])) == ''


def test_alert_is_nonmodal_and_remains_after_completion(qtbot):
    from compras_tn.presentation.jobs import JobManager
    from compras_tn.presentation.widgets import OperationPanel
    panel = OperationPanel(JobManager())
    qtbot.addWidget(panel)
    panel.show()
    panel.begin('cycle-test', 'Iniciando')
    panel._progress('cycle-test', 0, 1, WARNING_PREFIX + ' Tarea 163519599: falta el paso 6.')
    assert panel.cycle_banner.isVisible()
    assert panel._cycle_dialog is None
    panel._show_cycle_details()
    assert panel._cycle_dialog.isVisible()
    panel._progress('cycle-test', 1, 1, 'Procesando tarea')
    panel._finished('cycle-test', OperationResult.from_items([]))
    assert panel.cycle_banner.isVisible()
    panel._cycle_dialog.close()
    assert panel.cycle_details.isVisible()


def test_failed_download_destination_does_not_complete_that_task(repositories):
    req = OperationRequest(kind='descarga_normal', items=[{'order_number':'377745'}])
    run = repositories.start(req)
    repositories.finish(run, OperationResult.from_items([
        OperationItem(key='377745', status=ItemStatus.SUCCEEDED, payload={
            'order_number':'377745', 'task_numbers':['163519599','166549665'],
            'task_destinations':[
                {'task_number':'163519599','preparation_status':'succeeded'},
                {'task_number':'166549665','preparation_status':'failed'}]})]))
    evidence = TaskCycle(repositories).evidence()
    assert ('163519599','377745',6) in evidence
    assert ('166549665','377745',6) not in evidence

@pytest.mark.parametrize('sheet_written', [False, True])
def test_saved_oc_with_pending_followup_counts_for_all_grouped_tasks(repositories, sheet_written):
    req = OperationRequest(kind='precarga_oc_bienes', items=[{
        'task_number':'163519599', 'supplier':'Proveedor', 'sources':[
            {'task_number':'163519599'}, {'task_number':'166549665'}]}])
    run = repositories.start(req)
    repositories.finish(run, OperationResult.from_items([
        OperationItem(key='163519599 · Proveedor', status=ItemStatus.FAILED,
            payload={'task_number':'163519599', 'order_number':'377745',
                     'sheet_written':sheet_written})]))
    evidence = TaskCycle(repositories).evidence()
    assert ('163519599','377745',4) in evidence
    assert ('166549665','377745',4) in evidence


def test_failed_oc_without_save_confirmation_does_not_count(repositories):
    req = OperationRequest(kind='precarga_oc_bienes', items=[{'task_number':'163519599'}])
    run = repositories.start(req)
    repositories.finish(run, OperationResult.from_items([
        OperationItem(key='163519599', status=ItemStatus.FAILED,
            payload={'task_number':'163519599', 'order_number':'377745'})]))
    assert ('163519599','377745',4) not in TaskCycle(repositories).evidence()


@pytest.mark.parametrize('stage', range(4, 11))
@pytest.mark.parametrize('approved', [True, False])
def test_cycle_confirmation_before_any_audited_module(repositories, tmp_path, stage, approved):
    from compras_tn.domain.models import JobStatus
    facade, *_ = _facade(repositories, tmp_path)
    calls = []
    def progress(*args):
        pass
    def confirm(message):
        assert calls == []
        assert 'manual' not in message
        assert '¿Desea continuar de todas formas?' in message
        return approved
    progress.confirm_cycle = confirm
    def operation():
        calls.append('executed')
        return OperationResult.from_items([OperationItem(key='163519599', status=ItemStatus.SUCCEEDED)])
    result = facade._audited(request(stage), operation, progress=progress)
    assert calls == (['executed'] if approved or stage == 4 else [])
    assert result.status == (JobStatus.SUCCEEDED if approved or stage == 4 else JobStatus.CANCELLED)


def test_organizer_has_no_previous_system_step_to_confirm(repositories, tmp_path):
    facade, *_ = _facade(repositories, tmp_path)
    def progress(*args):
        pass
    progress.confirm_cycle = lambda message: pytest.fail('Organizer must not ask about manual steps')
    assert facade._cycle_notice(OperationRequest(kind='organizar_cotizaciones',
        items=[{'task_number':'163519599'}]), progress) == ''


@pytest.mark.parametrize('decision', ['continue', 'cancel', 'close', 'cancel_job'])
def test_worker_waits_for_ui_cycle_confirmation(qtbot, qapp, repositories, tmp_path, decision):
    from PySide6.QtWidgets import QMessageBox
    from compras_tn.presentation.jobs import JobManager
    from compras_tn.domain.models import JobStatus
    facade, *_ = _facade(repositories, tmp_path)
    jobs = JobManager()
    executed = []
    results = []
    jobs.job_finished.connect(lambda job, result: results.append(result))
    def operation():
        executed.append('executed')
        return OperationResult.from_items([OperationItem(key='163519599', status=ItemStatus.SUCCEEDED)])
    job = jobs.submit('default', lambda progress, cancelled:
        facade._audited(request(7), operation, progress=progress))
    def prompt():
        return next((w for w in qapp.topLevelWidgets() if isinstance(w, QMessageBox)
                     and w.isVisible() and w.windowTitle() == 'Pasos anteriores pendientes'), None)
    from PySide6.QtCore import QTimer
    timer = QTimer()
    timer.setInterval(10)
    observed = []
    def answer():
        dialog = prompt()
        if dialog is None:
            return
        timer.stop()
        observed.append(list(executed))
        if decision == 'close':
            dialog.close()
        elif decision == 'cancel_job':
            jobs.cancel(job)
        else:
            button = next(b for b in dialog.buttons() if ('Sí, continuar' in b.text()) == (decision == 'continue'))
            button.click()
    timer.timeout.connect(answer)
    timer.start()
    qtbot.waitUntil(lambda: bool(results))
    assert observed == [[]]
    assert executed == (['executed'] if decision == 'continue' else [])
    assert results[0].status == (JobStatus.SUCCEEDED if decision == 'continue' else JobStatus.CANCELLED)
    qtbot.waitUntil(lambda: not jobs.has_running_jobs())


@pytest.mark.parametrize('source', ['manual', 'correo'])
def test_declining_download_never_downloads_or_marks_mail(repositories, tmp_path, source, monkeypatch):
    from compras_tn.domain.models import JobStatus, ScannedOrderMessage
    facade, mail, downloads, scanner = _facade(repositories, tmp_path)
    calls = []
    monkeypatch.setattr(downloads, 'download', lambda *args, **kwargs: pytest.fail('Download must wait for approval'))
    def progress(*args):
        pass
    progress.confirm_cycle = lambda message: calls.append(message) or False
    if source == 'manual':
        result = facade.download_orders(OperationRequest(kind='descarga_normal',
            items=[{'task_number':'163519599', 'order_number':'377745'}]), progress=progress)
    else:
        scanner.messages = [ScannedOrderMessage(external_id='cycle-mail',
            orders=[{'task_number':'163519599', 'order_number':'377745'}])]
        result = facade.scan_and_download_orders(PurchaseMode.BIENES, headless=True, progress=progress)
    assert len(calls) == 1
    assert result.status == JobStatus.CANCELLED
    assert scanner.marked == []


def test_supply_cycle_check_runs_before_first_download_click(tmp_path, monkeypatch):
    from compras_tn.infrastructure.automation.downloads import OrderPortalPage
    from compras_tn.application.task_cycle import CycleDeclined
    page = OrderPortalPage(SimpleNamespace(), tmp_path)
    monkeypatch.setattr(page, '_elements_now', lambda *args, **kwargs: [object(), object()])
    monkeypatch.setattr(page, '_button_key', lambda button, index: ['377745', '377746'][index])
    monkeypatch.setattr(page, '_click_element', lambda *args: pytest.fail('Must confirm before clicking download'))
    def progress(*args):
        pass
    def check(items):
        assert items == [{'order_number':'377745'}, {'order_number':'377746'}]
        raise CycleDeclined('cancelled')
    progress.check_cycle = check
    with pytest.raises(CycleDeclined):
        page.download_all_visible_results(progress=progress)


def test_task_record_with_shared_download_metadata_does_not_cross_other_task_orders():
    from compras_tn.application.task_cycle import targets
    task = TaskRecord(task_number='166697966', order_number='378584, 378592', payload={
        'task_numbers':['166697966','166698548'],
        'orders':[{'order_number':'378584'},{'order_number':'378592'}]})
    assert targets(task.model_dump(mode='json')) == {('166697966','378584'),('166697966','378592')}


def test_shared_orders_keep_all_tasks_when_input_is_a_download_result():
    from compras_tn.application.task_cycle import targets
    assert targets({'task_number':'166697966','task_numbers':['166697966','166698548'],
                    'order_number':'378592'}) == {('166697966','378592'),('166698548','378592')}
    assert targets({'task_number':'166697966','orders':[{'order_number':'378584'}]}) == {('166697966','378584')}


def test_shared_pdf_metadata_in_historical_workflow_does_not_warn_for_completed_steps(repositories):
    tasks = [TaskRecord(task_number='166697966',order_number='378584, 378592',payload={
        'task_numbers':['166697966','166698548'],
        'orders':[{'order_number':'378584'},{'order_number':'378592'}]}),
        TaskRecord(task_number='166698548',order_number='378592',payload={
        'task_numbers':['166697966','166698548'],
        'orders':[{'order_number':'378592'}]})]
    for stage in (4,5):
        req=OperationRequest(kind='actualizar_tareas', options={'cycle_stage':stage},
            items=[task.model_dump(mode='json') for task in tasks])
        run=repositories.start(req)
        repositories.finish(run,OperationResult.from_items([
            OperationItem(key=task.task_number,status=ItemStatus.SUCCEEDED) for task in tasks]))
    for number,numbers in [('378584',['166697966']),('378592',['166697966','166698548'])]:
        req=OperationRequest(kind='descarga_normal',items=[{'order_number':number}])
        run=repositories.start(req)
        repositories.finish(run,OperationResult.from_items([
            OperationItem(key=number,status=ItemStatus.SUCCEEDED,payload={
                'order_number':number,'task_numbers':numbers,'task_destinations':[
                    {'task_number':task,'preparation_status':'succeeded'} for task in numbers]})]))
    selected=OperationRequest(kind='actualizar_tareas',options={'cycle_stage':7},
        items=[task.model_dump(mode='json') for task in tasks])
    assert TaskCycle(repositories).warnings(selected) == ''
    tasks[0].payload['orders'].append({'order_number':'399999'})
    selected.items=[task.model_dump(mode='json') for task in tasks]
    warning=TaskCycle(repositories).warnings(selected)
    assert 'Tarea 166697966 · OC 399999:' in warning
    assert 'Tarea 166698548 · OC 399999:' not in warning
    assert 'OC 378584:' not in warning
    assert 'OC 378592:' not in warning
