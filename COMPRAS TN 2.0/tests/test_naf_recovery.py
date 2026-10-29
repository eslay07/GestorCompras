from types import SimpleNamespace

import pytest
import requests
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
from test_grouped_orders import consolidate_orders, draft, gateway, sheet_rows
from test_oc_critical_safety import setup_facade

from compras_tn.domain.models import SessionCredentials
from compras_tn.infrastructure.automation.downloads import (
    PORTAL_URL,
    NafCredentialsRequired,
    OrderPortalPage,
    SeleniumOrderDownloadGateway,
)
from compras_tn.infrastructure.automation.purchase_orders import (
    GOODS_PURCHASE_ORDER_URL,
    GoodsPurchaseOrderPage,
    PurchaseOrderValidationError,
)
from compras_tn.paths import AppPaths


@pytest.mark.parametrize('partial', [False, True])
def test_response_lost_after_write_rereads_before_retry(monkeypatch, partial):
    sheets, worksheet = gateway(monkeypatch, sheet_rows())
    merged, = consolidate_orders([draft(), draft('161516364', 7349)])
    real_write = worksheet.batch_update
    calls = []
    def unreliable(updates, **kwargs):
        calls.append([u['range'] for u in updates])
        real_write(updates[:1] if partial and len(calls) == 1 else updates, **kwargs)
        if len(calls) == 1:
            raise requests.ConnectionError('response lost')
    worksheet.batch_update = unreliable
    monkeypatch.setattr('compras_tn.infrastructure.google_sheets.time.sleep', lambda _: None)
    sheets.record_purchase_order(merged, '375235')
    assert calls == ([['G7347', 'G7349'], ['G7349']] if partial else [['G7347', 'G7349']])
    assert worksheet.rows[1][6] == worksheet.rows[3][6] == '375235'


@pytest.mark.parametrize('change', ['formula', 'order', 'article'])
def test_conflict_after_partial_write_is_not_overwritten(monkeypatch, change):
    sheets, worksheet = gateway(monkeypatch, sheet_rows())
    merged, = consolidate_orders([draft(), draft('161516364', 7349)])
    calls = []
    def interrupted(updates, **kwargs):
        calls.append(updates)
        worksheet.rows[1][6] = '375235'
        if change == 'article':
            worksheet.rows[3][1] = 'NEW'
        else:
            worksheet.rows[3][6] = '=1' if change == 'formula' else '375236'
        raise requests.Timeout('response lost')
    worksheet.batch_update = interrupted
    monkeypatch.setattr('compras_tn.infrastructure.google_sheets.time.sleep', lambda _: None)
    with pytest.raises(ValueError):
        sheets.record_purchase_order(merged, '375235')
    assert len(calls) == 1


def test_retry_budget_is_three(monkeypatch):
    sheets, _ = gateway(monkeypatch, sheet_rows())
    calls = []
    def fail(*args):
        calls.append(1)
        raise requests.Timeout('offline')
    monkeypatch.setattr(sheets, '_record_purchase_order_attempt', fail)
    monkeypatch.setattr('compras_tn.infrastructure.google_sheets.time.sleep', lambda _: None)
    with pytest.raises(requests.Timeout):
        sheets.record_purchase_order(draft(), '375235')
    assert len(calls) == 3


@pytest.mark.parametrize('status,retries', [(429, 2), (503, 2), (400, 1), (403, 1)])
def test_only_transient_api_failures_retry(monkeypatch, status, retries):
    import json

    from gspread.exceptions import APIError

    sheets, _ = gateway(monkeypatch, sheet_rows())
    calls = []
    response = requests.Response()
    response.status_code = status
    response._content = json.dumps({'error': {'code': status, 'message': 'test'}}).encode()
    def attempt(*args):
        calls.append(1)
        if len(calls) == 1:
            raise APIError(response)
    monkeypatch.setattr(sheets, '_record_purchase_order_attempt', attempt)
    monkeypatch.setattr('compras_tn.infrastructure.google_sheets.time.sleep', lambda _: None)
    if retries == 1:
        with pytest.raises(APIError):
            sheets.record_purchase_order(draft(), '375235')
    else:
        sheets.record_purchase_order(draft(), '375235')
    assert len(calls) == retries


