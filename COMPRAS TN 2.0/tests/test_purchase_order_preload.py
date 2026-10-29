from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from test_application_services import _facade

from compras_tn.application.catalog_matching import match_supplier_nickname
from compras_tn.domain.models import (
    ItemStatus,
    OperationItem,
    OperationRequest,
    OperationResult,
    PurchaseMode,
    PurchaseOrderArticle,
    PurchaseOrderDraft,
    SessionCredentials,
    Supplier,
)
from compras_tn.infrastructure.automation.purchase_orders import (
    GoodsPurchaseOrderPage,
    SeleniumPurchaseOrderGateway,
    build_observation,
    expiration_date,
    normalize_observation,
)
from compras_tn.infrastructure.download_report import render_download_report
from compras_tn.infrastructure.google_sheets import GoogleSheetsGateway
from compras_tn.paths import AppPaths


def test_general_sheet_parser_groups_each_task_by_supplier() -> None:
    rows = [
        ["", "", "TAREA #163687165", "", "", "", "", "", "S/N", "MERCADEO", "PAUL LUGMAÑA", "GAD AMBATO COMSECA."],
        ["", "USB-01", "CABLE DATOS EXTENSIÓN USB", 1, "SEWRIMTEC", 6, ""],
        ["", "USB-02", "ADAPTADOR USB", 2, "SEWRIMTEC", 3.5, ""],
        ["", "MON-01", "MONITOR", 1, "OTRO PROVEEDOR", 120, ""],
    ]

    drafts = GoogleSheetsGateway.parse_purchase_order_rows(rows)

    assert len(drafts) == 2
    assert drafts[0].task_number == "163687165"
    assert drafts[0].supplier == "SEWRIMTEC"
    assert drafts[0].subtotal == Decimal("13.0")
    assert drafts[0].is_valid
    assert [article.code for article in drafts[0].articles] == ["USB-01", "USB-02"]


def test_general_sheet_parser_omits_rows_with_existing_order_or_create_code() -> None:
    rows = [
        ["", "", "TAREA 163687166", "", "", "", "", "", "", "SISTEMAS", "ANA", "RENOVACIÓN"],
        ["", "CREAR CODIGO", "EQUIPO", 1, "PROVEEDOR", 10, "12345"],
    ]

    drafts = GoogleSheetsGateway.parse_purchase_order_rows(rows)

    assert drafts == []


def test_general_sheet_parser_only_detects_complete_rows_and_keeps_real_row_number() -> None:
    rows = [
        ["", "", "TAREA 163687166", "", "", "", "", "", "S/N", "SISTEMAS", "ANA", "RENOVACIÓN"],
        ["", "SIN-PRECIO", "NO LISTO", 1, "PROVEEDOR", "", ""],
        ["", "LISTO-01", "", 2, "Proveedor Uno", "5.50", ""],
        ["", "CON-OC", "YA GENERADO", 1, "Proveedor Uno", 10, "12345"],
    ]

    drafts = GoogleSheetsGateway.parse_purchase_order_rows(rows, start_row=7346)

    assert len(drafts) == 1
    assert [article.code for article in drafts[0].articles] == ["LISTO-01"]
    assert drafts[0].articles[0].description == "LISTO-01"
    assert drafts[0].source_rows == [7348]


def test_general_sheet_parser_omits_task_without_any_ready_article() -> None:
    rows = [
        ["", "", "TAREA 163687166", "", "", "", "", "", "S/N", "SISTEMAS", "ANA", "RENOVACIÓN"],
        ["", "ART-01", "SIN CANTIDAD", "", "PROVEEDOR", 10, ""],
        ["", "ART-02", "SIN PROVEEDOR", 1, "", 10, ""],
    ]

    assert GoogleSheetsGateway.parse_purchase_order_rows(rows, start_row=7346) == []


def test_general_sheet_parser_reads_currency_with_comma_thousands_separator() -> None:
    rows = [
        ["", "", "TAREA 164448987", "", "", "", "", "", "S/N", "SISTEMAS", "ANA", "COMPRA"],
        ["", "10-111-261-266", "LIBERNOVO MAXIS AIRFLOW", 1, "ONLYCOMP", "$2,265.680", ""],
    ]

    draft = GoogleSheetsGateway.parse_purchase_order_rows(rows, start_row=7346)[0]

    assert draft.articles[0].unit_price == Decimal("2265.680")


