import json
import os
from types import SimpleNamespace

import pytest

from compras_tn.application.task_orders import task_orders, normalize_orders, missing_order_data
from compras_tn.application.workflows import WorkflowEngine
from compras_tn.application.workflow_repair import repair_workflow
from compras_tn.domain.models import FlowStep, TaskRecord, WorkflowDefinition, PurchaseMode, PurchaseOrderDraft, PurchaseOrderArticle
from compras_tn.infrastructure.document_files import inspect_file, select_copies, file_types, add_type, pdf_content_key
from compras_tn.infrastructure.automation.downloads import SeleniumOrderDownloadGateway
from compras_tn.infrastructure.automation.purchase_orders import pending_approvers, GoodsPurchaseOrderPage, PurchaseOrderValidationError
from compras_tn.infrastructure.google_sheets import GoogleSheetsGateway
from compras_tn.infrastructure.portable import export_profile, merge_profile


class Settings:
    def __init__(self): self.values = {}
    def get(self, ns, key, default=None): return self.values.get((ns, key), default)
    def set(self, ns, key, value): self.values[ns, key] = value
    def list_namespace(self, ns): return {key: value for (namespace, key), value in self.values.items() if namespace == ns}


def pdf(path, text, metadata="version"):
    stream = f"BT /F1 12 Tf 40 700 Td ({text}) Tj ET".encode()
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
        b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream',
        f'<< /Producer ({metadata}) >>'.encode()]
    result = b'%PDF-1.4\n'
    offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(result))
        result += f'{i} 0 obj\n'.encode() + obj + b'\nendobj\n'
    start = len(result)
    result += f'xref\n0 {len(objects)+1}\n0000000000 65535 f \n'.encode()
    result += b''.join(f'{offset:010} 00000 n \n'.encode() for offset in offsets[1:])
    result += f'trailer << /Size {len(objects)+1} /Root 1 0 R /Info 6 0 R >>\nstartxref\n{start}\n%%EOF'.encode()
    path.write_bytes(result)
    return path


def test_pdf_duplicates_keep_latest_but_preserve_different_order_and_amount(tmp_path):
    paths = [pdf(tmp_path/'old.pdf', 'ORDEN DE COMPRA 377630 TOTAL 20', 'old'),
             pdf(tmp_path/'new.pdf', 'ORDEN DE COMPRA 377630 TOTAL 20', 'new'),
             pdf(tmp_path/'changed.pdf', 'ORDEN DE COMPRA 377630 TOTAL 21'),
             pdf(tmp_path/'another.pdf', 'ORDEN DE COMPRA 377631 TOTAL 20')]
    for index, path in enumerate(paths): os.utime(path, ns=(1000000000, 1000000000 + index))
    assert pdf_content_key(paths[0]) == pdf_content_key(paths[1])
    assert inspect_file(paths[0])['sha256'] != inspect_file(paths[1])['sha256']
    definition = next(t for t in file_types(Settings()) if t['id'] == 'orden')
    chosen, omitted = select_copies([inspect_file(p) for p in paths], definition)
    assert {p['path'] for p in chosen} == {str(p.resolve()) for p in paths[1:]}
    assert omitted[0]['kept_path'] == str(paths[1].resolve())


def test_custom_type_extensions_and_default_preservation(tmp_path):
    from compras_tn.infrastructure.document_files import matches_type
    settings = Settings()
    custom = add_type(settings, 'Certificado', 'certificado', extensions=['PDF'], copies='latest_identical', comparison='exact')
    assert matches_type(tmp_path/'certificado.PDF', custom)
    assert not matches_type(tmp_path/'certificado.docx', custom)
    edited = add_type(settings, 'Certificación', 'certificado', identifier=custom['id'])
    assert edited['id'] == custom['id']
    assert next(t for t in file_types(settings) if t['id'] == 'cotizacion')['copies'] == 'all'
    assert next(t for t in file_types(settings) if t['id'] == 'orden')['copies'] == 'latest_identical'


def test_exact_and_unreadable_copies_and_date_tie(tmp_path):
    paths = [tmp_path/n for n in ['b.pdf', 'a.pdf', 'other.pdf']]
    for index, path in enumerate(paths):
        path.write_bytes(b'not a pdf' if index < 2 else b'different')
        os.utime(path, ns=(1000000000, 1000000000))
    chosen, omitted = select_copies([inspect_file(p) for p in paths], dict(copies='latest_identical', comparison='pdf_text'))
    assert {p['path'] for p in chosen} == {str(p.resolve()) for p in paths[1:]}
    assert len(omitted) == 1


