from decimal import Decimal
from types import SimpleNamespace

import pytest
from test_application_services import _facade

from compras_tn.domain.models import (
    ItemStatus,
    OperationItem,
    OperationRequest,
    OperationResult,
    PurchaseMode,
    PurchaseOrderArticle,
    PurchaseOrderDraft,
    Supplier,
    WorkflowDefinition,
)
from compras_tn.domain.purchase_order_groups import consolidate_orders
from compras_tn.infrastructure.automation.purchase_orders import build_observation
from compras_tn.infrastructure.google_sheets import GoogleSheetsGateway
from compras_tn.infrastructure.operation_report import render_operation_report


def draft(task="164448987", row=7347, **changes):
    values = dict(task_number=task, supplier="PROVEEDOR", supplier_reference="ALIAS", ruc="1716726581001",
        department="GTN", requester="PERSONA EXACTA", detail=f"Detalle {task}",
        source_rows=[row], articles=[PurchaseOrderArticle(source_supplier="ALIAS", code="A-1",
        description="MATERIAL", quantity=Decimal("2"), unit_price=Decimal("3.50"), source_row=row)])
    values.update(changes)
    return PurchaseOrderDraft(**values)


def test_merge_quantities_keeps_observations_and_all_source_rows():
    first, second = draft(), draft("161516364", 7349)
    merged, = consolidate_orders([second, first, first])
    assert merged.task_numbers == ["164448987", "161516364"]
    assert merged.source_rows == [7347, 7349]
    assert len(merged.articles) == 1
    assert merged.articles[0].quantity == Decimal("4")
    assert merged.subtotal == Decimal("14")
    assert [a.quantity for a in merged.original_articles] == [Decimal("2"), Decimal("2")]
    observation = build_observation(merged)
    assert observation == build_observation(first) + "\n" + build_observation(second)
    assert observation.count("DETALLE:\n") == 2
    assert observation.count("MATERIAL 2 ALIAS $3.50") == 2
    assert consolidate_orders([merged])[0] == merged


@pytest.mark.parametrize("changes", [{"ruc": "0999999999001"}, {"department": "gtn"},
    {"requester": "Persona Exacta"}, {"requester": "PERSONA  EXACTA"}])
def test_exact_group_key_separates_differences(changes):
    assert len(consolidate_orders([draft(), draft("161516364", 7349, **changes)])) == 2


def test_outer_spaces_and_aliases_resolve_same_ruc(repositories, tmp_path):
    facade, *_ = _facade(repositories, tmp_path)
    repositories.save(Supplier(name="PROVEEDOR", nickname="ALIAS", nickname_2="OTRO", ruc="1716726581001", email_primary="p@example.com"))
    first = draft(supplier="alias")
    second = draft("161516364", 7349, supplier="otro", department=" GTN ", requester="PERSONA EXACTA ")
    merged, = facade._resolve_purchase_order_catalogs([first, second])
    assert merged.is_valid
    assert len(merged.task_numbers) == 2


def test_different_prices_block_entire_group_with_evidence():
    second = draft("161516364", 7349)
    second.articles[0].unit_price = Decimal("4.25")
    merged, = consolidate_orders([draft(), second])
    assert not merged.is_valid
    message = " ".join(merged.validation_errors)
    for expected in ("A-1", "164448987", "161516364", "7347", "7349", "3.50", "4.25"):
        assert expected in message


def sheet_rows(second_oc="", extra=False):
    rows = [
        ["", "", "164448987", "", "", "", "", "", "S/N", "GTN", "PERSONA EXACTA", "Detalle 164448987"],
        ["", "A-1", "MATERIAL", 2, "ALIAS", 3.5, ""],
        ["", "", "161516364", "", "", "", "", "", "S/N", "GTN", "PERSONA EXACTA", "Detalle 161516364"],
        ["", "A-1", "MATERIAL", 2, "ALIAS", 3.5, second_oc],
    ]
    if extra:
        rows.append(["", "B-2", "OTRO", 1, "NO REGISTRADO", 10, ""])
    return rows