def test_purchase_order_eligibility_requires_authenticated_sheet(monkeypatch: Any) -> None:
    values = {
        ("google", "google_creds"): "",
        ("google", "google_sheet_id"): "demo-sheet-id",
        ("google", "google_oc_sheet_name"): "GENERAL",
    }

    class Settings:
        def get(self, namespace: str, key: str, default: Any = None) -> Any:
            return values.get((namespace, key), default)

    class Response:
        text = (
            "OBSERVACION,CODIGO,DESCRIPCION,CANTIDAD,PROVEEDOR,PRECIO,OC,HISTORICO,"
            "PEDIDO,DEPARTAMENTO,SOLICITANTE,DETALLE\n"
            ",,TAREA 163687199,,,,,,,SISTEMAS,ANA,COMPRA DE PRUEBA\n"
            ",ART-01,ARTICULO DE PRUEBA,2,PROVEEDOR,5.50,,,S/N,SISTEMAS,ANA,"
            "COMPRA DE PRUEBA\n"
        )
        headers = {"Content-Type": "text/csv; charset=utf-8"}

        @staticmethod
        def raise_for_status() -> None:
            return None

    requested: list[dict[str, Any]] = []

    def get(_url: str, **kwargs: Any) -> Response:
        requested.append(kwargs)
        return Response()

    monkeypatch.setattr("compras_tn.infrastructure.google_sheets.requests.get", get)

    with pytest.raises(ValueError, match="credenciales Google"):
        GoogleSheetsGateway(Settings()).read_purchase_order_drafts()
    assert requested == []


def _draft() -> PurchaseOrderDraft:
    return PurchaseOrderDraft(
        task_number="163687165",
        supplier="SEWRIMTEC",
        ruc="0991338144001",
        requester="PAUL LUGMAÑA",
        pedido="S/N",
        department="MERCADEO",
        detail="GAD AMBATO COMSECA.",
        articles=[
            PurchaseOrderArticle(
                code="USB-01",
                description="CABLE DATOS EXTENSIÓN USB 3.0 MACHO A MACHO TIPO A-A 1.5 MTS",
                quantity=Decimal("1"),
                unit_price=Decimal("6"),
                source_row=2,
            )
        ],
    )


def test_observation_is_automatic_and_normalizes_unsupported_controls() -> None:
    observation = build_observation(_draft())
    assert observation.startswith("TAREA #163687165//PEDIDO:S/N//MERCADEO:GAD AMBATO COMSECA.")
    assert "SOLIC. PAUL LUGMAÑA // REFER. COTIZ. SEWRIMTEC DETALLE:\n\n" in observation
    assert observation.endswith("1 SEWRIMTEC $6.00")
    assert normalize_observation("Texto\u0000 “válido” — sí") == 'Texto "válido" - sí'


def test_expiration_keeps_day_or_uses_last_day_of_next_month() -> None:
    assert expiration_date(datetime(2026, 1, 31)).date().isoformat() == "2026-02-28"
    assert expiration_date(datetime(2026, 12, 15)).date().isoformat() == "2027-01-15"


def test_aliases_merge_all_articles_per_task_and_ruc(repositories, tmp_path):
    facade, *_ = _facade(repositories, tmp_path)
    repositories.save(Supplier(name='PROVEEDOR OFICIAL', nickname='ONLYCOMP', nickname_2='OCOMP',
                               ruc='1716726581001', email_primary='test@example.com'))
    header = ['', '', '164448987', '', '', '', '', '', 'S/N', 'GTN', 'PERSONA', 'COMPRA']
    rows = [header,
            ['', 'A', 'GRABADORA', 1, 'ONLYCOMP', '233.62'],
            ['', 'B', 'SILLA', 1, 'onlycomp', '2265.68'],
            ['', 'C', 'OTRO', 2, 'OCOMP', 3],
            ['', 'D', 'INCOMPLETO', 1, 'ONLYCOMP', '']]
    drafts = facade._resolve_purchase_order_catalogs(GoogleSheetsGateway.parse_purchase_order_rows(rows, start_row=7346))
    assert len(drafts) == 1
    assert drafts[0].source_rows == [7347, 7348, 7349]
    assert [a.code for a in drafts[0].articles] == ['A', 'B', 'C']
    observation = build_observation(drafts[0])
    assert 'COTIZ. ONLYCOMP DETALLE:\n\n' in observation
    assert len(observation.split('DETALLE:\n\n')[1].splitlines()) == 3
    assert 'PROVEEDOR OFICIAL' not in observation


