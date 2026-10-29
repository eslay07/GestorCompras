"""Durable PDF delivery queue."""
from alembic import op

revision = "0003_transfers"
down_revision = "0002_operational_hardening"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE oc_transfers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        identity TEXT NOT NULL UNIQUE,
        pdf_path TEXT NOT NULL,
        sha256 TEXT NOT NULL,
        task_number TEXT NOT NULL,
        repo_id TEXT NOT NULL,
        root_dir TEXT NOT NULL,
        remote_dir TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'pending',
        message TEXT NOT NULL DEFAULT '',
        candidates TEXT NOT NULL DEFAULT '[]',
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")


def downgrade():
    op.drop_table("oc_transfers")