class Worksheet:
    def __init__(self, rows):
        self.rows = rows
        self.updates = []
    def get(self, region, **kwargs):
        if region.startswith("A"):
            return self.rows
        if ":" in region:
            return [[r[6]] if len(r) > 6 else [] for r in self.rows]
        return [[self.rows[int(region[1:]) - 7346][6]]]
    def batch_update(self, updates, **kwargs):
        self.updates.extend(updates)
        for update in updates:
            self.rows[int(update["range"][1:]) - 7346][6] = update["values"][0][0]


def gateway(monkeypatch, rows):
    worksheet = Worksheet(rows)
    sheets = GoogleSheetsGateway(SimpleNamespace(get=lambda *args: args[-1]))
    monkeypatch.setattr(sheets, "_worksheet", lambda *args, **kwargs: worksheet)
    return sheets, worksheet


def test_single_cells_cannot_report_synced_when_source_block_is_empty(monkeypatch):
    import requests
    sheets, worksheet = gateway(monkeypatch, sheet_rows())
    merged, = consolidate_orders([draft(), draft('161516364', 7349)])
    original_get = worksheet.get
    def inconsistent(region, **kwargs):
        if region.startswith('G') and ':' not in region:
            return [['374580']]
        return original_get(region, **kwargs)
    monkeypatch.setattr(worksheet, 'get', inconsistent)
    monkeypatch.setattr('compras_tn.infrastructure.google_sheets.time.sleep', lambda _: None)
    with pytest.raises(requests.ConnectionError, match='releer el bloque'):
        sheets.record_purchase_order(merged, '374580')
    assert worksheet.updates == []


def test_grouped_write_updates_every_original_row_and_revalidates(monkeypatch):
    sheets, worksheet = gateway(monkeypatch, sheet_rows())
    merged, = consolidate_orders([draft(), draft("161516364", 7349)])
    sheets.validate_purchase_order(merged)
    sheets.record_purchase_order(merged, "374562")
    assert [item["range"] for item in worksheet.updates] == ["G7347", "G7349"]
    assert sheets.read_purchase_order_drafts() == []
    sheets.record_purchase_order(merged, "374562")  # idempotent recovery
    worksheet.rows[3][6] = "374563"
    with pytest.raises(ValueError, match="no se sobrescribió"):
        sheets.record_purchase_order(merged, "374562")


def test_gspread_mutated_batch_ranges_do_not_duplicate_sheet_name(monkeypatch):
    sheets, worksheet = gateway(monkeypatch, sheet_rows())
    original = worksheet.batch_update
    def mutating_update(updates, **kwargs):
        original(updates, **kwargs)
        for update in updates:
            update["range"] = "'GENERAL'!" + update["range"]
    worksheet.batch_update = mutating_update
    merged, = consolidate_orders([draft(), draft("161516364", 7349)])
    sheets.record_purchase_order(merged, "374580")
    assert worksheet.rows[1][6] == "374580" and worksheet.rows[3][6] == "374580"


def test_grouped_write_refuses_changed_contribution_before_any_write(monkeypatch):
    sheets, worksheet = gateway(monkeypatch, sheet_rows())
    merged, = consolidate_orders([draft(), draft("161516364", 7349)])
    worksheet.rows[3][3] = 5
    with pytest.raises(ValueError, match="cambió"):
        sheets.record_purchase_order(merged, "374562")
    assert worksheet.updates == []


def test_task_status_includes_unselected_suppliers_and_rejects_formula(monkeypatch):
    sheets, worksheet = gateway(monkeypatch, sheet_rows("374562", extra=True))
    worksheet.rows[1][6] = "374562"
    states = sheets.read_purchase_task_status()
    assert states["164448987"]["ready"]
    assert not states["161516364"]["ready"]
    worksheet.rows[4][6] = '=IF(TRUE,"374563","")'
    assert not sheets.read_purchase_task_status()["161516364"]["ready"]
    worksheet.rows[4][6] = "374563"
    assert sheets.read_purchase_task_status()["161516364"]["ready"]
    worksheet.rows[4][3] = ""  # incomplete article does not delay task
    worksheet.rows[4][6] = ""
    assert sheets.read_purchase_task_status()["161516364"]["ready"]


