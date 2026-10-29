from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


class PurchaseMode(StrEnum):
    BIENES = "bienes"
    SERVICIOS = "servicios"
    GENERAL = "general"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ItemStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    NOT_FOUND = "not_found"
    SKIPPED = "skipped"
    FAILED = "failed"


class DomainModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True)


class Supplier(DomainModel):
    id: int | None = None
    name: str = Field(min_length=1)
    ruc: str = Field(min_length=1)
    email_primary: str = ""
    email_secondary: str = ""
    nickname: str = ""
    nickname_2: str = ""
    nickname_3: str = ""

    @field_validator("ruc", mode="before")
    @classmethod
    def preserve_ruc(cls, value: Any) -> str:
        return str(value or "").strip()


class Assignment(DomainModel):
    subdepartment: str = Field(min_length=1)
    department: str = Field(min_length=1)
    person: str = Field(min_length=1)


class EmailTemplate(DomainModel):
    id: int | None = None
    name: str = Field(min_length=1)
    html: str = Field(min_length=1)
    signature_path: str = ""


class FlowStep(DomainModel):
    action_id: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)


class WorkflowDefinition(DomainModel):
    id: int | None = None
    name: str = Field(min_length=1)
    mode: PurchaseMode = PurchaseMode.GENERAL
    version: int = 1
    enabled: bool = True
    stop_on_error: bool = True
    steps: list[FlowStep] = Field(default_factory=list)
    updated_at: datetime | None = None


class TaskRecord(DomainModel):
    task_number: str = Field(min_length=1)
    origin: str = "manual"
    purchase_mode: PurchaseMode = PurchaseMode.GENERAL
    order_number: str = ""
    supplier: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class OrderRecord(DomainModel):
    order_number: str = Field(min_length=1)
    task_number: str = ""
    task_numbers: list[str] = Field(default_factory=list)
    supplier: str = ""
    ruc: str = ""
    pdf_path: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class DispatchPreviewItem(DomainModel):
    order_number: str = Field(min_length=1)
    valid: bool = False
    error: str = ""
    task_numbers: list[str] = Field(default_factory=list)
    supplier: str = ""
    ruc: str = ""
    recipients: list[str] = Field(default_factory=list)
    cc: list[str] = Field(default_factory=list)
    pdf_path: str = ""
    pdf_mtime_ns: int = 0
    pdf_size: int = 0


class DispatchPreview(DomainModel):
    items: list[DispatchPreviewItem] = Field(default_factory=list)

    @property
    def valid_count(self) -> int:
        return sum(item.valid for item in self.items)


class ScannedOrderMessage(DomainModel):
    external_id: str = Field(min_length=1)
    orders: list[dict[str, Any]] = Field(default_factory=list)
    subject: str = ""
    sender: str = ""


class SessionCredentials(DomainModel):
    username: str = Field(min_length=1)
    email: str = Field(min_length=3)
    password: str = Field(min_length=1, repr=False, exclude=True)

    def redacted(self) -> dict[str, str]:
        return {"username": self.username, "email": self.email, "password": "***"}


class OperationItem(DomainModel):
    key: str
    status: ItemStatus
    message: str = ""
    error_code: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class OperationRequest(DomainModel):
    kind: str
    mode: PurchaseMode = PurchaseMode.GENERAL
    items: list[dict[str, Any]] = Field(default_factory=list)
    options: dict[str, Any] = Field(default_factory=dict)


class OperationResult(DomainModel):
    status: JobStatus
    items: list[OperationItem] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime | None = None
    message: str = ""
    report_path: str = ""

    @classmethod
    def from_items(cls, items: list[OperationItem], message: str = "") -> OperationResult:
        statuses = {item.status for item in items}
        if not statuses or statuses <= {ItemStatus.SUCCEEDED, ItemStatus.SKIPPED}:
            status = JobStatus.SUCCEEDED
        elif statuses & {ItemStatus.SUCCEEDED, ItemStatus.SKIPPED}:
            status = JobStatus.PARTIAL
        else:
            status = JobStatus.FAILED
        return cls(status=status, items=items, finished_at=utc_now(), message=message)


class PurchaseOrderArticle(DomainModel):
    source_supplier: str = ""
    code: str = Field(min_length=1)
    description: str = Field(min_length=1)
    quantity: Decimal
    unit_price: Decimal
    source_row: int = Field(ge=1)


class PurchaseOrderDraft(DomainModel):
    supplier_reference: str = ""
    task_number: str = Field(min_length=1)
    supplier: str = Field(min_length=1)
    ruc: str = ""
    requester: str = ""
    pedido: str = "S/N"
    department: str = ""
    detail: str = ""
    existing_order: str = ""
    articles: list[PurchaseOrderArticle] = Field(default_factory=list)
    source_rows: list[int] = Field(default_factory=list)
    validation_errors: list[str] = Field(default_factory=list)
    sources: list[PurchaseOrderDraft] = Field(default_factory=list)
    split_part: int = 0
    split_total: int = 0

    @property
    def operation_key(self) -> str:
        base = f"{self.task_number} · {self.supplier}"
        return base + (f" · Parte {self.split_part}/{self.split_total}" if self.split_total > 1 else "")

    @property
    def original_drafts(self) -> list[PurchaseOrderDraft]:
        return self.sources or [self]

    @property
    def task_numbers(self) -> list[str]:
        return list(dict.fromkeys(source.task_number for source in self.original_drafts))

    @property
    def original_articles(self) -> list[PurchaseOrderArticle]:
        return [article for source in self.original_drafts for article in source.articles]

    @property
    def subtotal(self) -> Decimal:
        return sum(
            (article.quantity * article.unit_price for article in self.articles),
            start=Decimal("0"),
        )

    @property
    def is_valid(self) -> bool:
        return bool(self.articles) and not self.validation_errors