def test_multiple_orders_render_one_text_operation_and_missing_names_block_everything():
    calls = []
    executor = SimpleNamespace(execute=lambda action, params, context: calls.append((action, params)))
    task = TaskRecord(task_number='166573896', payload={'orders': [
        dict(order_number='377630', supplier='Proveedor A', approvers=['PERSONA UNO']),
        dict(order_number='377631', supplier='Proveedor B', approvers=['PERSONA DOS'])]})
    workflow = WorkflowDefinition(name='Seguimiento', steps=[FlowStep(action_id='abrir_seguimiento'),
        FlowStep(action_id='escribir_seguimiento', params={'texto':'OC {orden_compra} {proveedor}: {aprobadores}'}),
        FlowStep(action_id='guardar_seguimiento'), FlowStep(action_id='cerrar_mensaje_ok')])
    WorkflowEngine(executor).execute(workflow, task)
    assert [a for a, p in calls].count('guardar_seguimiento') == 1
    assert calls[1][1]['texto'] == 'OC 377630 Proveedor A: PERSONA UNO\nOC 377631 Proveedor B: PERSONA DOS'
    task.payload['orders'][1]['approvers'] = []
    calls.clear()
    with pytest.raises(ValueError, match='377631'):
        WorkflowEngine(executor).execute(workflow, task)
    assert not calls


def test_orders_are_persisted_and_source_refresh_preserves_manual_edits(repositories):
    inbox = repositories
    task = TaskRecord(task_number='166573896', origin='carga_oc_automatica', purchase_mode=PurchaseMode.BIENES)
    inbox.synchronize_oc_task(task, True)
    orders = [dict(order_number='377630', supplier='Proveedor A', approvers=['UNO']),
              dict(order_number='377631', supplier='Proveedor B', approvers=['DOS'])]
    inbox.update_task_orders(task, orders)
    inbox.synchronize_oc_task(task, True)
    assert task_orders(inbox.list_pending()[0]) == orders
    with pytest.raises(ValueError, match='contradictorios'):
        normalize_orders([orders[0], dict(order_number='377630', supplier='Distinto')])


@pytest.mark.parametrize('supplier,expected', [('COMERCIAL KYWI S.A.', 'ORDEN 377630 - COMERCIAL KYWI.pdf'),
    ('', 'ORDEN 377630.pdf'), ('  UNO   DOS TRES ', 'ORDEN 377630 - UNO DOS.pdf')])
def test_download_rename_only(tmp_path, supplier, expected):
    path = tmp_path/'download.pdf'
    path.write_bytes(b'PDF')
    target = SeleniumOrderDownloadGateway._rename(path, '377630', supplier)
    assert target.name == expected
    assert target.read_bytes() == b'PDF'
    second = tmp_path/'second.pdf'
    second.write_bytes(b'OTHER')
    alternative = SeleniumOrderDownloadGateway._rename(second, '377630', supplier)
    assert alternative.stem == target.stem + ' (1)'
    assert target.read_bytes() == b'PDF'


def test_pending_names_only_and_order():
    assert pending_approvers([['1','165 - PROAÑO AYABACA HUGO IVAN','-', 'POR APROBAR'],
        ['2','50 - TOPIC GRANADOS MARION TOMISLAV','-', 'POR AUTORIZAR'],
        ['3','99 - YA APROBADO','-', 'APROBADO']]) == ['PROAÑO AYABACA HUGO IVAN', 'TOPIC GRANADOS MARION TOMISLAV']


def test_ambiguous_approval_never_clicks_again():
    page = object.__new__(GoodsPurchaseOrderPage)
    page._saved_numbers = lambda: {'377630'}
    page._elements_now = lambda *a: []
    page._find = lambda *a, **kw: pytest.fail('Must not click/send again')
    with pytest.raises(PurchaseOrderValidationError, match='no se repitió'):
        page.send_and_read_approval('377630', lambda *a: None, 'ambiguous')


def test_final_confirmation_is_repaired_and_draft_not_committed():
    flow = WorkflowDefinition(name='Carga', steps=[FlowStep(action_id='subir_archivo')])
    repaired, notes = repair_workflow(flow)
    assert repaired.steps[-1].action_id == 'cerrar_mensaje_ok'
    assert notes and len(flow.steps) == 1
    assert repair_workflow(repaired)[1] == []


def test_import_conflicting_workflow_preserves_both_without_duplicates(repositories, database):
    from compras_tn.infrastructure.db.models import WorkflowRow
    from compras_tn.infrastructure.portable import merge_profile
    with database.session() as session:
        session.add(WorkflowRow(name='Flujo local', mode='bienes', version=1, enabled=True,
                                steps_json='[{"action_id":"consultar","params":{}}]', updated_at=__import__('datetime').datetime.now(__import__('datetime').UTC)))
    profile = {'format':1, 'settings':[], 'tables':{'workflow_definitions':[
        dict(name='Flujo local', mode='bienes', version=1, enabled=True,
             steps_json='[{"action_id":"abrir_tareas_personales","params":{}}]')]}}
    assert merge_profile(database.path if hasattr(database, 'path') else database.engine.url.database, profile)['added'] == 1
    assert merge_profile(database.path if hasattr(database, 'path') else database.engine.url.database, profile)['added'] == 0
    from sqlalchemy import select
    with database.session() as session:
        imported = session.scalar(select(WorkflowRow).where(WorkflowRow.name.contains('(importado')))
        imported.enabled = False
    assert merge_profile(database.path, profile)['added'] == 1
    assert merge_profile(database.path, profile)['added'] == 0


