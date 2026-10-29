import json
from types import SimpleNamespace

import pytest
import requests

from compras_tn.infrastructure.automation.downloads import OrderPortalPage
from compras_tn.infrastructure.google_sheets import GoogleSheetsGateway


def test_preload_enables_network_diagnostics(monkeypatch, tmp_path):
    from compras_tn.infrastructure.automation.purchase_orders import SeleniumPurchaseOrderGateway
    calls = []
    monkeypatch.setattr(
        "compras_tn.infrastructure.automation.purchase_orders.create_corporate_browser",
        lambda *args, **kwargs: calls.append((args, kwargs)) or object(),
    )
    gateway = object.__new__(SeleniumPurchaseOrderGateway)
    gateway.settings = SimpleNamespace(get=lambda *args: 25)
    gateway.app_paths = SimpleNamespace(root=tmp_path)
    gateway._create_driver(True)
    assert calls[0][1]["network_diagnostics"] is True
    assert calls[0][1]["naf_navigation"] is True


def test_order_menu_waits_for_lazy_route_without_repeated_click(monkeypatch, tmp_path):
    page = OrderPortalPage(SimpleNamespace(), tmp_path)
    clicks, waits = [], []
    monkeypatch.setattr(page, "_find_now", lambda locators: locators == page.ORDER_QUERY_MENU)
    monkeypatch.setattr(page, "_click", lambda *args, **kwargs: clicks.append(args))
    def pending(*args, **kwargs):
        waits.append(kwargs["timeout"])
        raise TimeoutError("lazy bundle pending")
    monkeypatch.setattr(page, "_wait_for_any", pending)
    with pytest.raises(TimeoutError, match="recursos pendientes"):
        page._open_menu_item(page.ORDER_QUERY_MENU, "consulta", ((page.ORDER_INPUT, "orders"),))
    assert len(clicks) == 1
    assert len(waits) == 1 and waits[0] >= 120


def test_goods_keeps_existing_authenticated_menu(monkeypatch, tmp_path):
    from compras_tn.infrastructure.automation.purchase_orders import GoodsPurchaseOrderPage
    page = GoodsPurchaseOrderPage(SimpleNamespace(), tmp_path)
    state = {"form": False}
    monkeypatch.setattr(page, '_ensure_navigation_open', lambda: None)
    monkeypatch.setattr(page, '_find_now', lambda locators, **_: state['form']
        if locators == page.FORM_TITLE else locators in (page.MOVEMENTS, page.PURCHASE_ORDERS, page.GOODS))
    monkeypatch.setattr(page, '_navigate', lambda _: pytest.fail('No debe recargar la sesion autenticada'))
    def opened(locators, *_args):
        if locators == page.GOODS:
            state['form'] = True
            return 'form'
        return 'goods'
    monkeypatch.setattr(page, '_open_menu_item', opened)
    monkeypatch.setattr(page, '_find', lambda *_args, **_: state['form'])
    page._navigate_shell_to_orders('movements')
    assert state['form']


def test_network_diagnostic_excludes_sso_tickets_and_headers(tmp_path):
    events = [
        {"method": "Network.requestWillBeSent", "params": {
            "type": "Document", "requestId": "1", "request": {
                "url": "https://sites.telconet.ec/naf/compras/sso/check?ticket=SECRET",
                "headers": {"Cookie": "SECRET"}}}},
        {"method": "Network.responseReceived", "params": {
            "type": "Document", "response": {"status": 502, "mimeType": "text/html"}}},
        {"method": "Network.loadingFailed", "params": {
            "requestId": "1", "errorText": "net::ERR_CONNECTION_RESET"}},
    ]
    driver = SimpleNamespace(get_log=lambda _: [
        {"message": json.dumps({"message": event})} for event in events])
    result = OrderPortalPage(driver, tmp_path)._network_diagnostic()
    assert "502" in result and "ERR_CONNECTION_RESET" in result
    assert "SECRET" not in result and "ticket" not in result and "Cookie" not in result


def test_blank_sso_timeout_reports_stage_without_retrying_download(monkeypatch, tmp_path):
    driver = SimpleNamespace(current_url="https://sites.telconet.ec/naf/compras/sso/check?ticket=SECRET")
    page = OrderPortalPage(driver, tmp_path)
    def blocked(_credentials):
        raise TimeoutError("waiting for shell")
    monkeypatch.setattr(page, "_login_and_open_orders", blocked)
    monkeypatch.setattr(page, "capture_diagnostic", lambda *_args: "diagnostico.txt")
    with pytest.raises(TimeoutError, match="SSO") as error:
        page.login_and_open_orders(SimpleNamespace(password="password"))
    assert "SECRET" not in str(error.value)
    assert "diagnostico.txt" in str(error.value)


@pytest.mark.parametrize("recover", [True, False])
def test_general_read_retries_resets_without_writes(monkeypatch, recover):
    gateway = GoogleSheetsGateway(SimpleNamespace(get=lambda *args: "GENERAL"))
    calls = []
    def rows(*args, **kwargs):
        calls.append(kwargs)
        if not recover or len(calls) < 3:
            raise requests.ConnectionError("ConnectionResetError 10054")
        return []
    monkeypatch.setattr(gateway, "_rows", rows)
    monkeypatch.setattr("compras_tn.infrastructure.google_sheets.time.sleep", lambda _: None)
    if recover:
        assert gateway.read_task_catalog() == {}
    else:
        with pytest.raises(ConnectionError, match="GENERAL"):
            gateway.read_task_catalog()
    assert len(calls) == 3
    assert all(call == {"range_name": "B:L"} for call in calls)


@pytest.mark.parametrize("recover", [True, False])
def test_oc_initial_sheet_read_retries_complete_snapshot(monkeypatch, recover):
    gateway = GoogleSheetsGateway(SimpleNamespace())
    calls = []
    def read():
        calls.append(1)
        if not recover or len(calls) < 3:
            raise requests.ConnectionError("ConnectionResetError 10054")
        return []
    monkeypatch.setattr(gateway, '_read_purchase_order_drafts_once', read)
    monkeypatch.setattr('compras_tn.infrastructure.google_sheets.time.sleep', lambda _: None)
    if recover:
        assert gateway.read_purchase_order_drafts() == []
    else:
        with pytest.raises(ConnectionError, match='No se pudo validar la hoja'):
            gateway.read_purchase_order_drafts()
    assert len(calls) == 3