def test_naf_fills_every_article_and_observation_without_saving(monkeypatch, tmp_path):
    draft = _draft()
    draft.articles.append(draft.articles[0].model_copy(update={'code': 'SILLA', 'source_row': 3}))
    page = GoodsPurchaseOrderPage(object(), tmp_path)
    calls = []
    monkeypatch.setattr(page, '_select_exact', lambda label, value, **kw: calls.append((label, value, kw.get('index', 0))))
    monkeypatch.setattr(page, '_set_text', lambda label, value, **kw: calls.append((label, value, kw.get('index', 0))))
    monkeypatch.setattr(page, '_set_date', lambda *args: None)
    monkeypatch.setattr(page, '_set_checkbox', lambda *args: None)
    monkeypatch.setattr(page, '_field_elements', lambda label: [object(), object()])
    monkeypatch.setattr(page, 'fill_observation', lambda text: calls.append(('observation', text, 0)))
    page.fill(draft)
    assert [c for c in calls if c[0] == 'No. Artículo'] == [('No. Artículo', 'USB-01', 0), ('No. Artículo', 'SILLA', 1)]
    assert [c[2] for c in calls if c[0] == 'Precio'] == [0, 1]
    assert calls[-1][0] == 'observation'
    assert len(calls[-1][1].split('DETALLE:\n\n')[1].splitlines()) == 2


@pytest.mark.parametrize('conflict', [False, True])
def test_writeback_all_article_rows_and_never_overwrites(monkeypatch, conflict):
    rows = [['', '', '164448987', '', '', '', '', '', 'S/N', 'GTN', 'PERSONA', 'COMPRA'],
            ['', 'A', 'GRABADORA', 1, 'ONLYCOMP', 233.62],
            ['', 'B', 'SILLA', 1, 'ONLYCOMP', 2265.68]]
    draft = GoogleSheetsGateway.parse_purchase_order_rows(rows, start_row=7346)[0]
    cells = {'G7347': '', 'G7348': '=123' if conflict else ''}
    writes = []
    class Worksheet:
        def get(self, range_name, **kwargs):
            if range_name.startswith('A7346:'):
                return [list(row[:6]) + [cells.get(f'G{7346+i}', row[6] if len(row)>6 else '')]
                        + list(row[7:]) for i, row in enumerate(rows)]
            return [[cells[range_name]]]
        def batch_update(self, updates, **kwargs):
            writes.extend(updates)
            cells.update({u['range']: u['values'][0][0] for u in updates})
    gateway = GoogleSheetsGateway(SimpleNamespace(get=lambda *args: args[-1]))
    monkeypatch.setattr(gateway, '_worksheet', lambda name, **kwargs: Worksheet())
    if conflict:
        with pytest.raises(ValueError, match='no se sobrescribió'):
            gateway.record_purchase_order(draft, '374562')
        assert writes == []
    else:
        gateway.record_purchase_order(draft, '374562')
        assert cells == {'G7347': '374562', 'G7348': '374562'}
        assert [u['range'] for u in writes] == ['G7347', 'G7348']


def test_purchase_order_page_exposes_only_the_save_action() -> None:
    save_locators = " ".join(value for _kind, value in GoodsPurchaseOrderPage.SAVE)
    assert "Guardar" in save_locators
    assert not hasattr(GoodsPurchaseOrderPage, "APPROVE")


