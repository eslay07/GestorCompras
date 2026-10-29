from types import SimpleNamespace

import pytest

from compras_tn.infrastructure.automation.downloads import OrderPortalPage
from compras_tn.infrastructure.automation.telcos import TasksPage


class Cell:
    def __init__(self, text):
        self.text = text


class Row:
    text = '123456 999999 Referencia 123456 Finalizada'
    def find_elements(self, *_):
        return [Cell('123456'), Cell('999999'), Cell('Referencia 123456'), Cell('Finalizada')]


def test_task_column_excludes_parent_and_observation():
    driver = SimpleNamespace(find_elements=lambda *_: [Cell('No. Tarea Padre'), Cell('No. Tarea'),
                                                        Cell('Observación'), Cell('Estado')])
    page = TasksPage(driver)
    assert page.row_number(Row()) == '999999'


def test_finalized_task_fails_before_wait(monkeypatch):
    page = TasksPage(object())
    page.current_task = '999999'
    monkeypatch.setattr(page, '_task_row', lambda: Row())
    monkeypatch.setattr(page, 'row_value', lambda *_: 'Finalizada')
    with pytest.raises(ValueError, match='finalizada'):
        page._row_control(['button'])


def test_company_redirect_after_queries_menu(monkeypatch, tmp_path):
    page = OrderPortalPage(object(), tmp_path)
    state = {'ready': False, 'selected': False}
    def find(locators, **_):
        if locators == page.ORDER_INPUT:
            return state['ready']
        return locators in (page.QUERIES, page.ORDER_QUERY_MENU)
    monkeypatch.setattr(page, '_find_now', find)
    monkeypatch.setattr(page, '_open_menu_item', lambda *args: 'company')
    def select():
        state.update(ready=True, selected=True)
    monkeypatch.setattr(page, '_select_company', select)
    monkeypatch.setattr(page, '_find', lambda *args, **kwargs: state['ready'])
    page._navigate_shell_to_orders()
    assert state['selected']


def test_modal_backdrop_is_not_loading():
    assert all(selector != '.ui-widget-overlay' for _, selector in TasksPage.BLOCKING_OVERLAYS)


@pytest.mark.parametrize('label,value,option_text,selected', [
    ('Proveedor', '1716726581001', '008052 - PROVEEDOR - 1716726581001', 'PROVEEDOR'),
    ('Solicita', 'PEREZ BARBERAN MARIA BELEN', '1542 - PEREZ BARBERAN MARIA BELEN', 'PEREZ BARBERAN MARIA BELEN'),
    ('Tipo', 'BIENES', 'BI-BIENES', 'BIENES'),
    ('Bodega', 'BQEF', 'BQEF - BODEGA PRINCIPAL QUITO ELOY ALFARO', 'BODEGA PRINCIPAL QUITO ELOY ALFARO'),
    ('No. Artículo', '10-101-270-681', '10-101-270-681 PLAUD NOTE PRO', '10-101-270-681'),
])
def test_supplier_option_replaced_during_search(monkeypatch, tmp_path, label, value, option_text, selected):
    from selenium.common.exceptions import StaleElementReferenceException

    from compras_tn.infrastructure.automation.purchase_orders import GoodsPurchaseOrderPage

    clicked = []
    page = GoodsPurchaseOrderPage(SimpleNamespace(execute_script=lambda *a: selected if clicked else ''), tmp_path)
    from selenium.webdriver.common.keys import Keys

    field = SimpleNamespace(is_enabled=lambda: True, click=lambda: None,
                            get_attribute=lambda name: None,
                            send_keys=lambda *a: clicked.append(True) if Keys.RETURN in a else None)
    class Option:
        def __init__(self, stale):
            self.stale = stale
        @property
        def text(self):
            if self.stale:
                raise StaleElementReferenceException('Angular replaced the option')
            return option_text
        def click(self):
            pytest.fail('El catálogo debe confirmarse con Enter')
        def get_attribute(self, name):
            return 'ng-option ng-option-marked' if name == 'class' else ''
    options = iter([[Option(True)], [Option(False)], []])
    monkeypatch.setattr(page, '_field_elements', lambda label: [field])
    monkeypatch.setattr(page, '_elements_now', lambda locators, **k:
                        [] if 'ng-select-loading' in str(locators) else next(options))
    def wait(predicate, description, timeout):
        for _ in range(4):
            result = predicate(None)
            if result:
                return result
        raise TimeoutError(description)
    monkeypatch.setattr(page, '_wait', wait)
    page._select_exact(label, value, error_code='catalogo', allow_unique_code=label in ('Proveedor', 'Bodega', 'No. Artículo'))
    assert clicked == [True]


def test_department_blurs_before_employee(monkeypatch):
    from selenium.webdriver.common.keys import Keys

    keys = []
    field = SimpleNamespace(get_attribute=lambda name: 'txtDepartment' if name == 'id' else 'Bodega', send_keys=lambda *a: keys.extend(a))
    suggestion = SimpleNamespace(text='Bodega', is_displayed=lambda: True,
                                 get_attribute=lambda name: 'autocomplete-active' if Keys.DOWN in keys else '')
    page = TasksPage(SimpleNamespace(find_elements=lambda *a: [] if Keys.RETURN in keys else [suggestion]))
    monkeypatch.setattr(page, 'set_text', lambda *a: None)
    monkeypatch.setattr(page, 'click_resolved', lambda *a, **k: None)
    monkeypatch.setattr(page, 'find', lambda *a, **k: field)
    monkeypatch.setattr(page, 'find_now', lambda *a, **k: field)
    def wait(predicate, *args):
        for _ in range(4):
            result = predicate(None)
            if result:
                return result
        raise TimeoutError(args)
    monkeypatch.setattr(page, 'wait', wait)
    monkeypatch.setattr(page, 'busy', lambda: False)
    page.select_autocomplete((('id', 'txtDepartment'),), 'BODEGA', 'Departamento')
    assert keys == [Keys.DOWN, Keys.RETURN, Keys.TAB]