@pytest.mark.parametrize('header,cell,ok', [('', '', True), ('APROBADORES PENDIENTES', 'UNO', True),
    ('OTRA COLUMNA', '', False), ('', '=A1', False)])
def test_column_o_verified_and_protected(header, cell, ok):
    state = {'O1': header, 'O7347': cell}
    writes = []
    class Worksheet:
        def get(self, name, **kw): return [[state.get(name, '')]]
        def batch_update(self, updates, **kw):
            writes.extend(updates)
            for update in updates: state[update['range']] = update['values'][0][0]
    gateway = GoogleSheetsGateway(Settings())
    gateway._worksheet = lambda *a, **kw: Worksheet()
    checked = []
    gateway.record_purchase_order = lambda draft, number: checked.append(number)
    draft = PurchaseOrderDraft(task_number='166573896', supplier='UNO', articles=[PurchaseOrderArticle(
        code='A', description='ITEM', quantity=1, unit_price=1, source_row=7347)])
    if ok:
        gateway.record_approvers(draft, '377630', ['PERSONA UNO', 'PERSONA DOS'])
        assert state['O7347'] == 'PERSONA UNO, PERSONA DOS'
        assert state['O1'] == 'APROBADORES PENDIENTES'
        assert checked == ['377630']
    else:
        with pytest.raises(ValueError): gateway.record_approvers(draft, '377630', ['PERSONA UNO'])
        assert writes == []


def test_approval_recovery_after_sheet_failure_does_not_send_again():
    from compras_tn.application.services import ApplicationFacade
    facade = object.__new__(ApplicationFacade)
    facade.settings = Settings()
    facade._oc_scope = lambda: 'scope:'
    names = ['PERSONA UNO', 'PERSONA DOS']
    calls = []
    def send(number, stage, previous):
        calls.append(number)
        stage('sending', [])
        stage('sent', [])
        stage('read', names)
        return names
    page = SimpleNamespace(send_and_read_approval=send)
    def fail(*args): raise ConnectionError('O unavailable')
    facade.sheets = SimpleNamespace(record_approvers=fail)
    draft = PurchaseOrderDraft(task_number='166573896', supplier='Proveedor')
    with pytest.raises(ConnectionError): facade._approve_saved_oc(draft, '377630', page)
    assert facade.settings.get('oc_approvals', 'scope:377630')['state'] == 'read'
    facade.sheets.record_approvers = lambda *args: None
    facade._approve_saved_oc(draft, '377630', page)
    assert calls == ['377630']
    assert facade.settings.get('oc_approvals', 'scope:377630')['state'] == 'synced'


def test_orders_dialog_saves_pairs_and_uses_provider_dropdown(qtbot):
    from compras_tn.presentation.task_orders_dialog import TaskOrdersDialog
    dialog = TaskOrdersDialog('166573896', [], ['Proveedor A', 'Proveedor B'])
    qtbot.addWidget(dialog)
    dialog.table.item(0, 0).setText('377630')
    dialog.table.cellWidget(0, 1).setCurrentText('Proveedor A')
    dialog.table.item(0, 2).setText('PERSONA UNO, PERSONA DOS')
    dialog.add_row(dict(order_number='377631', supplier='Proveedor B', approvers=['TRES']))
    rows = dialog.value()
    assert rows[0]['approvers'] == ['PERSONA UNO', 'PERSONA DOS']
    assert rows[1]['supplier'] == 'Proveedor B'


@pytest.mark.parametrize('guide', ['Observación', 'Seguimiento', 'Adjuntar archivo', 'Reasignación',
    'Consultar datos', 'Ver historial', 'Ver archivos', 'Pausa', 'Iniciar y pausar'])
def test_every_guide_can_run_two_tasks_without_pending_confirmation(guide, qtbot, monkeypatch):
    import compras_tn.presentation.workflows_page as page_module
    from PySide6.QtWidgets import QDialog
    class Dialog:
        def __init__(self, definition, **kw): self.definition = definition
        def setWindowTitle(self, text): pass
        def exec(self): return QDialog.Accepted
        def value(self):
            return FlowStep(action_id=self.definition.action_id, params={p.name:
                (p.default or (p.options[0] if p.options else 'Texto de prueba')) for p in self.definition.parameters})
    monkeypatch.setattr(page_module, 'StepDialog', Dialog)
    editor = page_module.WorkflowEditor(SimpleNamespace(list_workflows=lambda mode: []), PurchaseMode.BIENES, lambda: None)
    qtbot.addWidget(editor)
    editor.preset.setCurrentText(guide)
    editor.create_guided()
    workflow = editor.value()
    assert not repair_workflow(workflow)[1]
    calls = []
    executor = SimpleNamespace(execute=lambda action, params, context: calls.append((context['numero_tarea'], action)))
    for number in ('166573896', '166573897'):
        WorkflowEngine(executor).execute(workflow, TaskRecord(task_number=number))
        assert [action for task, action in calls if task == number] == [step.action_id for step in workflow.steps]