def test_partial_success_response_retries_only_unwritten_cells(monkeypatch):
    sheets, worksheet = gateway(monkeypatch, sheet_rows())
    merged, = consolidate_orders([draft(), draft('161516364', 7349)])
    real_write = worksheet.batch_update
    calls = []
    def partial_write(updates, **kwargs):
        calls.append([u['range'] for u in updates])
        real_write(updates[:1], **kwargs)
    worksheet.batch_update = partial_write
    monkeypatch.setattr('compras_tn.infrastructure.google_sheets.time.sleep', lambda _: None)
    sheets.record_purchase_order(merged, '375235')
    assert calls == [['G7347', 'G7349'], ['G7349']]


def test_discard_requires_review_and_preserves_history(repositories, tmp_path):
    facade = setup_facade(repositories, tmp_path)
    facade.login('ana', 'memory-only')
    original = facade.load_purchase_order_drafts()[0]
    facade._prepare_oc_save(original)
    receipt, = facade.pending_oc_recoveries()
    with pytest.raises(ValueError, match='Confirme'):
        facade.recover_purchase_order(receipt['key'], receipt['at'], discard=True)
    facade.recover_purchase_order(receipt['key'], receipt['at'], discard=True, verified=True, reason='Revisada consulta NAF; sin orden')
    updated = facade.settings.get('oc_receipts', receipt['key'])
    assert updated['history'][0]['state'] == 'saving'
    assert updated['audit']['action'] == 'discard'
    assert facade.load_purchase_order_drafts()[0].is_valid
    facade._prepare_oc_save(original)
    assert len(facade.settings.get('oc_receipts', receipt['key'])['history']) == 2


def test_candidates_are_only_for_review_and_recovery_is_explicit(repositories, tmp_path):
    facade = setup_facade(repositories, tmp_path)
    paths = AppPaths.from_root(tmp_path / 'data')
    folder = paths.diagnostics / 'precarga_oc'
    folder.mkdir(parents=True)
    original = facade.load_purchase_order_drafts()[0]
    for number in ('375235', '375236'):
        (folder / f'{number}-oc_{original.task_number}.txt').write_text(
            f'URL: https://sites.telconet.ec/naf/compras/movimientos/orden-compra/bienes/{number}\nTransacción realizada correctamente', encoding='utf-8')
    facade.purchases = SimpleNamespace(app_paths=paths)
    facade._prepare_oc_save(original)
    receipt, = facade.pending_oc_recoveries()
    assert receipt['candidates'] == ['375235', '375236']
    assert receipt['number'] == ''
    assert not facade.load_purchase_order_drafts()[0].is_valid
    facade.login('ana', 'memory-only')
    synced = []
    facade.sheets.record_purchase_order = lambda d, n: synced.append(n)
    facade.recover_purchase_order(receipt['key'], receipt['at'], number='375236', verified=True, reason='Verificada orden conservada')
    assert synced == ['375236']
    assert facade.settings.get('oc_receipts', receipt['key'])['history'][-1]['audit']['number'] == '375236'
    with pytest.raises(ValueError, match='cambió'):
        facade.recover_purchase_order(receipt['key'], receipt['at'], number='375235', verified=True, reason='stale UI')


def test_runtime_uses_existing_store_database_without_creating_one(tmp_path, monkeypatch):
    monkeypatch.delenv('COMPRAS_TN_DATA_DIR', raising=False)
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    root = tmp_path / 'Packages/PythonSoftwareFoundation.Python.3.13_test/LocalCache/Local/ComprasTN/2.0'
    root.mkdir(parents=True)
    (root / 'compras_tn.db').touch()
    assert AppPaths.default().root == root.resolve()
    normal = tmp_path / 'ComprasTN/2.0'
    normal.mkdir(parents=True)
    (normal / 'compras_tn.db').touch()
    with pytest.raises(RuntimeError, match='varias bases'):
        AppPaths.default()
    monkeypatch.setenv('COMPRAS_TN_DATA_DIR', str(root))
    assert AppPaths.default().root == root.resolve()