def test_purchase_order_driver_respects_hidden_browser_option(
    monkeypatch: Any, tmp_path: Any
) -> None:
    created: list[Any] = []

    class Settings:
        def get(self, _namespace: str, _key: str, default: Any = None) -> Any:
            return default

    class Driver:
        def execute_cdp_cmd(self, _command: str, _parameters: Any) -> dict:
            return {}

        def set_page_load_timeout(self, _timeout: int) -> None:
            return None

        def set_script_timeout(self, _timeout: int) -> None:
            return None

    def create(*, options: Any, service: Any = None) -> Driver:
        created.append(options)
        return Driver()

    monkeypatch.setattr(
        "compras_tn.infrastructure.automation.purchase_orders.webdriver.Chrome", create
    )
    gateway = SeleniumPurchaseOrderGateway(
        Settings(), AppPaths.from_root(tmp_path / "appdata")
    )

    gateway._create_driver(True)
    gateway._create_driver(False)

    assert "--headless=new" in created[0].arguments
    assert "--headless=new" not in created[1].arguments
    assert all(options.page_load_strategy == "none" for options in created)


def test_purchase_order_login_stops_if_cas_keeps_showing_login(
    monkeypatch: Any, tmp_path: Any
) -> None:
    from selenium.webdriver.common.keys import Keys

    page = GoodsPurchaseOrderPage(
        SimpleNamespace(), tmp_path, login_timeout=100, login_attempts=1
    )
    writes: list[str] = []
    keys: list[tuple[str, str]] = []
    sleeps: list[int] = []
    waits: list[int] = []
    class Field:
        def __init__(self, name: str):
            self.name = name
        def send_keys(self, key: str) -> None:
            keys.append((self.name, key))
    username = Field("username")
    password = Field("password")
    monkeypatch.setattr(page, "_navigate", lambda _url: None)
    monkeypatch.setattr(page, "wait_idle", lambda **_kwargs: None)
    monkeypatch.setattr(page, "_shell_landmark", lambda: False)
    monkeypatch.setattr(page, "_prepare_cas_execution", lambda _previous="": "state-1")
    monkeypatch.setattr(
        page,
        "_find",
        lambda locators, _description, **_kwargs: username
        if locators == page.USERNAME
        else password,
    )
    monkeypatch.setattr(
        page,
        "_write",
        lambda locators, value, _description: writes.append(value)
        or (username if locators == page.USERNAME else password),
    )
    monkeypatch.setattr(
        "compras_tn.infrastructure.automation.downloads.time.sleep",
        sleeps.append,
    )
    monkeypatch.setattr(page, "_click_element", lambda _element: pytest.fail("No debe hacer clic"))

    def wait_for_shell(timeout: int, **_kwargs: Any) -> str:
        waits.append(timeout)
        raise TimeoutError("sin ingreso")

    monkeypatch.setattr(page, "_wait_for_shell", wait_for_shell)
    monkeypatch.setattr(page, "_login_error", lambda: "")
    monkeypatch.setattr(page, "_find_now", lambda _locators, **_kwargs: username)

    with pytest.raises(TimeoutError, match="sin ingreso"):
        page._login_and_open_orders(
            SessionCredentials(
                username="usuario_demo@telconet.ec",
                email="usuario@telconet.ec",
                password="secreto",
            )
        )

    assert writes == ["USUARIO_DEMO", "secreto"]
    assert keys == [("password", Keys.ENTER)]
    assert sleeps == []
    assert waits == [100]


def test_purchase_order_gateway_delegates_shared_login_before_processing(
    monkeypatch: Any, tmp_path: Any
) -> None:
    attempts = 0
    drivers: list[Any] = []
    progress_messages: list[str] = []
    flow: list[str] = []

    class Settings:
        def get(self, _namespace: str, key: str, default: Any = None) -> Any:
            return 2 if key == "oc_login_retries" else default

    class Driver:
        def __init__(self) -> None:
            self.quit_calls = 0
            self.current_url = "https://sites.telconet.ec/naf/compras/sso/check"

        def quit(self) -> None:
            self.quit_calls += 1

    class Page:
        cancelled: Any = None

        def login_and_open_orders(self, _credentials: Any) -> None:
            nonlocal attempts
            attempts += 1

        def fill(self, draft: PurchaseOrderDraft) -> PurchaseOrderDraft:
            flow.append('fill')
            return draft

        def save_once(self) -> str:
            flow.append('save')
            return "400001"

        def open_fresh_form(self) -> None:
            flow.append('fresh')

    gateway = SeleniumPurchaseOrderGateway(
        Settings(), AppPaths.from_root(tmp_path / "appdata")
    )

    def create(_headless: bool) -> Driver:
        driver = Driver()
        drivers.append(driver)
        return driver

    monkeypatch.setattr(gateway, "_create_driver", create)
    monkeypatch.setattr(gateway, "_page", lambda _driver: Page())

    result = gateway.preload(
        SessionCredentials(
            username="usuario_demo@telconet.ec",
            email="usuario_demo@telconet.ec",
            password="secreto",
        ),
        [_draft(), _draft()],
        progress=lambda _current, _total, message: progress_messages.append(message),
    )

    assert result.status.value == "succeeded"
    assert flow == ['fill', 'save', 'fresh', 'fill', 'save']
    assert attempts == 1
    assert len(drivers) == 1
    assert drivers[0].quit_calls == 1
    assert any("Ingresando a NAF como USUARIO_DEMO" in message for message in progress_messages)