def test_naf_recovers_service_redirect_without_resubmitting(monkeypatch, tmp_path):
    from selenium.webdriver.common.keys import Keys

    from compras_tn.domain.models import SessionCredentials
    from compras_tn.infrastructure.automation.downloads import PORTAL_URL

    page = OrderPortalPage(object(), tmp_path, login_timeout=100)
    navigated, waits, opened, events = [], [], [], []
    class Field:
        def __init__(self, name):
            self.name = name
        def send_keys(self, *keys):
            events.append((self.name, keys))
    monkeypatch.setattr(page, '_navigate', navigated.append)
    monkeypatch.setattr(page, 'wait_idle', lambda **k: None)
    monkeypatch.setattr(page, '_shell_landmark', lambda: False)
    monkeypatch.setattr(page, '_find_now', lambda locators, **kwargs: locators == page.USERNAME)
    monkeypatch.setattr(page, '_prepare_cas_execution', lambda _previous='': 'opaque-state')
    monkeypatch.setattr(
        page,
        '_write',
        lambda locators, value, *a, **k: (
            events.append(
                ('write_username' if locators == page.USERNAME else 'write_password', value)
            )
            or Field('username' if locators == page.USERNAME else 'password')
        ),
    )
    monkeypatch.setattr(page, '_click_element', lambda *_: pytest.fail('No debe pulsar Iniciar sesión'))
    monkeypatch.setattr(page, '_login_error', lambda: '')
    def wait(timeout, **_kwargs):
        waits.append(timeout)
        return 'company'
    monkeypatch.setattr(page, '_wait_for_shell', wait)
    monkeypatch.setattr(page, '_navigate_shell_to_orders', opened.append)
    page._login_and_open_orders(SessionCredentials(
        username='usuario_demo', email='usuario_demo@telconet.ec', password='test-only',
    ))
    assert navigated == [PORTAL_URL]
    assert events == [
        ('write_username', 'USUARIO_DEMO'),
        ('write_password', 'test-only'),
        ('password', (Keys.ENTER,)),
    ]
    assert waits == [100]
    assert opened == ['company']


def test_naf_retry_dialog_remains_transient_until_shell_is_ready(
    monkeypatch, tmp_path
):
    page = OrderPortalPage(SimpleNamespace(current_url='https://sites.telconet.ec/naf/compras/sso/check'), tmp_path, login_timeout=100)
    clicks = []
    landmarks = iter([False, False, False, "orders"])

    class Dialog:
        text = "No se pudo validar la sesión"

    monkeypatch.setattr(page, "_login_error", lambda: "")
    monkeypatch.setattr(page, "_shell_landmark", lambda: next(landmarks))
    monkeypatch.setattr(
        page,
        "_find_now",
        lambda locators, **_kwargs: Dialog()
        if locators in (page.SSO_RETRY_DIALOG, page.SSO_RETRY_YES)
        else False,
    )
    monkeypatch.setattr(page, "_click_element", lambda element: clicks.append(element))
    moments = iter(range(0, 200, 6))
    monkeypatch.setattr(
        "compras_tn.infrastructure.automation.downloads.time.monotonic",
        lambda: next(moments),
    )

    def wait(predicate, _description, _timeout):
        result = False
        while not result:
            result = predicate(page.driver)
        return result

    monkeypatch.setattr(page, "_wait", wait)

    assert page._wait_for_shell(100) == "orders"
    assert len(clicks) == 2


@pytest.mark.parametrize('initial_company', [False, True])
def test_goods_selects_company_before_or_after_goods(monkeypatch, tmp_path, initial_company):
    from compras_tn.infrastructure.automation.purchase_orders import GoodsPurchaseOrderPage

    page = GoodsPurchaseOrderPage(object(), tmp_path)
    state = {'company': initial_company, 'selected': False, 'form': False}
    def find(locators, **_):
        if locators == page.FORM_TITLE:
            return state['form']
        if locators == page.COMPANY_INPUT:
            return state['company']
        return locators in (page.MOVEMENTS, page.PURCHASE_ORDERS, page.GOODS)
    def open_menu(locators, description, outcomes):
        if locators == page.GOODS:
            if state['selected']:
                state['form'] = True
                return 'form'
            state['company'] = True
            assert (page.COMPANY_INPUT, 'company') in outcomes
            return 'company'
        return 'goods'
    def select():
        assert state['company']
        state.update(company=False, selected=True)
    monkeypatch.setattr(page, '_find_now', find)
    monkeypatch.setattr(page, '_navigate', lambda _url: (_ for _ in ()).throw(TimeoutError()))
    monkeypatch.setattr(page, '_open_menu_item', open_menu)
    monkeypatch.setattr(page, '_select_company', select)
    monkeypatch.setattr(page, '_find', lambda *a, **k: state['form'])
    page._navigate_shell_to_orders()
    assert state['selected'] and state['form']


def test_task_buttons_require_an_explicit_task_before_any_click():
    page = TasksPage(object())
    with pytest.raises(ValueError, match="consulte y seleccione"):
        page._row_control(["button"])
