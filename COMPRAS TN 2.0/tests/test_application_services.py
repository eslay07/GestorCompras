from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from compras_tn.application.services import ApplicationFacade
from compras_tn.domain.models import (
    EmailTemplate,
    FlowStep,
    ItemStatus,
    JobStatus,
    OperationItem,
    OperationRequest,
    OperationResult,
    OrderRecord,
    PurchaseMode,
    PurchaseOrderDraft,
    ScannedOrderMessage,
    SessionCredentials,
    TaskRecord,
    WorkflowDefinition,
)
from compras_tn.infrastructure.db import Repositories


class FakeMail:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    def validate(self, credentials: SessionCredentials) -> None:
        assert credentials.password

    def validate_inbox(self, credentials: SessionCredentials) -> None:
        assert credentials.password

    def scan_tasks(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return []

    def send_html(
        self,
        credentials: SessionCredentials,
        to: Sequence[str],
        subject: str,
        html: str,
        attachments: Sequence[Path] = (),
        cc: Sequence[str] = (),
    ) -> None:
        self.sent.append(
            {"to": list(to), "subject": subject, "html": html, "attachments": list(attachments)}
        )


class FakeTelcos:
    def validate(self, credentials: SessionCredentials, *, headless: bool = True) -> None:
        return None

    def execute_workflow(self, credentials: SessionCredentials, workflow: WorkflowDefinition, tasks: Sequence[TaskRecord], **kwargs: Any) -> OperationResult:
        return OperationResult.from_items(
            [OperationItem(key=task.task_number, status=ItemStatus.SUCCEEDED) for task in tasks]
        )

    def reassign(self, credentials: SessionCredentials, tasks: Sequence[TaskRecord], department: str, employee: str, comment_template: str, **kwargs: Any) -> OperationResult:
        return OperationResult.from_items(
            [OperationItem(key=task.task_number, status=ItemStatus.SUCCEEDED) for task in tasks]
        )


class FakeDownloads:
    def __init__(self) -> None:
        self.fail_second = False

    def download(self, credentials: SessionCredentials, request: OperationRequest, **kwargs: Any) -> OperationResult:
        items: list[OperationItem] = []
        for index, raw in enumerate(request.items):
            number = str(raw["order_number"])
            if index == 1 and self.fail_second:
                items.append(OperationItem(key=number, status=ItemStatus.FAILED, message="falló"))
            else:
                items.append(
                    OperationItem(
                        key=number,
                        status=ItemStatus.SUCCEEDED,
                        payload={
                            "order_number": number,
                            "task_number": f"T{number}",
                            "supplier": "Proveedor",
                            "pdf_path": f"{number}.pdf",
                        },
                    )
                )
        return OperationResult.from_items(items)


def test_download_request_consolidates_repeated_order_metadata() -> None:
    request = OperationRequest(
        kind="descarga_normal",
        mode=PurchaseMode.BIENES,
        items=[
            {
                "order_number": "373627",
                "supplier": "Proveedor Uno",
                "task_numbers": ["19558554854"],
                "external_id": "MAIL-1",
            },
            {
                "order_number": "373627",
                "supplier": "",
                "task_numbers": ["19558554855", "19558554854"],
                "external_id": "MAIL-2",
            },
        ],
    )

    consolidated = ApplicationFacade._consolidate_download_request(request)

    assert len(consolidated.items) == 1
    assert consolidated.items[0]["supplier"] == "Proveedor Uno"
    assert consolidated.items[0]["task_numbers"] == ["19558554854", "19558554855"]
    assert consolidated.items[0]["external_ids"] == ["MAIL-1", "MAIL-2"]


def test_download_request_preserves_conflicting_supplier_candidates() -> None:
    request = OperationRequest(
        kind="descarga_normal",
        items=[
            {"order_number": "373627", "supplier": "Proveedor Uno"},
            {"order_number": "373627", "supplier": "Proveedor Dos"},
        ],
    )

    item = ApplicationFacade._consolidate_download_request(request).items[0]

    assert item["supplier"] == "Proveedor Uno"
    assert item["supplier_candidates"] == ["Proveedor Uno", "Proveedor Dos"]


class FakeOrders:
    def __init__(self, records: dict[str, OrderRecord]):
        self.records = records

    def resolve(self, order_number: str) -> OrderRecord:
        if order_number not in self.records:
            raise FileNotFoundError(order_number)
        return self.records[order_number]


class FakeSheets:
    def read_purchase_task_status(self):
        return {}

    def validate_purchase_order(self, draft):
        return None

    def record_purchase_order(self, draft, number):
        return None

    def __init__(self) -> None:
        self.drafts: list[PurchaseOrderDraft] = []

    def read_approved_orders(self) -> list[dict[str, Any]]:
        return [{"order_number": "1"}]

    def read_purchase_order_drafts(self) -> list[PurchaseOrderDraft]:
        return self.drafts


class FakeRenderer:
    def render(self, template: EmailTemplate, context: dict[str, Any]) -> str:
        return template.html.replace("{proveedor}", str(context.get("proveedor") or ""))


class FakeScanner:
    def __init__(self) -> None:
        self.messages: list[ScannedOrderMessage] = []
        self.marked: list[str] = []

    def scan(
        self,
        credentials: SessionCredentials,
        **_kwargs: Any,
    ) -> list[ScannedOrderMessage]:
        return self.messages

    def validate(self, credentials: SessionCredentials) -> None:
        return None

    def mark_processed(self, external_ids: Sequence[str]) -> None:
        self.marked.extend(external_ids)


class FakeReports:
    def __init__(self, folder: Path):
        self.folder = folder

    def write(self, request: OperationRequest, result: OperationResult) -> Path:
        path = self.folder / f"{request.kind}.xlsx"
        path.write_bytes(b"report")
        return path


class FakeSeafile:
    def validate(self, credentials: SessionCredentials) -> None:
        return None

    def upload(self, credentials: SessionCredentials, file_path: Path, repo_id: str, parent_dir: str = "/") -> str:
        return "ok"


def _facade(repositories: Repositories, tmp_path: Path) -> tuple[ApplicationFacade, FakeMail, FakeDownloads, FakeScanner]:
    pdf1 = tmp_path / "1.pdf"
    pdf2 = tmp_path / "2.pdf"
    pdf1.write_bytes(b"pdf")
    pdf2.write_bytes(b"pdf")
    orders = FakeOrders(
        {
            "1": OrderRecord(
                order_number="1", task_number="101", supplier="P", ruc="001",
                pdf_path=str(pdf1), metadata={"emails": ["uno@example.com"]},
            ),
            "2": OrderRecord(
                order_number="2", task_number="102", supplier="P", ruc="001",
                pdf_path=str(pdf2), metadata={"emails": ["dos@example.com"]},
            ),
        }
    )
    mail = FakeMail()
    downloads = FakeDownloads()
    scanner = FakeScanner()
    facade = ApplicationFacade(
        suppliers=repositories,
        settings=repositories,
        catalogs=repositories,
        inbox=repositories,
        jobs=repositories,
        mail=mail,
        telcos=FakeTelcos(),
        downloads=downloads,
        orders=orders,
        sheets=FakeSheets(),
        renderer=FakeRenderer(),
        order_mail=scanner,
        reports=FakeReports(tmp_path),
        seafile=FakeSeafile(),
    )
    facade.login("ana", "session-only-secret")
    return facade, mail, downloads, scanner


def test_mass_email_groups_by_ruc_and_enqueues_tasks(repositories: Repositories, tmp_path: Path) -> None:
    facade, mail, _downloads, _scanner = _facade(repositories, tmp_path)
    result = facade.send_dispatch(
        ["1", "2"],
        EmailTemplate(name="Aviso", html="Hola {proveedor}"),
        grouped=True,
        mode=PurchaseMode.BIENES,
    )
    assert result.status.value == "succeeded"
    assert len(mail.sent) == 1
    assert set(mail.sent[0]["to"]) == {"uno@example.com", "dos@example.com"}
    assert {task.task_number for task in facade.list_pending_tasks()} == {"101", "102"}


def test_multitask_order_sends_once_and_enqueues_each_task(
    repositories: Repositories, tmp_path: Path
) -> None:
    facade, mail, _downloads, _scanner = _facade(repositories, tmp_path)
    facade.orders.records["1"] = facade.orders.records["1"].model_copy(
        update={"task_number": "101", "task_numbers": ["101", "103"]}
    )

    result = facade.send_dispatch(
        ["1"],
        EmailTemplate(name="Aviso", html="Hola {proveedor}"),
        grouped=False,
        mode=PurchaseMode.BIENES,
    )

    assert result.status == JobStatus.SUCCEEDED
    assert len(mail.sent) == 1
    assert "TAREA 101, 103" in mail.sent[0]["subject"]
    assert {task.task_number for task in facade.list_pending_tasks()} == {"101", "103"}


def test_dispatch_preview_keeps_errors_without_blocking_valid_orders(
    repositories: Repositories, tmp_path: Path
) -> None:
    facade, mail, _downloads, _scanner = _facade(repositories, tmp_path)
    preview = facade.prepare_dispatch(["1", "404"])

    assert preview.valid_count == 1
    assert preview.items[1].error
    result = facade.send_prepared_dispatch(
        preview,
        EmailTemplate(name="Aviso", html="Hola {proveedor}"),
        grouped=False,
        mode=PurchaseMode.BIENES,
    )

    assert result.status == JobStatus.PARTIAL
    assert len(mail.sent) == 1
    assert {item.key for item in result.items if item.status == ItemStatus.FAILED} == {"404"}


def test_pending_oc_is_a_warning_and_workflow_still_runs(
    repositories: Repositories, tmp_path: Path
) -> None:
    facade, _mail, _downloads, _scanner = _facade(repositories, tmp_path)
    number = "164448987"
    repositories.set(
        "oc_task_candidates",
        facade._oc_scope() + number,
        {"task_number": number, "rows": {}},
    )
    progress: list[str] = []

    result = facade.execute_workflow(
        WorkflowDefinition(name="Continuar"),
        [
            TaskRecord(
                task_number=number,
                origin="carga_oc_automatica",
                purchase_mode=PurchaseMode.BIENES,
            )
        ],
        headless=True,
        progress=lambda _current, _total, message: progress.append(message),
    )

    assert result.status == JobStatus.SUCCEEDED
    assert "Advertencia" in result.message
    assert "pendientes o sin verificar" in result.message
    assert any("Advertencia" in message for message in progress)


def test_download_scan_marks_message_only_when_every_order_finishes(repositories: Repositories, tmp_path: Path) -> None:
    facade, _mail, downloads, scanner = _facade(repositories, tmp_path)
    scanner.messages = [
        ScannedOrderMessage(
            external_id="UID-1",
            orders=[{"order_number": "1"}, {"order_number": "2"}],
        )
    ]
    downloads.fail_second = True
    facade.scan_and_download_orders(PurchaseMode.BIENES, headless=True)
    assert scanner.marked == []
    downloads.fail_second = False
    facade.scan_and_download_orders(PurchaseMode.BIENES, headless=True)
    assert scanner.marked == ["UID-1"]
    assert {task.task_number for task in facade.list_pending_tasks("descargas")} == {"T1", "T2"}


@pytest.mark.parametrize('headless', [False, True], ids=['visible', 'oculto'])
@pytest.mark.parametrize('source', ['manual', 'correo'])
def test_download_entrypoints_preserve_browser_mode_and_mail_state(repositories, tmp_path, headless, source):
    facade, _mail, downloads, scanner = _facade(repositories, tmp_path)
    captured = []
    original = downloads.download
    def download(credentials, request, **kwargs):
        captured.append(request)
        return original(credentials, request, **kwargs)
    downloads.download = download
    if source == 'correo':
        scanner.messages = [ScannedOrderMessage(external_id='UID-MODES', orders=[{'order_number':'374761'}])]
        result = facade.scan_and_download_orders(PurchaseMode.BIENES, headless=headless)
    else:
        result = facade.download_orders(OperationRequest(kind='descarga_normal', mode=PurchaseMode.BIENES,
            items=[{'order_number':'374761'}], options={'headless':headless}))
    assert captured[0].options['headless'] is headless
    assert result.items[0].status == ItemStatus.SUCCEEDED
    assert scanner.marked == (['UID-MODES'] if source == 'correo' else [])


def test_static_missing_file_alias_blocks_workflow_save(repositories: Repositories, tmp_path: Path) -> None:
    facade, _mail, _downloads, _scanner = _facade(repositories, tmp_path)
    flow = WorkflowDefinition(
        name="Archivo",
        steps=[
            FlowStep(action_id="abrir_subida_archivo"),
            FlowStep(action_id="seleccionar_archivo", params={"ruta": "@contrato"}),
        ],
    )
    with pytest.raises(ValueError, match="alias '@contrato'"):
        facade.save_workflow(flow)


def test_session_password_never_reaches_sqlite(repositories: Repositories, tmp_path: Path) -> None:
    facade, _mail, _downloads, _scanner = _facade(repositories, tmp_path)
    assert facade.credentials.password == "session-only-secret"
    database_folder = repositories.database.path.parent
    for file in database_folder.iterdir():
        if file.is_file():
            assert b"session-only-secret" not in file.read_bytes()
