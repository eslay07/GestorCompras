from types import SimpleNamespace

import pytest
from test_application_services import _facade
from test_purchase_order_preload import _draft

from compras_tn.domain.models import Supplier, OperationResult
from compras_tn.infrastructure.google_sheets import GoogleSheetsGateway


@pytest.mark.parametrize('sync_fails', [False, True])
def test_gateway_syncs_before_next_order_and_stops_on_failure(tmp_path, monkeypatch, sync_fails):
    from compras_tn.domain.models import SessionCredentials
    from compras_tn.infrastructure.automation.purchase_orders import SeleniumPurchaseOrderGateway
    from compras_tn.paths import AppPaths

    events = []
    class Page:
        def login_and_open_orders(self, credentials):
            pass
        def fill(self, draft):
            events.append('fill')
            return draft
        def save_once(self):
            events.append('save')
            return '374562'
        def open_fresh_form(self):
            events.append('fresh')
    gateway = SeleniumPurchaseOrderGateway(SimpleNamespace(get=lambda *a: a[-1]), AppPaths.from_root(tmp_path))
    monkeypatch.setattr(gateway, '_create_driver', lambda headless: SimpleNamespace(quit=lambda: None))
    monkeypatch.setattr(gateway, '_page', lambda driver: Page())
    def sync(draft, number):
        events.append('sync')
        if sync_fails:
            raise ConnectionError('offline')
    result = gateway.preload(SessionCredentials(username='test', email='test@example.com', password='test'),
                             [_draft(), _draft()], before_save=lambda draft: events.append('validate'), on_saved=sync)
    if sync_fails:
        assert events == ['fill', 'validate', 'save', 'sync']
        assert result.items[0].payload['order_number'] == '374562'
        assert result.items[1].status.value == 'skipped'
    else:
        assert events == ['fill', 'validate', 'save', 'sync', 'fresh', 'fill', 'validate', 'save', 'sync']


def test_eligibility_excludes_numeric_text_and_formula_oc(monkeypatch):
    rows = [['', '', '163687165', '', '', '', '', '', 'S/N', 'DEP', 'PERSONA', 'DETALLE']]
    for index, oc in enumerate([123456, '123457', '', '', '']):
        rows.append(['', f'A{index}', 'ITEM', 1, 'PROV', 2, oc])
    formulas = [[], [123456], ['123457'], ['=IF(TRUE,"","")'], [''], ['']]
    worksheet = SimpleNamespace(get=lambda name, **kwargs: formulas if name.startswith('G') else rows)
    gateway = GoogleSheetsGateway(SimpleNamespace(get=lambda *args: args[-1]))
    monkeypatch.setattr(gateway, '_worksheet', lambda name, **kwargs: worksheet)
    drafts = gateway.read_purchase_order_drafts()
    assert [a.code for a in drafts[0].articles] == ['A3', 'A4']


def test_ambiguous_save_stops_batch_without_opening_next_form(tmp_path, monkeypatch):
    from compras_tn.domain.models import SessionCredentials
    from compras_tn.infrastructure.automation.purchase_orders import SeleniumPurchaseOrderGateway
    from compras_tn.paths import AppPaths

    events = []
    class Page:
        def login_and_open_orders(self, credentials):
            pass
        def fill(self, draft):
            events.append('fill')
            return draft
        def save_once(self):
            events.append('save')
            raise TimeoutError('No llegó el número')
        def capture_diagnostic(self, *args):
            return ''
        def open_fresh_form(self):
            pytest.fail('No abandonar el resultado ambiguo para otra orden')
    gateway = SeleniumPurchaseOrderGateway(SimpleNamespace(get=lambda *a: a[-1]), AppPaths.from_root(tmp_path))
    monkeypatch.setattr(gateway, '_create_driver', lambda headless: SimpleNamespace(quit=lambda: None))
    monkeypatch.setattr(gateway, '_page', lambda driver: Page())
    result = gateway.preload(SessionCredentials(username='test', email='test@example.com', password='test'), [_draft(), _draft()])
    assert events == ['fill', 'save']
    assert [item.status.value for item in result.items] == ['failed', 'skipped']


def setup_facade(repositories, tmp_path):
    facade, *_ = _facade(repositories, tmp_path)
    repositories.save(Supplier(name='SEWRIMTEC', ruc='0991338144001', email_primary='test@example.com'))
    facade.sheets.drafts = [_draft()]
    return facade


def test_revalidate_rejects_new_article_and_nonempty_g(repositories, tmp_path):
    facade = setup_facade(repositories, tmp_path)
    original = facade._resolve_purchase_order_catalogs([_draft()])[0]
    facade._validate_oc_snapshot(original)
    facade.sheets.drafts[0].articles.append(original.articles[0].model_copy(update={'source_row': 3}))
    with pytest.raises(ValueError, match='conjunto de artículos'):
        facade._validate_oc_snapshot(original)
    facade.sheets.drafts = []
    with pytest.raises(ValueError, match='conjunto de artículos'):
        facade._validate_oc_snapshot(original)


