"""Add editable, case-insensitive supplier nicknames."""

import sqlalchemy as sa

from alembic import op

revision = "0004_supplier_nickname"
down_revision = "0003_transfers"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "suppliers",
        sa.Column("nickname", sa.String(length=250), nullable=False, server_default=""),
    )
    op.execute(
        """CREATE UNIQUE INDEX uq_suppliers_nickname_nocase
        ON suppliers (nickname COLLATE NOCASE)
        WHERE TRIM(nickname) <> ''"""
    )


def downgrade():
    op.drop_index("uq_suppliers_nickname_nocase", table_name="suppliers")
    op.drop_column("suppliers", "nickname")