def test_stable_generic_cas_restores_service_without_resubmitting(monkeypatch, tmp_path):
    driver = SimpleNamespace(current_url='https://cas.telconet.ec/cas/login')
    page = OrderPortalPage(driver, tmp_path)
    monkeypatch.setattr(page, '_shell_landmark', lambda: False)
    monkeypatch.setattr(page, '_login_error', lambda: '')
    monkeypatch.setattr(page, '_find_now', lambda locators, **_: locators == page.USERNAME)
    navigations = []
    def navigate(url):
        navigations.append(url)
        driver.current_url = url
    monkeypatch.setattr(page, '_navigate', navigate)
    monkeypatch.setattr(page, '_auth_transition', lambda _: None)
    moments = iter([0, 4, 5, 9])
    monkeypatch.setattr('compras_tn.infrastructure.automation.downloads.time.monotonic', lambda: next(moments))
    def wait(predicate, *args):
        for _ in range(4):
            predicate(driver)
    monkeypatch.setattr(page, '_wait', wait)
    with pytest.raises(NafCredentialsRequired):
        page._wait_for_shell(100)
    assert navigations == [PORTAL_URL]


def test_dashboard_is_authenticated_with_closed_menu(monkeypatch, tmp_path):
    page = OrderPortalPage(SimpleNamespace(current_url='https://sites.telconet.ec/naf/compras/dashboard'), tmp_path)
    monkeypatch.setattr(page, '_find_now', lambda locators, **_: 'Dashboard' in str(locators))
    assert page._shell_landmark() == 'dashboard'


@pytest.mark.parametrize('path,expected', [
    ('/naf/compras/movimientos/orden-compra/bienes/375235', {'375235'}),
    ('/naf/compras/movimientos/orden-compra/bienes/375235/edit', set()),
    ('/naf/compras/movimientos/orden-compra/bienes?number=375235', set()),
    ('/naf/compras/other/375235', set()),
])
def test_save_number_uses_only_exact_order_route(monkeypatch, tmp_path, path, expected):
    page = GoodsPurchaseOrderPage(SimpleNamespace(current_url='https://sites.telconet.ec' + path), tmp_path)
    monkeypatch.setattr(page, '_elements_now', lambda _: [])
    assert page._saved_numbers() == expected


def test_slow_redirect_is_observed_without_navigation(monkeypatch, tmp_path):
    driver = SimpleNamespace(current_url='https://cas.telconet.ec/cas/login?ticket=secret')
    page = OrderPortalPage(driver, tmp_path)
    monkeypatch.setattr(page, '_shell_landmark', lambda: False)
    monkeypatch.setattr(page, '_login_error', lambda: '')
    monkeypatch.setattr(page, '_find_now', lambda *a, **k: False)
    monkeypatch.setattr(page, '_toggle_menu_now', lambda: False)
    monkeypatch.setattr(page, '_navigate', lambda _: pytest.fail('Do not interrupt redirect'))
    def wait(predicate, *args):
        for i in range(10):
            driver.current_url = f'https://sites.telconet.ec/naf/compras/sso/check?ticket={i}'
            assert not predicate(driver)
        return 'dashboard'
    monkeypatch.setattr(page, '_wait', wait)
    assert page._wait_for_shell(100) == 'dashboard'


def test_explicit_credential_rejection_is_immediate(monkeypatch, tmp_path):
    page = OrderPortalPage(object(), tmp_path)
    monkeypatch.setattr(page, '_login_error', lambda: 'Credenciales incorrectas')
    with pytest.raises(PermissionError):
        page._wait_for_shell(100)


def test_flow_execution_error_requests_immediate_retry(monkeypatch, tmp_path):
    class Password:
        def get_attribute(self, _name):
            return ""

    driver = SimpleNamespace(
        current_url=(
            "https://cas.telconet.ec/cas/login?service=naf&"
            "exception.message=Error+decoding+flow+execution"
        )
    )
    page = OrderPortalPage(driver, tmp_path)
    monkeypatch.setattr(page, "_login_error", lambda: "")
    monkeypatch.setattr(page, "_shell_landmark", lambda: False)
    monkeypatch.setattr(
        page,
        "_find_now",
        lambda locators, **_kwargs: Password()
        if locators == page.PASSWORD
        else locators == page.USERNAME,
    )
    monkeypatch.setattr(page, "_cas_execution_fingerprint", lambda: "new-state")
    monkeypatch.setattr(page, "_auth_transition", lambda _state: None)
    monkeypatch.setattr(
        page,
        "_wait",
        lambda predicate, _description, _timeout: predicate(driver),
    )

    with pytest.raises(NafCredentialsRequired, match="formulario nuevo"):
        page._wait_for_shell(100, submitted_execution="old-state")


