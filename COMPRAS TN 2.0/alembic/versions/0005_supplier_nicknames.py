"""Add second and third case-insensitive supplier nicknames."""

import sqlalchemy as sa

from alembic import op

revision = "0005_supplier_nicknames"
down_revision = "0004_supplier_nickname"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "suppliers",
        sa.Column("nickname_2", sa.String(length=250), nullable=False, server_default=""),
    )
    op.add_column(
        "suppliers",
        sa.Column("nickname_3", sa.String(length=250), nullable=False, server_default=""),
    )
    op.execute(
        """CREATE UNIQUE INDEX uq_suppliers_nickname_2_nocase
        ON suppliers (nickname_2 COLLATE NOCASE)
        WHERE TRIM(nickname_2) <> ''"""
    )
    op.execute(
        """CREATE UNIQUE INDEX uq_suppliers_nickname_3_nocase
        ON suppliers (nickname_3 COLLATE NOCASE)
        WHERE TRIM(nickname_3) <> ''"""
    )


def downgrade():
    op.drop_index("uq_suppliers_nickname_3_nocase", table_name="suppliers")
    op.drop_index("uq_suppliers_nickname_2_nocase", table_name="suppliers")
    op.drop_column("suppliers", "nickname_3")
    op.drop_column("suppliers", "nickname_2")