def test_reconcile_tasks_independently_and_never_reopen_consumed(repositories, tmp_path, monkeypatch):
    facade, *_ = _facade(repositories, tmp_path)
    sheets, worksheet = gateway(monkeypatch, sheet_rows("374562", extra=True))
    worksheet.rows[1][6] = "374562"
    facade.sheets = sheets
    merged, = consolidate_orders([draft(), draft("161516364", 7349)])
    facade._record_oc_receipt(merged, "synced", "374562")
    facade.reconcile_oc_tasks()
    pending = repositories.list_pending("carga_oc_automatica")
    assert [t.task_number for t in pending] == ["164448987"]
    repositories.consume(["164448987"])
    worksheet.rows[4][6] = "374563"
    facade.reconcile_oc_tasks()
    facade.reconcile_oc_tasks()
    pending = repositories.list_pending("carga_oc_automatica")
    assert [t.task_number for t in pending] == ["161516364"]
    assert pending[0].payload["order_numbers"] == ["374562", "374563"]
    # New ready article makes even an already-pending task wait again.
    worksheet.rows.append(["", "C-3", "NUEVO", 1, "OTRO", 1, ""])
    facade.reconcile_oc_tasks()
    assert repositories.list_pending("carga_oc_automatica") == []


def test_old_synced_history_not_imported(repositories, tmp_path):
    facade, *_ = _facade(repositories, tmp_path)
    original = draft()
    for key in facade._oc_receipt_keys(original):
        repositories.set("oc_receipts", key, {"state": "synced", "number": "374562", "draft": original.model_dump(mode="json")})
    assert facade.reconcile_oc_tasks() == []
    assert repositories.list_pending("carga_oc_automatica") == []


def test_report_multitask_html_escaped_and_no_results_failure():
    merged, = consolidate_orders([draft(), draft("161516364", 7349)])
    request = OperationRequest(kind="precarga_oc_bienes", items=[merged.model_dump(mode="json")])
    result = OperationResult.from_items([OperationItem(key="group", status=ItemStatus.FAILED,
        message="<script>error</script>", payload={"task_number": merged.task_number, "order_number": "374562", "sheet_written": False})])
    report = render_operation_report(request, result, "Reporte OC")
    assert "164448987, 161516364" in report.html
    assert "&lt;script&gt;" in report.html and "<script>" not in report.html
    assert "Pendiente" in report.html
    assert "border-collapse:collapse" in report.html
    empty = render_operation_report(request, OperationResult.from_items([], "Error general de conexión"), "Reporte")
    assert "Error general de conexión" in empty.html and "Error general de conexión" in empty.text


def test_email_report_does_not_depend_on_local_excel(repositories, tmp_path):
    facade, mail, *_ = _facade(repositories, tmp_path)
    facade.login("ana", "memory-only")
    def fail_report(*args):
        raise OSError("disco lleno")
    facade.reports.write = fail_report
    facade._audited(OperationRequest(kind="actualizar_tareas"),
        lambda: OperationResult.from_items([], "Sin elementos"), report_recipients=["ana@example.com"], report_title="Actualizar tareas")
    assert mail.sent[-1]["attachments"] == []
    assert "disco lleno" in mail.sent[-1]["html"]


def test_revalidate_detects_changed_original_even_when_total_is_unchanged(repositories, tmp_path, monkeypatch):
    facade, *_ = _facade(repositories, tmp_path)
    repositories.save(Supplier(name="PROVEEDOR", nickname="ALIAS", ruc="1716726581001", email_primary="p@example.com"))
    facade.sheets, worksheet = gateway(monkeypatch, sheet_rows())
    merged, = facade.load_purchase_order_drafts()
    facade._validate_oc_snapshot(merged)
    worksheet.rows[1][3], worksheet.rows[3][3] = 1, 3
    with pytest.raises(ValueError, match="cambiaron"):
        facade._prepare_oc_save(merged)
    assert repositories.list_namespace("oc_receipts") == {}


