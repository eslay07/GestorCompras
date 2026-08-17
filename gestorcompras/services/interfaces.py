"""Contratos pequeños para desacoplar la interfaz de sus adaptadores."""

from __future__ import annotations

from typing import Protocol

from gestorcompras.core.models import (
    DemoDocument,
    DemoMessage,
    OperationResult,
    PurchaseTask,
    Supplier,
)


class MailService(Protocol):
    def list_messages(self) -> tuple[DemoMessage, ...]: ...

    def generate(self, recipient: str, order_id: str) -> DemoMessage: ...


class TaskService(Protocol):
    def list_tasks(self) -> tuple[PurchaseTask, ...]: ...

    def list_suppliers(self) -> tuple[Supplier, ...]: ...

    def reassign(self, task_id: str, supplier_id: str) -> OperationResult: ...

    def update(self, task_id: str) -> OperationResult: ...


class StorageService(Protocol):
    def list_documents(self) -> tuple[DemoDocument, ...]: ...

    def download(self, document_id: str) -> OperationResult: ...
