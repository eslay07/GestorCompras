from html.parser import HTMLParser
from types import SimpleNamespace

from compras_tn.domain.models import TaskRecord, PurchaseMode, OperationRequest, OperationItem, ItemStatus, OperationResult
from compras_tn.domain.purchase_order_observations import normalize_observation
from compras_tn.infrastructure.download_report import render_download_report
from compras_tn.infrastructure.automation.purchase_orders import GoodsPurchaseOrderPage
from test_application_services import _facade


def test_fraction_normalization_preserves_mixed_numbers_and_accents():
    assert normalize_observation('CLAVO 2½” × ¼ — NIÑO Ø10 m²') == 'CLAVO 2 1/2" x 1/4 - NIÑO DIA10 m2'


def test_catalog_description_is_normalized_in_form_without_changing_source(tmp_path, monkeypatch):
    from test_purchase_order_preload import _draft
    draft = _draft()
    draft.articles[0].description = 'CLAVO 2 ½”'
    field = SimpleNamespace(get_attribute=lambda key:{'value':'CLAVO 2 ½”'}.get(key), is_enabled=lambda:True)
    page = GoodsPurchaseOrderPage(object(), tmp_path)
    monkeypatch.setattr(page, '_field_elements', lambda label:[field] if label == 'Descripción' else [])
    written = []
    monkeypatch.setattr(page, '_set_text', lambda label, value, **kwargs:written.append((label,value)))
    page._normalize_article_description(draft.articles[0], 0)
    assert written == [('Descripción', 'CLAVO 2 1/2"')]
    assert draft.articles[0].description == 'CLAVO 2 ½”'


def test_download_report_has_one_row_per_order_sorted_by_task():
    request = OperationRequest(kind='descarga_normal', items=[
        {'order_number':'41','task_numbers':['200','100']},
        {'order_number':'39','task_number':'200'},
        {'order_number':'40','task_number':'100'}])
    result = OperationResult.from_items([OperationItem(key=n, status=ItemStatus.SUCCEEDED,
        payload={'supplier':'PROVEEDOR'}) for n in ['41','39','40']])
    report = render_download_report(request,result)
    class Cells(HTMLParser):
        def __init__(self):
            super().__init__(); self.values=[]; self.active=False
        def handle_starttag(self, tag, attrs):
            if tag=='td': self.active=True
        def handle_endtag(self, tag):
            if tag=='td': self.active=False
        def handle_data(self, value):
            if self.active:self.values.append(value)
    cells=Cells(); cells.feed(report.html)
    pairs=[tuple(cells.values[i:i+2]) for i in range(0,len(cells.values),4)]
    assert pairs==[('40','100'),('41','200 - 100'),('39','200')]
    assert [number for number,task in pairs].count('41')==1


def test_download_only_task_is_not_filled_with_undownloaded_oc_from_general(repositories,tmp_path):
    facade,*_=_facade(repositories,tmp_path)
    facade.sheets.read_task_orders=lambda numbers:{'166698853':[
        {'order_number':'378517','supplier':'P','approvers':['UNO']}]}
    task=TaskRecord(task_number='166698853',origin='descargas',purchase_mode=PurchaseMode.BIENES)
    updated=facade.refresh_workflow_approvers([task])[0]
    assert not any(order['order_number'] for order in updated.payload['orders'])


