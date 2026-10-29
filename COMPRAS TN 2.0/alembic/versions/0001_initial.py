"""Esquema inicial de COMPRAS TN 2.0."""

import sqlalchemy as sa

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "suppliers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(250), nullable=False),
        sa.Column("ruc", sa.String(30), nullable=False, unique=True),
        sa.Column("email_primary", sa.String(320), nullable=False),
        sa.Column("email_secondary", sa.String(320), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_suppliers_name", "suppliers", ["name"])
    op.create_table(
        "assignments",
        sa.Column("subdepartment", sa.String(160), primary_key=True),
        sa.Column("department", sa.String(160), nullable=False),
        sa.Column("person", sa.String(160), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "email_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False, unique=True),
        sa.Column("html", sa.Text(), nullable=False),
        sa.Column("signature_path", sa.Text(), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "workflow_definitions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False, unique=True),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("steps_json", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "settings",
        sa.Column("namespace", sa.String(80), primary_key=True),
        sa.Column("key", sa.String(160), primary_key=True),
        sa.Column("value_json", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "processed_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(80), nullable=False),
        sa.Column("external_id", sa.String(300), nullable=False),
        sa.Column("raw_hash", sa.String(128), nullable=False, server_default=""),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source", "external_id", name="uq_processed_source_external"),
    )
    op.create_index("ix_processed_hash", "processed_messages", ["raw_hash"])
    op.create_table(
        "source_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(80), nullable=False),
        sa.Column("external_id", sa.String(300), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("subject", sa.Text(), nullable=False, server_default=""),
        sa.Column("sender", sa.Text(), nullable=False, server_default=""),
        sa.Column("task_number", sa.String(80), nullable=False, server_default=""),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("raw_hash", sa.String(128), nullable=False, server_default=""),
        sa.UniqueConstraint("source", "external_id", name="uq_source_message_external"),
    )
    op.create_table(
        "task_inbox",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("origin", sa.String(80), nullable=False),
        sa.Column("task_number", sa.String(80), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_task_inbox_pending", "task_inbox", ["status", "origin"])
    op.create_table(
        "operation_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(80), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("request_json", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "operation_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("operation_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_key", sa.String(200), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
    )
    op.create_table(
        "migration_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("summary_json", sa.Text(), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    for table in (
        "migration_records",
        "operation_items",
        "operation_runs",
        "task_inbox",
        "source_messages",
        "processed_messages",
        "settings",
        "workflow_definitions",
        "email_templates",
        "assignments",
        "suppliers",
    ):
        op.drop_table(table)