@pytest.mark.parametrize(
    "canonical,legacy,expected",
    [(45, 90, 45), (None, 90, 90)],
)
def test_purchase_order_element_timeout_prefers_canonical_setting(
    tmp_path: Any, canonical: Any, legacy: Any, expected: int
) -> None:
    class Settings:
        def get(self, namespace: str, key: str, default: Any = None) -> Any:
            values = {
                ("automation", "oc_element_timeout"): canonical,
                ("automation", "oc_field_timeout"): legacy,
            }
            return values.get((namespace, key), default)

    gateway = SeleniumPurchaseOrderGateway(
        Settings(), AppPaths.from_root(tmp_path / "appdata")
    )
    page = gateway._page(SimpleNamespace())
    assert page.element_timeout == expected
    assert page.login_attempts == 3


def test_supplier_three_nicknames_are_resolved_case_insensitively() -> None:
    supplier = Supplier(
        name="SERIMTEC",
        nickname="SEWRIMTEC",
        nickname_2="Serim Tec",
        nickname_3="S3",
        ruc="0991338144001",
        email_primary="compras@example.com",
    )

    for value in ("sewrimtec", "SERIM TEC", "s3"):
        matched, error = match_supplier_nickname(value, [supplier])
        assert error == ""
        assert matched == supplier


def test_supplier_official_name_is_also_accepted() -> None:
    supplier = Supplier(
        name="SERIMTEC",
        nickname="SEWRIMTEC",
        ruc="0991338144001",
        email_primary="compras@example.com",
    )

    matched, error = match_supplier_nickname("SERIMTEC", [supplier])

    assert error == ""
    assert matched == supplier


def test_loading_drafts_associates_sheet_supplier_with_local_ruc(
    repositories: Any, tmp_path: Any
) -> None:
    facade, _mail, _downloads, _scanner = _facade(repositories, tmp_path)
    repositories.save(
        Supplier(
            name="SERIMTEC",
            nickname="SEWRIMTEC",
            ruc="0991338144001",
            email_primary="compras@example.com",
        )
    )
    facade.sheets.drafts = [
        _draft().model_copy(update={"supplier": "SEWRIMTEC", "ruc": ""})
    ]

    loaded = facade.load_purchase_order_drafts()

    assert loaded[0].supplier == "SERIMTEC"
    assert loaded[0].ruc == "0991338144001"
    assert loaded[0].is_valid


def test_loading_drafts_keeps_requester_exactly_as_cleaned_in_sheet(
    repositories: Any, tmp_path: Any
) -> None:
    facade, _mail, _downloads, _scanner = _facade(repositories, tmp_path)
    repositories.save(
        Supplier(
            name="SERIMTEC",
            nickname="SEWRIMTEC",
            ruc="0991338144001",
            email_primary="compras@example.com",
        )
    )

    facade.sheets.drafts = [_draft()]

    loaded = facade.load_purchase_order_drafts()

    assert loaded[0].requester == "PAUL LUGMAÑA"