def test_recovery_when_all_g_already_written_enrolls_without_regenerating(repositories, tmp_path, monkeypatch):
    facade, *_ = _facade(repositories, tmp_path)
    facade.sheets, worksheet = gateway(monkeypatch, sheet_rows("374562"))
    worksheet.rows[1][6] = "374562"
    merged, = consolidate_orders([draft(), draft("161516364", 7349)])
    facade._record_oc_receipt(merged, "pending", "374562")
    assert facade.load_purchase_order_drafts() == []
    facade.login("ana", "memory-only")
    receipt, = facade.pending_oc_recoveries()
    facade.recover_purchase_order(receipt['key'], receipt['at'], number='374562', verified=True, reason='Verificado en NAF')
    facade.reconcile_oc_tasks()
    assert len(repositories.list_pending("carga_oc_automatica")) == 2
    assert len(worksheet.updates) == 0


def test_conflicting_local_receipt_does_not_restore_rows_with_g_filled(repositories, tmp_path, monkeypatch):
    facade, *_ = _facade(repositories, tmp_path)
    facade.sheets, worksheet = gateway(monkeypatch, sheet_rows("374563"))
    worksheet.rows[1][6] = "374562"
    merged, = consolidate_orders([draft(), draft("161516364", 7349)])
    facade._record_oc_receipt(merged, "pending", "374562")
    assert facade.load_purchase_order_drafts() == []
    assert repositories.list_pending("carga_oc_automatica") == []


def test_revalidate_before_telcos_warns_but_continues_new_pending_supplier(repositories, tmp_path, monkeypatch):
    facade, *_ = _facade(repositories, tmp_path)
    facade.login("ana", "memory-only")
    facade.sheets, worksheet = gateway(monkeypatch, sheet_rows("374562"))
    worksheet.rows[1][6] = "374562"
    merged, = consolidate_orders([draft(), draft("161516364", 7349)])
    facade._record_oc_receipt(merged, "synced", "374562")
    selected = facade.reconcile_oc_tasks()
    worksheet.rows.append(["", "C-3", "NUEVO", 1, "OTRO", 1, ""])
    executed = []
    def allowed(_credentials, _workflow, tasks, **_kwargs):
        executed.extend(task.task_number for task in tasks)
        return OperationResult.from_items([
            OperationItem(key=task.task_number, status=ItemStatus.SUCCEEDED)
            for task in tasks
        ])
    facade.telcos.execute_workflow = allowed
    result = facade.execute_workflow(WorkflowDefinition(name="Prueba", mode=PurchaseMode.BIENES), selected, headless=True)
    assert result.status.value == "succeeded"
    assert executed == [task.task_number for task in selected]
    assert "Advertencia" in result.message
    assert "161516364" in result.message
    assert "pendientes" in result.message


def test_read_failure_hides_previously_ready_tasks(repositories, tmp_path, monkeypatch):
    facade, *_ = _facade(repositories, tmp_path)
    facade.sheets, worksheet = gateway(monkeypatch, sheet_rows("374562"))
    worksheet.rows[1][6] = "374562"
    merged, = consolidate_orders([draft(), draft("161516364", 7349)])
    facade._record_oc_receipt(merged, "synced", "374562")
    facade.reconcile_oc_tasks()
    def unavailable():
        raise ConnectionError("sin conexión")
    facade.sheets.read_purchase_task_status = unavailable
    with pytest.raises(ConnectionError):
        facade.reconcile_oc_tasks()
    assert repositories.list_pending("carga_oc_automatica") == []


def test_report_prefers_multipart_sender_without_attachments(repositories, tmp_path):
    facade, mail, *_ = _facade(repositories, tmp_path)
    facade.login("ana", "memory-only")
    sent = []
    mail.send_html_with_text = lambda credentials, to, subject, html, text: sent.append((html, text))
    facade._send_report(OperationRequest(kind="reasignar"), OperationResult.from_items([], "Prueba"), ["ana@example.com"], "Reasignación")
    assert len(sent) == 1
    assert "<table" not in sent[0][1]
    assert "Prueba" in sent[0][0] and "Prueba" in sent[0][1]
    assert mail.sent == []