def test_orchestrator_sync_only_passes_downloads_and_never_calls_oc_reconciliation(qtbot,repositories,tmp_path,monkeypatch):
    from compras_tn.presentation.workflows_page import WorkflowRunner
    from compras_tn.presentation.jobs import JobManager
    facade,*_=_facade(repositories,tmp_path)
    for origin,number in [('descargas','166698853'),('carga_oc_automatica','166698548')]:
        repositories.enqueue([TaskRecord(task_number=number,origin=origin,purchase_mode=PurchaseMode.BIENES,
            order_number='378517',supplier='P')])
    jobs=JobManager()
    runner=WorkflowRunner(facade,jobs,PurchaseMode.BIENES)
    qtbot.addWidget(runner)
    runner.refresh()
    assert {task.origin for task in runner.tasks}=={'descargas','carga_oc_automatica'}
    assert runner.source.findData('carga_oc_automatica')>=0
    runner.source.blockSignals(True)
    runner.source.setCurrentText('descargas')
    runner.source.blockSignals(False)
    runner.refresh()
    assert [task.origin for task in runner.tasks]==['descargas']
    monkeypatch.setattr(facade,'reconcile_oc_tasks',lambda: (_ for _ in ()).throw(AssertionError('Do not import OC creation tasks')))
    captured=[]
    monkeypatch.setattr(facade,'refresh_workflow_approvers',lambda tasks:captured.extend(tasks) or tasks)
    callbacks=[]
    monkeypatch.setattr(jobs,'submit',lambda kind,callback:callbacks.append(callback) or 'sync-test')
    runner.import_oc()
    callbacks[0](None,None)
    assert [task.origin for task in captured]==['descargas']


import pytest

@pytest.mark.parametrize('origin', ['descargas','carga_oc_automatica','correo','manual'])
def test_sync_routes_to_selected_origin_and_preserves_order_associations(repositories,tmp_path,monkeypatch,origin):
    from compras_tn.application.task_orders import task_orders
    facade,*_=_facade(repositories,tmp_path)
    for source,number in [('descargas','378517'),('carga_oc_automatica','378522'),('correo','378523'),('manual','378524')]:
        repositories.enqueue([TaskRecord(task_number='166698853',origin=source,purchase_mode=PurchaseMode.BIENES,
            order_number=number,supplier='P')])
    reconciled=[]
    monkeypatch.setattr(facade,'reconcile_oc_tasks',lambda:reconciled.append(True) or [])
    facade.sheets.read_task_orders=lambda numbers:{'166698853':[
        {'order_number':number,'supplier':'P','approvers':['APROBADOR']} for number in ['378517','378522','378523','378524']]}
    result=facade.synchronize_workflow_origin(origin,PurchaseMode.BIENES)
    expected={'descargas':'378517','carga_oc_automatica':'378522','correo':'378523','manual':'378524'}
    assert [task.origin for task in result]==[origin]
    assert [row['order_number'] for row in task_orders(result[0])]==[expected[origin]]
    assert bool(reconciled)==(origin=='carga_oc_automatica')
    for source,number in expected.items():
        saved,=repositories.list_pending(source)
        assert [row['order_number'] for row in task_orders(saved)]==[number]


def test_workflow_completion_does_not_consume_other_module_same_task(repositories,tmp_path,monkeypatch):
    from compras_tn.domain.models import WorkflowDefinition
    facade,*_=_facade(repositories,tmp_path)
    for source,number in [('descargas','378517'),('carga_oc_automatica','378522')]:
        repositories.enqueue([TaskRecord(task_number='166698853',origin=source,purchase_mode=PurchaseMode.BIENES,
            order_number=number,supplier='P')])
    monkeypatch.setattr(facade,'reconcile_oc_tasks',lambda:[])
    task,=repositories.list_pending('descargas')
    result=facade.execute_workflow(WorkflowDefinition(name='Prueba'),[task],headless=True)
    assert result.items[0].status==ItemStatus.SUCCEEDED
    assert repositories.list_pending('descargas')==[]
    assert len(repositories.list_pending('carga_oc_automatica'))==1


def test_sync_completion_preserves_the_selected_origin(qtbot,repositories,tmp_path,monkeypatch):
    from compras_tn.presentation.workflows_page import WorkflowRunner
    from compras_tn.presentation.jobs import JobManager
    facade,*_=_facade(repositories,tmp_path)
    runner=WorkflowRunner(facade,JobManager(),PurchaseMode.BIENES)
    qtbot.addWidget(runner)
    runner.source.blockSignals(True)
    runner.source.setCurrentIndex(runner.source.findData('carga_oc_automatica'))
    runner.source.blockSignals(False)
    runner.oc_scan_job='sync-completed'
    runner._mail_imported('sync-completed',[])
    assert runner.source.currentData()=='carga_oc_automatica'