def test_stale_saving_receipt_blocks_regeneration_after_restart(repositories, tmp_path):
    facade = setup_facade(repositories, tmp_path)
    draft = facade._resolve_purchase_order_catalogs([_draft()])[0]
    facade._prepare_oc_save(draft)
    another, *_ = _facade(repositories, tmp_path)
    another.sheets.drafts = [_draft()]
    with pytest.raises(ValueError, match='Recuperación pendiente'):
        another._validate_oc_snapshot(draft)
    assert not another.load_purchase_order_drafts()[0].is_valid


def test_pending_sync_recovery_requires_explicit_review(repositories, tmp_path):
    facade = setup_facade(repositories, tmp_path)
    draft = facade._resolve_purchase_order_catalogs([_draft()])[0]
    facade._record_oc_receipt(draft, 'pending', '374562')
    recorded = []
    facade.sheets.record_purchase_order = lambda d, n: recorded.append((d.task_number, n))
    assert len(facade.load_purchase_order_drafts()) == 1
    assert recorded == []
    facade.login('ana', 'memory-only')
    receipt, = facade.pending_oc_recoveries()
    facade.recover_purchase_order(receipt['key'], receipt['at'], number='374562', verified=True, reason='Comprobada en NAF')
    assert recorded == [('163687165', '374562')]
    assert facade.settings.get('oc_receipts', facade._oc_receipt_keys(draft)[0])['state'] == 'synced'


def test_sync_failure_keeps_number_in_persistent_receipt(repositories, tmp_path):
    facade = setup_facade(repositories, tmp_path)
    draft = facade._resolve_purchase_order_catalogs([_draft()])[0]
    def fail(*args):
        raise ConnectionError('sin conexión')
    facade.sheets.record_purchase_order = fail
    with pytest.raises(ConnectionError):
        facade._sync_saved_oc(draft, '374562')
    receipt = facade.settings.get('oc_receipts', facade._oc_receipt_keys(draft)[0])
    assert receipt['state'] == 'pending'
    assert receipt['number'] == '374562'
    with pytest.raises(ValueError, match='Recuperación pendiente'):
        facade._validate_oc_snapshot(draft)

@pytest.mark.parametrize('state', ['saving', 'pending', 'synced'])
def test_reviewed_block_can_be_reopened_without_writing_sheet(repositories, tmp_path, state):
    facade = setup_facade(repositories, tmp_path)
    facade.login('ana', 'memory-only')
    draft = facade._resolve_purchase_order_catalogs([_draft()])[0]
    facade._record_oc_receipt(draft, state, '376004' if state != 'saving' else '')
    receipt, = facade.pending_oc_recoveries(include_synced=True)
    facade.sheets.record_purchase_order = lambda *args: pytest.fail('Do not write G when releasing')
    facade.recover_purchase_order(receipt['key'], receipt['at'], reopen=True,
                                  verified=True, reason='Orden anterior anulada en NAF')
    stored = facade.settings.get('oc_receipts', receipt['key'])
    assert stored['state'] == 'released'
    assert stored['history'][-1]['state'] == state
    assert stored['audit']['action'] == 'reopen'
    assert stored['audit']['actor'] == 'ANA'
    assert facade.load_purchase_order_drafts()[0].is_valid


@pytest.mark.parametrize('verified,reason,eligible', [(False, 'anulada', True), (True, '', True), (True, 'anulada', False)])
def test_reopen_rejects_missing_review_or_occupied_sheet(repositories, tmp_path, verified, reason, eligible):
    facade = setup_facade(repositories, tmp_path)
    draft = facade._resolve_purchase_order_catalogs([_draft()])[0]
    facade._record_oc_receipt(draft, 'synced', '376004')
    receipt, = facade.pending_oc_recoveries(include_synced=True)
    if not eligible:
        facade.sheets.drafts = []
    with pytest.raises(ValueError):
        facade.recover_purchase_order(receipt['key'], receipt['at'], reopen=True, verified=verified, reason=reason)
    assert facade.settings.get('oc_receipts', receipt['key'])['state'] == 'synced'

def test_reopen_rejects_stale_receipt(repositories, tmp_path):
    facade = setup_facade(repositories, tmp_path)
    draft = facade._resolve_purchase_order_catalogs([_draft()])[0]
    facade._record_oc_receipt(draft, 'synced', '376004')
    receipt, = facade.pending_oc_recoveries(include_synced=True)
    facade._record_oc_receipt(draft, 'pending', '376005')
    with pytest.raises(ValueError, match='intento cambió'):
        facade.recover_purchase_order(receipt['key'], receipt['at'], reopen=True, verified=True, reason='anulada')
    assert facade.settings.get('oc_receipts', receipt['key'])['number'] == '376005'