def test_original_download_report_format_has_no_attachment_contract() -> None:
    request = OperationRequest(
        kind="descarga_normal",
        mode=PurchaseMode.BIENES,
        items=[{"order_number": "373627", "supplier": "Proveedor uno"}],
    )
    result = OperationResult.from_items([
        OperationItem(
            key="373627",
            status=ItemStatus.SUCCEEDED,
            payload={
                "task_number": "163687165",
                "task_numbers": ["163687165", "163687166"],
                "supplier": "Proveedor uno",
                "pdf_path": "C:/OC/373627.pdf",
                "pdf_paths": [
                    "C:/BD_TN/Septiembre/163687165/373627.pdf",
                    "C:/BD_TN/Septiembre/163687166/373627.pdf",
                ],
                "task_destinations": [
                    {
                        "task_number": "163687165",
                        "month": "Septiembre",
                        "pdf_path": "C:/BD_TN/Septiembre/163687165/373627.pdf",
                        "preparation_status": "succeeded",
                    },
                    {
                        "task_number": "163687166",
                        "month": "Septiembre",
                        "pdf_path": "C:/BD_TN/Septiembre/163687166/373627.pdf",
                        "preparation_status": "succeeded",
                    },
                ],
            },
        ),
        OperationItem(
            key="373628",
            status=ItemStatus.SKIPPED,
            error_code="order_not_approved",
            message="La OC no está aprobada.",
            payload={"supplier": "Proveedor dos"},
        ),
    ])

    report = render_download_report(request, result)

    assert report is not None
    assert report.subject == "Reporte de órdenes descargadas"
    assert "Órdenes descargadas correctamente:" in report.html
    assert "NO APROBADAS" in report.html
    assert all(header in report.html for header in ("Orden", "Tarea", "Proveedor", "Ubicación"))
    assert "163687165 - 163687166 - Septiembre" in report.html
    assert "C:/BD_TN/Septiembre/163687165/373627.pdf" in report.html
    assert "C:/BD_TN/Septiembre/163687166/373627.pdf" in report.html
    assert "┌" in report.text and "373627" in report.text


def test_download_report_merges_duplicate_rows_without_erasing_supplier() -> None:
    request = OperationRequest(
        kind="descarga_normal",
        mode=PurchaseMode.BIENES,
        items=[
            {
                "order_number": "373627",
                "supplier": "Proveedor Uno",
                "task_numbers": ["19558554854"],
            },
            {
                "order_number": "373627",
                "supplier": "",
                "task_numbers": ["19558554855"],
            },
        ],
    )
    result = OperationResult.from_items(
        [
            OperationItem(
                key="373627",
                status=ItemStatus.SUCCEEDED,
                payload={
                    "supplier": "Proveedor Oficial",
                    "task_numbers": ["19558554854"],
                    "pdf_paths": ["C:/OC/uno.pdf"],
                },
            ),
            OperationItem(
                key="373627",
                status=ItemStatus.SUCCEEDED,
                payload={
                    "supplier": "",
                    "task_numbers": ["19558554855"],
                    "pdf_paths": ["C:/OC/dos.pdf"],
                },
            ),
        ]
    )

    report = render_download_report(request, result)

    assert report is not None
    assert report.html.count("<td style=") == 4
    assert "Proveedor Oficial" in report.html
    assert "19558554854 - 19558554855" in report.html
    assert "C:/OC/uno.pdf ; C:/OC/dos.pdf" in report.html


def test_download_email_uses_original_subject_and_does_not_attach_excel(
    repositories: Any, tmp_path: Any
) -> None:
    facade, mail, _downloads, _scanner = _facade(repositories, tmp_path)
    facade.login("ana", "memory-only")
    repositories.set("downloads", "correo_reporte", "reportes@example.com")

    facade.download_orders(
        OperationRequest(
            kind="descarga_normal",
            mode=PurchaseMode.BIENES,
            items=[{"order_number": "373627"}],
        )
    )

    assert mail.sent[-1]["subject"] == "Reporte de órdenes descargadas"
    assert mail.sent[-1]["attachments"] == []


