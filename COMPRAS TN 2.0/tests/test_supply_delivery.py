from types import SimpleNamespace

from compras_tn.domain.models import OperationRequest, PurchaseMode
from compras_tn.infrastructure.automation.downloads import (
    SeleniumOrderDownloadGateway,
    SupplyDownload,
)
from compras_tn.infrastructure.orders import OrderFileService


def test_supply_renames_with_row_number_and_does_not_route_by_task(tmp_path, monkeypatch):
    path = tmp_path / "ABASTECIMIENTO" / "generado.pdf"
    path.parent.mkdir()
    path.write_bytes(b"%PDF-test")
    files = SimpleNamespace(resolve_supplier=lambda *args, **kwargs: "PROVEEDOR S.A.",
                            invalidate_inventory=lambda: None)
    gateway = SeleniumOrderDownloadGateway(SimpleNamespace(), files, app_paths=SimpleNamespace())
    monkeypatch.setattr(OrderFileService, "extract", lambda p: {"supplier": "PROVEEDOR S.A.", "task_numbers": ["123456"]})
    sent = []
    monkeypatch.setattr(gateway, "_upload_supply", lambda credentials, pdf, **kwargs:
                        (sent.append(pdf) or "", {"upload_status": "uploaded"}))
    monkeypatch.setattr(gateway, "_finalize_task_destinations", lambda *args, **kwargs:
                        (_ for _ in ()).throw(AssertionError("No debe organizar por tarea")))
    page = SimpleNamespace(configure_supply_filters=lambda *args: None,
                           download_all_visible_results=lambda **kwargs: [SupplyDownload("375135", path)])
    request = OperationRequest(kind="descarga_abastecimiento", mode=PurchaseMode.BIENES)
    items = gateway._download_supply(page, None, request, 1, None, None)
    assert items[0].payload["pdf_path"] == str(path.parent / "ORDEN 375135 - PROVEEDOR S_A_.pdf")
    assert sent[0].is_file()
    assert items[0].payload["task_numbers"] == ["123456"]


def test_supply_download_folder_is_created_before_browser(tmp_path, monkeypatch):
    settings = SimpleNamespace(get=lambda namespace, key, default=None: default)
    gateway = SeleniumOrderDownloadGateway(settings, SimpleNamespace(), app_paths=SimpleNamespace())
    folders = []
    def create(folder, headless):
        folders.append(folder)
        assert folder.is_dir()
        raise RuntimeError("Prueba sin sesión")
    monkeypatch.setattr(gateway, "_create_driver", create)
    request = OperationRequest(kind="descarga_abastecimiento", mode=PurchaseMode.BIENES,
                               options={"download_folder": str(tmp_path)})
    gateway._download_batch(None, request)
    assert folders == [tmp_path / "ABASTECIMIENTO"]
    request.options["download_folder"] = str(tmp_path / "ABASTECIMIENTO")
    gateway._download_batch(None, request)
    assert folders[-1] == tmp_path / "ABASTECIMIENTO"


def test_current_naf_pdf_header_is_identified(monkeypatch, tmp_path):
    from contextlib import contextmanager

    import compras_tn.infrastructure.orders as orders

    @contextmanager
    def open_pdf(path):
        yield SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda:
            "ORDEN DE COMPRA\nBIENES\nNo 123456\nPROVEEDOR CONDICIONES\nNOMBRE: PROVEEDOR S.A. FORMA CREDITO\nRUC: 1234567890001")])
    monkeypatch.setattr(orders.pdfplumber, "open", open_pdf)
    info = OrderFileService.extract(tmp_path / "temporal.pdf")
    assert info["order_number"] == "123456"
    assert info["supplier"] == "PROVEEDOR S.A."


def test_supply_wait_ignores_late_pdf_of_another_order(monkeypatch, tmp_path):
    import compras_tn.infrastructure.automation.downloads as downloads

    page = downloads.OrderPortalPage(SimpleNamespace(), tmp_path)
    wrong = tmp_path / "otra.pdf"
    wrong.write_bytes(b"%PDF-wrong")
    (tmp_path / "downloads.htm.crdownload").write_bytes(b"descarga ajena")
    right = tmp_path / "correcta.pdf"
    monkeypatch.setattr(page, "_notifications", lambda: [
        "nuevo_id\x1fTransacción realizada correctamente No está permitida la descarga de la orden 654321"
    ])
    monkeypatch.setattr(downloads, "time", SimpleNamespace(monotonic=lambda: next(ticks)))
    ticks = iter(range(100))
    monkeypatch.setattr(OrderFileService, "extract", lambda path:
                        {"order_number": "123456" if path == right else "654321"})
    def wait(predicate, *args):
        for index in range(6):
            if index == 2:
                right.write_bytes(b"%PDF-correct")
            result = predicate(None)
            if result:
                return result
        raise TimeoutError("No llegó la OC correcta")
    monkeypatch.setattr(page, "_wait", wait)
    result = page.wait_for_download({}, expected_number="123456",
        previous_notifications=("viejo_id\x1fNo está permitida la descarga de la orden 654321",))
    assert result == right
    assert wrong.exists()
