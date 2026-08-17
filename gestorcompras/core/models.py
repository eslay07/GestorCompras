"""Modelos inmutables usados por los adaptadores de demostración."""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True, slots=True)
class Supplier:
    supplier_id: str
    name: str
    contact_email: str
    demo_identifier: str = "0000000000000"


@dataclass(frozen=True, slots=True)
class PurchaseTask:
    task_id: str
    order_id: str
    summary: str
    supplier_id: str
    owner: str
    status: str

    def reassigned(self, supplier_id: str) -> "PurchaseTask":
        return replace(self, supplier_id=supplier_id, status="Reasignada en demo")

    def completed(self) -> "PurchaseTask":
        return replace(self, status="Actualizada en demo")


@dataclass(frozen=True, slots=True)
class DemoMessage:
    message_id: str
    recipient: str
    subject: str
    preview: str
    status: str


@dataclass(frozen=True, slots=True)
class DemoDocument:
    document_id: str
    order_id: str
    filename: str
    supplier_name: str
    status: str


@dataclass(frozen=True, slots=True)
class OperationResult:
    ok: bool
    message: str
    reference: str