@pytest.mark.parametrize("headless", [False, True])
@pytest.mark.parametrize(
    "auth_module",
    ["descargas_oc", "descargas_abastecimiento", "carga_automatica_oc"],
)
def test_shared_login_retries_new_cas_state_without_fixed_sleeps(
    monkeypatch, tmp_path, caplog, headless, auth_module
):
    page = OrderPortalPage(
        SimpleNamespace(),
        tmp_path,
        login_attempts=3,
        auth_module=auth_module,
        headless=headless,
    )
    tokens = iter(["state-1", "state-2"])
    submissions = []

    class Password:
        def send_keys(self, key):
            submissions.append(key)

    monkeypatch.setattr(page, "_navigate", lambda _url: None)
    monkeypatch.setattr(page, "wait_idle", lambda **_kwargs: None)
    monkeypatch.setattr(page, "_shell_landmark", lambda: False)
    monkeypatch.setattr(page, "_wait", lambda *_args, **_kwargs: "cas")
    monkeypatch.setattr(page, "_prepare_cas_execution", lambda _previous="": next(tokens))
    writes = []
    monkeypatch.setattr(
        page,
        "_write",
        lambda locators, value, _description: writes.append((locators, value))
        or Password(),
    )
    outcomes = iter([NafCredentialsRequired("nuevo estado"), "dashboard"])

    def wait_for_shell(_timeout, **_kwargs):
        result = next(outcomes)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(page, "_wait_for_shell", wait_for_shell)
    opened = []
    monkeypatch.setattr(page, "_navigate_shell_to_orders", opened.append)

    page._login_and_open_orders(
        SessionCredentials(
            username="usuario@telconet.ec",
            email="usuario@telconet.ec",
            password="secret-test-value",
        )
    )

    assert len(submissions) == 2
    assert len(writes) == 4
    assert page._submitted_executions == {"state-1", "state-2"}
    assert opened == ["dashboard"]
    assert "secret-test-value" not in caplog.text
    assert "state-1" not in caplog.text


def test_shared_login_attempt_budget_is_clamped_to_three(tmp_path):
    assert OrderPortalPage(object(), tmp_path, login_attempts=0).login_attempts == 1
    assert OrderPortalPage(object(), tmp_path, login_attempts=99).login_attempts == 3


def test_submitted_cas_state_is_never_reused(monkeypatch, tmp_path):
    page = OrderPortalPage(SimpleNamespace(), tmp_path)
    page._submitted_executions.add("same-state")
    monkeypatch.setattr(page, "_cas_execution_fingerprint", lambda: "same-state")

    def wait(predicate, description, _timeout):
        assert predicate(page.driver) is False
        raise TimeoutError(description)

    monkeypatch.setattr(page, "_wait", wait)
    with pytest.raises(TimeoutError):
        page._fresh_cas_execution()