def test_preload_reports_blocked_rows_without_sending_them_to_naf(
    repositories: Any, tmp_path: Any
) -> None:
    facade, mail, _downloads, _scanner = _facade(repositories, tmp_path)
    facade.login("ana", "memory-only")
    repositories.save(
        Supplier(
            name="SERIMTEC",
            nickname="SEWRIMTEC",
            ruc="0991338144001",
            email_primary="compras@example.com",
        )
    )
    received: list[PurchaseOrderDraft] = []
    options: dict[str, Any] = {}

    class Purchases:
        def preload(self, _credentials: Any, drafts: Any, **kwargs: Any) -> OperationResult:
            received.extend(drafts)
            options.update(kwargs)
            return OperationResult.from_items([
                OperationItem(
                    key=f"{draft.task_number} · {draft.supplier}",
                    status=ItemStatus.SUCCEEDED,
                    payload={"task_number": draft.task_number, "supplier": draft.supplier},
                )
                for draft in drafts
            ])

    facade.purchases = Purchases()
    facade.sheets.drafts = [_draft()]
    blocked = _draft().model_copy(update={"task_number": "999999999", "department": "OTRO", "validation_errors": ["artículo inválido"]})

    result = facade.preload_purchase_orders([_draft(), blocked], headless=True)

    assert len(received) == 1
    assert options["headless"] is True
    assert result.status.value == "partial"
    assert any(item.error_code == "validacion_hoja" for item in result.items)
    assert mail.sent[-1]["attachments"] == []


@pytest.mark.parametrize('error_type', [ConnectionResetError, __import__('requests').ConnectionError,
                                       __import__('google.auth.exceptions', fromlist=['TransportError']).TransportError])
def test_general_read_retries_transport_failures(monkeypatch, error_type):
    gateway = GoogleSheetsGateway(SimpleNamespace())
    attempts = []
    def read():
        attempts.append(True)
        if len(attempts) < 3:
            raise error_type('connection reset')
        return []
    monkeypatch.setattr(gateway, '_read_purchase_order_drafts_once', read)
    monkeypatch.setattr('compras_tn.infrastructure.google_sheets.time.sleep', lambda _: None)
    assert gateway.read_purchase_order_drafts() == []
    assert len(attempts) == 3


def test_general_read_stops_after_three_connection_resets(monkeypatch):
    gateway = GoogleSheetsGateway(SimpleNamespace())
    attempts = []
    def read():
        attempts.append(True)
        raise ConnectionResetError('10054')
    monkeypatch.setattr(gateway, '_read_purchase_order_drafts_once', read)
    monkeypatch.setattr('compras_tn.infrastructure.google_sheets.time.sleep', lambda _: None)
    with pytest.raises(ConnectionError, match='tres intentos'):
        gateway.read_purchase_order_drafts()
    assert len(attempts) == 3


def _long_draft(count=6):
    draft = _draft()
    draft.articles = [draft.articles[0].model_copy(update={
        'source_row':7347+i, 'description':f'ARTICULO {i} ' + 'X' * 640,
        'quantity':Decimal(i + 1)}, deep=True) for i in range(count)]
    draft.source_rows = [a.source_row for a in draft.articles]
    return draft


def test_long_observations_split_into_three_orders_without_losing_rows_or_money():
    from compras_tn.domain.purchase_order_groups import consolidate_orders
    from compras_tn.domain.purchase_order_observations import observation_length
    draft = _long_draft()
    parts = consolidate_orders([draft])
    assert len(parts) == 3
    assert all(observation_length(build_observation(part)) <= 2000 for part in parts)
    assert len({part.operation_key for part in parts}) == 3
    assert [part.split_part for part in parts] == [1, 2, 3]
    originals = [article for part in parts for article in part.original_articles]
    assert originals == draft.articles
    assert sum((part.subtotal for part in parts), Decimal(0)) == draft.subtotal
    assert sum((a.quantity for part in parts for a in part.articles), Decimal(0)) == sum(a.quantity for a in draft.articles)
    assert all(part.is_valid for part in parts)


def test_observation_exact_limit_and_single_oversized_row_never_truncated():
    from compras_tn.domain.purchase_order_groups import consolidate_orders
    from compras_tn.domain.purchase_order_observations import observation_length
    draft = _draft()
    current = observation_length(build_observation(draft))
    draft.articles[0].description += 'X' * (2000-current)
    part = consolidate_orders([draft])[0]
    assert part.is_valid
    assert observation_length(build_observation(part)) == 2000
    draft.articles[0].description += 'X'
    blocked = consolidate_orders([draft])[0]
    assert not blocked.is_valid
    assert blocked.original_articles == draft.articles
    assert 'un solo artículo' in ' '.join(blocked.validation_errors)


