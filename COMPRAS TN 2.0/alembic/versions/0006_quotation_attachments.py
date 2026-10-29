"""Durable quotation attachment review and delivery history."""
from alembic import op

revision = "0006_quotation_attachments"
down_revision = "0005_supplier_nicknames"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE quotation_attachments (
        identity TEXT PRIMARY KEY,
        account TEXT NOT NULL,
        payload TEXT NOT NULL,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    op.execute("CREATE INDEX ix_quotation_account ON quotation_attachments(account)")


def downgrade():
    op.drop_table("quotation_attachments")