def test_goods_waits_for_permissions_without_reloading_authenticated_shell(monkeypatch, tmp_path):
    page = GoodsPurchaseOrderPage(object(), tmp_path)
    navigations = []
    monkeypatch.setattr(page, "_find_now", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(page, "_navigate", navigations.append)
    monkeypatch.setattr(page, "_wait_for_any", lambda *_args, **_kwargs: "form")
    monkeypatch.setattr(
        page,
        "_open_menu_item",
        lambda *_args, **_kwargs: pytest.fail("No debe abrir el menú"),
    )

    page._navigate_shell_to_orders("dashboard")

    assert navigations == []


@pytest.mark.parametrize(
    "kind,normal,supply,expected",
    [
        ("descarga_oc", False, True, False),
        ("descarga_abastecimiento", False, True, True),
    ],
)
def test_each_download_flow_uses_its_own_hidden_mode(
    tmp_path, kind, normal, supply, expected
):
    class Settings:
        def get(self, namespace, key, default=None):
            values = {
                ("downloads", "headless"): normal,
                ("downloads", "abastecimiento_headless"): supply,
            }
            return values.get((namespace, key), default)

    gateway = SeleniumOrderDownloadGateway(
        Settings(),
        object(),
        app_paths=AppPaths.from_root(tmp_path / "appdata"),
    )
    request = SimpleNamespace(kind=kind, options={})
    assert gateway._headless_for(request) is expected


def test_explicit_download_hidden_mode_overrides_module_default(tmp_path):
    settings = SimpleNamespace(get=lambda *_args, **_kwargs: True)
    gateway = SeleniumOrderDownloadGateway(
        settings,
        object(),
        app_paths=AppPaths.from_root(tmp_path / "appdata"),
    )
    request = SimpleNamespace(kind="descarga_abastecimiento", options={"headless": False})
    assert gateway._headless_for(request) is False


def test_auth_transitions_never_log_url_secrets(monkeypatch, tmp_path, caplog):
    import logging
    logger = logging.getLogger("compras_tn.infrastructure.automation.downloads")
    monkeypatch.setattr(logger, "disabled", False)
    monkeypatch.setattr(logger, "propagate", True)

    page = OrderPortalPage(SimpleNamespace(current_url='https://cas.telconet.ec/cas/login?ticket=PRIVATE'), tmp_path)
    with caplog.at_level(logging.INFO):
        page._auth_transition('Redirección NAF en curso')
    assert 'tiempo=' in caplog.text and 'PRIVATE' not in caplog.text
    from compras_tn.security import sanitize_text
    assert 'PRIVATE' not in sanitize_text('ticket=PRIVATE cookie=PRIVATE')


def test_recovery_dialog_cancel_never_syncs_or_selects_candidate(qtbot, repositories, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QComboBox, QDialog

    from compras_tn.presentation.jobs import JobManager
    from compras_tn.presentation.purchase_orders_page import PurchaseOrderPreloadPage

    facade = setup_facade(repositories, tmp_path)
    facade._prepare_oc_save(facade.load_purchase_order_drafts()[0])
    receipt, = facade.pending_oc_recoveries()
    receipt['candidates'] = ['375235', '375236']
    monkeypatch.setattr(facade, 'pending_oc_recoveries', lambda **kwargs: [receipt])
    monkeypatch.setattr(facade, 'recover_purchase_order', lambda *a, **k: pytest.fail('Cancel must not sync'))
    def cancel(dialog):
        choices = dialog.findChildren(QComboBox)
        from PySide6.QtWidgets import QTableWidget, QPlainTextEdit, QLineEdit
        from PySide6.QtCore import Qt
        assert len(choices) == 1
        table = dialog.findChild(QTableWidget)
        assert table.rowCount() == 1
        assert table.item(0, 0).checkState() == Qt.Unchecked
        assert not dialog.findChildren(QPlainTextEdit)
        assert not dialog.findChildren(QLineEdit)
        return QDialog.Rejected
    monkeypatch.setattr(QDialog, 'exec', cancel)
    page = PurchaseOrderPreloadPage(facade, JobManager())
    qtbot.addWidget(page)
    page.recover_pending()
    assert not page.recovery_job


@pytest.mark.parametrize('result', ['stale', 'click_timeout', 'old', 'conflict', 'intercepted'])
def test_save_never_reclicks_and_requires_new_coherent_number(monkeypatch, tmp_path, result):
    driver = SimpleNamespace(current_url='https://sites.telconet.ec/naf/compras/movimientos/orden-compra/bienes/400001')
    page = GoodsPurchaseOrderPage(driver, tmp_path, query_timeout=1)
    page._verified_observation = 'verified'
    monkeypatch.setattr(page, '_observation_matches', lambda _: True)
    monkeypatch.setattr(page, '_notifications', lambda: [])
    # Geometry/side-menu interaction has its own real Chrome regression test.
    monkeypatch.setattr(page, '_prepare_form_control', lambda *_: None)
    clicks = []
    readings = []
    def click():
        clicks.append(1)
        if result == 'intercepted':
            from selenium.common.exceptions import ElementClickInterceptedException
            raise ElementClickInterceptedException('menu covers button')
        if result == 'click_timeout':
            raise TimeoutException('response lost after submitted')
    def numbers():
        readings.append(1)
        if not clicks or result == 'old':
            return {'400001'}
        if result == 'stale' and len(readings) == 2:
            raise StaleElementReferenceException('replaced')
        return {'400001', '400002'} if result == 'conflict' else {'400002'}
    monkeypatch.setattr(page, '_find', lambda *a, **k: SimpleNamespace(click=click))
    monkeypatch.setattr(page, '_saved_numbers', numbers)
    if result == 'intercepted':
        with pytest.raises(PurchaseOrderValidationError, match='NAF impidio'):
            page.save_once()
    elif result in ('old', 'conflict'):
        with pytest.raises(PurchaseOrderValidationError, match='inequívoca'):
            page.save_once()
    else:
        assert page.save_once() == '400002'
    assert clicks == [1]
