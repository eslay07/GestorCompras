from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class SupplierRow(Base):
    __tablename__ = "suppliers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(250), index=True)
    nickname: Mapped[str] = mapped_column(String(250), default="")
    nickname_2: Mapped[str] = mapped_column(String(250), default="")
    nickname_3: Mapped[str] = mapped_column(String(250), default="")
    ruc: Mapped[str] = mapped_column(String(30), unique=True)
    email_primary: Mapped[str] = mapped_column(String(320))
    email_secondary: Mapped[str] = mapped_column(String(320), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AssignmentRow(Base):
    __tablename__ = "assignments"
    subdepartment: Mapped[str] = mapped_column(String(160), primary_key=True)
    department: Mapped[str] = mapped_column(String(160))
    person: Mapped[str] = mapped_column(String(160))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EmailTemplateRow(Base):
    __tablename__ = "email_templates"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    html: Mapped[str] = mapped_column(Text)
    signature_path: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class WorkflowRow(Base):
    __tablename__ = "workflow_definitions"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    mode: Mapped[str] = mapped_column(String(20))
    version: Mapped[int] = mapped_column(Integer, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    stop_on_error: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    steps_json: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SettingRow(Base):
    __tablename__ = "settings"
    namespace: Mapped[str] = mapped_column(String(80), primary_key=True)
    key: Mapped[str] = mapped_column(String(160), primary_key=True)
    value_json: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ProcessedMessageRow(Base):
    __tablename__ = "processed_messages"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_processed_source_external"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(80))
    external_id: Mapped[str] = mapped_column(String(300))
    raw_hash: Mapped[str] = mapped_column(String(128), default="", index=True)
    status: Mapped[str] = mapped_column(String(40))
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SourceMessageRow(Base):
    __tablename__ = "source_messages"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_source_message_external"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(80))
    external_id: Mapped[str] = mapped_column(String(300))
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    subject: Mapped[str] = mapped_column(Text, default="")
    sender: Mapped[str] = mapped_column(Text, default="")
    task_number: Mapped[str] = mapped_column(String(80), default="")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    raw_hash: Mapped[str] = mapped_column(String(128), default="")


class TaskInboxRow(Base):
    __tablename__ = "task_inbox"
    __table_args__ = (
        Index(
            "uq_task_inbox_pending",
            "origin",
            "task_number",
            unique=True,
            sqlite_where=text("status = 'pending'"),
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    origin: Mapped[str] = mapped_column(String(80))
    task_number: Mapped[str] = mapped_column(String(80))
    mode: Mapped[str] = mapped_column(String(20))
    payload_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OperationRunRow(Base):
    __tablename__ = "operation_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(80))
    mode: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(30))
    request_json: Mapped[str] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    items: Mapped[list[OperationItemRow]] = relationship(cascade="all, delete-orphan")


class OperationItemRow(Base):
    __tablename__ = "operation_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("operation_runs.id", ondelete="CASCADE"))
    item_key: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(30))
    message: Mapped[str] = mapped_column(Text, default="")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")


class MigrationRecordRow(Base):
    __tablename__ = "migration_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_hash: Mapped[str] = mapped_column(String(128), unique=True)
    source_path: Mapped[str] = mapped_column(Text)
    summary_json: Mapped[str] = mapped_column(Text)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