def test_split_multiple_tasks_and_preexisting_price_conflicts_are_preserved():
    from compras_tn.domain.purchase_order_groups import consolidate_orders
    from compras_tn.domain.purchase_order_observations import observation_length
    one, two = _long_draft(3), _long_draft(3)
    two.task_number = '166698853'
    for article in two.articles:
        article.source_row += 10
    two.source_rows = [a.source_row for a in two.articles]
    parts = consolidate_orders([one, two])
    assert len(parts) >= 2
    assert all(observation_length(build_observation(part)) <= 2000 for part in parts)
    assert sorted(a.source_row for p in parts for a in p.original_articles) == sorted(one.source_rows+two.source_rows)
    assert set(t for p in parts for t in p.task_numbers) == {one.task_number, two.task_number}
    two.articles[0].unit_price += 1
    assert all(not part.is_valid for part in consolidate_orders([one, two]))


def test_split_preload_records_each_row_once_and_validates_remaining_parts(repositories, tmp_path, monkeypatch):
    facade, *_ = _facade(repositories, tmp_path)
    repositories.save(Supplier(name='SEWRIMTEC', ruc='0991338144001'))
    original = _long_draft()
    recorded = {}
    def read():
        articles = [a for a in original.articles if a.source_row not in recorded]
        return [original.model_copy(update={'articles':articles, 'source_rows':[a.source_row for a in articles]}, deep=True)] if articles else []
    def validate(draft):
        by_row = {a.source_row:(source, a) for source in read() for a in source.articles}
        for source in draft.original_drafts:
            GoogleSheetsGateway._validate_source(source, by_row)
    def record(draft, number):
        for article in draft.original_articles:
            assert article.source_row not in recorded
            recorded[article.source_row] = number
    facade.sheets = SimpleNamespace(read_purchase_order_drafts=read,
        validate_purchase_order=validate, record_purchase_order=record)
    monkeypatch.setattr(facade, 'reconcile_oc_tasks', lambda: [])
    monkeypatch.setattr(facade, '_approve_saved_oc', lambda *args: None)
    def preload(credentials, drafts, **kwargs):
        items = []
        assert len(drafts) == 3
        for index, part in enumerate(drafts):
            kwargs['before_save'](part)
            number = str(380000 + index)
            kwargs['on_saved'](part, number)
            items.append(OperationItem(key=part.operation_key, status=ItemStatus.SUCCEEDED,
                payload={'task_number':part.task_number, 'order_number':number}))
        return OperationResult.from_items(items)
    facade.purchases = SimpleNamespace(preload=preload)
    result = facade.preload_purchase_orders([original])
    assert len(result.items) == 3
    assert all(item.status == ItemStatus.SUCCEEDED for item in result.items)
    assert set(recorded) == set(original.source_rows)
    assert len(set(recorded.values())) == 3


def test_selected_split_part_keeps_identity_and_other_parts_are_not_sent(repositories, tmp_path):
    facade, *_ = _facade(repositories, tmp_path)
    repositories.save(Supplier(name='SEWRIMTEC', ruc='0991338144001'))
    planned = facade._resolve_purchase_order_catalogs([_long_draft()])
    selected = facade._resolve_purchase_order_catalogs([planned[1]])
    assert len(selected) == 1
    assert selected[0].operation_key == planned[1].operation_key
    assert selected[0].source_rows == planned[1].source_rows
    assert selected[0].articles == planned[1].articles


@pytest.mark.parametrize('maximum', [None, '2000', '3000'])
def test_observation_never_sends_over_2000_even_without_html_maxlength(maximum):
    from compras_tn.infrastructure.automation.purchase_orders import PurchaseOrderValidationError
    page = object.__new__(GoodsPurchaseOrderPage)
    page._click = lambda *args: None
    page._find = lambda *args, **kwargs: SimpleNamespace(get_attribute=lambda name: maximum)
    page._write = lambda *args: pytest.fail('Oversized observation must never be sent')
    with pytest.raises(PurchaseOrderValidationError, match='dividir la orden'):
        page.fill_observation('\U0001f600' * 1001)