def test_change_block_state_and_status_cell_open_selected_attempt(qtbot, repositories, tmp_path, monkeypatch):
    from compras_tn.presentation.jobs import JobManager
    from compras_tn.presentation.purchase_orders_page import PurchaseOrderPreloadPage
    facade = setup_facade(repositories, tmp_path)
    draft = facade._resolve_purchase_order_catalogs([_draft()])[0]
    facade._record_oc_receipt(draft, 'synced', '376004')
    page = PurchaseOrderPreloadPage(facade, JobManager())
    qtbot.addWidget(page)
    page.drafts = facade.load_purchase_order_drafts()
    page._render()
    state = page.table.cellWidget(0, 8)
    assert state.currentText() == 'Bloqueada'
    calls = []
    monkeypatch.setattr(page, 'set_row_state', lambda row, enabled:calls.append((row,enabled)))
    state.setCurrentIndex(0)
    assert calls == [(0, True)]


def test_table_block_and_unblock_need_no_reason(repositories,tmp_path):
    facade=setup_facade(repositories,tmp_path)
    draft=facade.load_purchase_order_drafts()[0]
    blocked=facade.set_purchase_order_enabled(draft,False)
    assert not blocked[0].is_valid
    enabled=facade.set_purchase_order_enabled(blocked[0],True)
    assert enabled[0].is_valid


def test_selected_recovery_uses_known_order_without_manual_input(repositories,tmp_path):
    facade=setup_facade(repositories,tmp_path)
    draft=facade.load_purchase_order_drafts()[0]
    facade._record_oc_receipt(draft,'pending','378517')
    receipt,=facade.pending_oc_recoveries()
    recorded=[]
    facade.sheets.record_purchase_order=lambda draft,number:recorded.append(number)
    result=facade.recover_selected_orders([receipt])
    assert recorded==['378517']
    assert result.items[0].status.value=='succeeded'


def test_selected_recovery_never_guesses_between_two_orders(repositories,tmp_path):
    facade=setup_facade(repositories,tmp_path)
    draft=facade.load_purchase_order_drafts()[0]
    facade._record_oc_receipt(draft,'saving')
    receipt,=facade.pending_oc_recoveries()
    receipt['candidates']=['378517','378522']
    facade.sheets.record_purchase_order=lambda *args:pytest.fail('Do not guess a saved OC')
    result=facade.recover_selected_orders([receipt])
    assert result.items[0].status.value=='failed'
    assert facade.settings.get('oc_receipts',receipt['key'])['state']=='saving'


def test_recovery_table_executes_only_checked_task_without_explanations(qtbot,repositories,tmp_path,monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDialog,QTableWidget,QPushButton,QPlainTextEdit,QLineEdit
    from compras_tn.presentation.jobs import JobManager
    from compras_tn.presentation.purchase_orders_page import PurchaseOrderPreloadPage
    facade=setup_facade(repositories,tmp_path)
    draft=facade.load_purchase_order_drafts()[0]
    facade._record_oc_receipt(draft,'pending','378517')
    jobs=JobManager()
    callbacks=[]
    monkeypatch.setattr(jobs,'submit',lambda kind,callback:callbacks.append(callback) or 'recover-selected')
    captured=[]
    monkeypatch.setattr(facade,'recover_selected_orders',lambda selected,*args:captured.extend(selected))
    def execute(dialog):
        assert not dialog.findChildren(QPlainTextEdit)
        assert not dialog.findChildren(QLineEdit)
        table=dialog.findChild(QTableWidget)
        assert table.rowCount()==1
        table.item(0,0).setCheckState(Qt.Checked)
        next(button for button in dialog.findChildren(QPushButton) if button.text()=='Ejecutar').click()
        return QDialog.Accepted
    monkeypatch.setattr(QDialog,'exec',execute)
    page=PurchaseOrderPreloadPage(facade,jobs)
    qtbot.addWidget(page)
    page.recover_pending()
    assert len(callbacks)==1
    callbacks[0](None,None)
    assert [receipt['number'] for receipt in captured]==['378517']


def test_approver_recovery_only_runs_selected_task(repositories,tmp_path):
    facade=setup_facade(repositories,tmp_path)
    draft=facade.load_purchase_order_drafts()[0]
    for number in ['378517','378522']:
        facade._ensure_approval_pending(draft,number)
    captured=[]
    facade.purchases=SimpleNamespace(recover_approvers=lambda credentials,entries,callback,**kwargs:
        captured.extend(entry['number'] for entry in entries) or OperationResult.from_items([]))
    selected=facade._oc_scope()+'378522'
    facade.recover_approvers(keys=[selected])
    assert captured==['378522']


def test_enabling_synced_block_restores_existing_number_without_new_order(repositories,tmp_path,monkeypatch):
    facade=setup_facade(repositories,tmp_path)
    draft=facade.load_purchase_order_drafts()[0]
    facade._record_oc_receipt(draft,'synced','378517')
    recorded=[]
    facade.sheets.record_purchase_order=lambda draft,number:recorded.append(number)
    monkeypatch.setattr(facade,'load_purchase_order_drafts',lambda *args:[])
    facade.set_purchase_order_enabled(draft,True)
    assert recorded==['378517']
