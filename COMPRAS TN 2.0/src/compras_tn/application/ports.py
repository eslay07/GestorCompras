from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from compras_tn.domain.models import (
    Assignment,
    EmailTemplate,
    OperationItem,
    OperationRequest,
    OperationResult,
    OrderRecord,
    PurchaseOrderDraft,
    ScannedOrderMessage,
    SessionCredentials,
    Supplier,
    TaskRecord,
    WorkflowDefinition,
)


class SupplierRepository(Protocol):
    def list(self, search: str = "") -> list[Supplier]: ...
    def save(self, supplier: Supplier) -> Supplier: ...
    def delete(self, supplier_id: int) -> None: ...
    def find_by_ruc(self, ruc: str) -> Supplier | None: ...
    def find_by_nickname(self, nickname: str) -> Supplier | None: ...


class SettingsRepository(Protocol):
    def get(self, namespace: str, key: str, default: Any = None) -> Any: ...
    def set(self, namespace: str, key: str, value: Any) -> None: ...
    def set_many(self, values: Mapping[tuple[str, str], Any]) -> None: ...
    def list_namespace(self, namespace: str) -> dict[str, Any]: ...


class CatalogRepository(Protocol):
    def list_assignments(self) -> list[Assignment]: ...
    def save_assignment(self, item: Assignment) -> Assignment: ...
    def delete_assignment(self, subdepartment: str) -> None: ...
    def list_templates(self) -> list[EmailTemplate]: ...
    def save_template(self, item: EmailTemplate) -> EmailTemplate: ...
    def delete_template(self, template_id: int) -> None: ...
    def list_workflows(self, mode: str | None = None) -> list[WorkflowDefinition]: ...
    def save_workflow(self, item: WorkflowDefinition) -> WorkflowDefinition: ...
    def delete_workflow(self, workflow_id: int) -> None: ...


class TaskInboxRepository(Protocol):
    def update_task_orders(self, task: TaskRecord, orders: list[dict], *, edited: bool = True, origin_only: bool = False) -> None: ...
    def synchronize_oc_task(self, task: TaskRecord, ready: bool) -> None: ...
    def dismiss(self, tasks: Sequence[TaskRecord]) -> None: ...

    def enqueue(self, tasks: Sequence[TaskRecord]) -> int: ...
    def list_pending(self, origin: str | None = None) -> list[TaskRecord]: ...
    def consume(self, task_numbers: Sequence[str], origin: str | None = None) -> None: ...


class JobRepository(Protocol):
    def cycle_successes(self) -> list[tuple[OperationRequest, OperationItem]]: ...
    def start(self, request: OperationRequest) -> int: ...
    def finish(self, run_id: int, result: OperationResult) -> None: ...


class MailGateway(Protocol):
    def validate(self, credentials: SessionCredentials) -> None: ...
    def validate_inbox(self, credentials: SessionCredentials) -> None: ...
    def scan_tasks(
        self,
        credentials: SessionCredentials,
        start: datetime,
        end: datetime,
        subject_contains: str,
        sender: str = "",
        progress: Callable[[int, int, str], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> list[dict[str, Any]]: ...
    def send_html(
        self,
        credentials: SessionCredentials,
        to: Sequence[str],
        subject: str,
        html: str,
        attachments: Sequence[Path] = (),
        cc: Sequence[str] = (),
    ) -> None: ...


class TelcosGateway(Protocol):
    def validate(self, credentials: SessionCredentials, *, headless: bool = True) -> None: ...

    def execute_workflow(
        self,
        credentials: SessionCredentials,
        workflow: WorkflowDefinition,
        tasks: Sequence[TaskRecord],
        *,
        headless: bool,
        progress: Callable[[int, int, str], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> OperationResult: ...

    def reassign(
        self,
        credentials: SessionCredentials,
        tasks: Sequence[TaskRecord],
        department: str,
        employee: str,
        comment_template: str,
        *,
        headless: bool,
        progress: Callable[[int, int, str], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> OperationResult: ...


class OrderDownloadGateway(Protocol):
    def download(
        self,
        credentials: SessionCredentials,
        request: OperationRequest,
        *,
        progress: Callable[[int, int, str], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> OperationResult: ...


class OrderResolver(Protocol):
    def resolve(self, order_number: str) -> OrderRecord: ...


class SheetGateway(Protocol):
    def read_task_orders(self, numbers: list[str]) -> dict[str, list[dict]]: ...
    def record_approvers(self, draft: PurchaseOrderDraft, number: str, names: list[str]) -> None: ...
    def read_purchase_task_status(self) -> dict[str, Any]: ...
    def read_approved_orders(self) -> list[dict[str, Any]]: ...
    def read_purchase_order_drafts(self) -> list[PurchaseOrderDraft]: ...
    def record_purchase_order(self, draft: PurchaseOrderDraft, order_number: str) -> None: ...
    def validate_purchase_order(self, draft: PurchaseOrderDraft) -> None: ...


class PurchaseOrderGateway(Protocol):
    def recover_approvers(self, credentials: SessionCredentials, entries: Sequence[dict],
                         callback: Callable[[PurchaseOrderDraft, str, Any], None], *, headless: bool = False,
                         progress: Callable[[int, int, str], None] | None = None,
                         cancelled: Callable[[], bool] | None = None) -> OperationResult: ...
    def preload(
        self,
        credentials: SessionCredentials,
        drafts: Sequence[PurchaseOrderDraft],
        *,
        headless: bool = False,
        progress: Callable[[int, int, str], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
        before_save: Callable[[PurchaseOrderDraft], None] | None = None,
        on_saved: Callable[[PurchaseOrderDraft, str], None] | None = None,
        after_saved: Callable[[PurchaseOrderDraft, str, Any], None] | None = None,
    ) -> OperationResult: ...


class TemplateRenderer(Protocol):
    def render(self, template: EmailTemplate, context: dict[str, Any]) -> str: ...


class OrderMailScanner(Protocol):
    def validate(self, credentials: SessionCredentials) -> None: ...
    def scan(
        self,
        credentials: SessionCredentials,
        *,
        progress: Callable[[int, int, str], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> list[ScannedOrderMessage]: ...
    def mark_processed(self, external_ids: Sequence[str]) -> None: ...


class ReportGateway(Protocol):
    def write(self, request: OperationRequest, result: OperationResult) -> Path: ...


class SeafileRepository(Protocol):
    def list_dir(self, path: str) -> list[dict[str, Any]]: ...
    def ensure_dir(self, path: str) -> None: ...
    def content_hash(self, path: str) -> str: ...
    def upload_verified(self, path: Path, parent: str) -> str: ...


class SeafileGateway(Protocol):
    def batch(self) -> AbstractContextManager[Any]: ...
    def connection(
        self, credentials: SessionCredentials, repo_id: str
    ) -> AbstractContextManager[SeafileRepository]: ...
    def validate(self, credentials: SessionCredentials) -> None: ...
    def upload(
        self,
        credentials: SessionCredentials,
        file_path: Path,
        repo_id: str,
        parent_dir: str = "/",
    ) -> str: ...
