"""Per-workflow batch continuation policy."""
from alembic import op
import sqlalchemy as sa

revision = "0007_workflow_failure_policy"
down_revision = "0006_quotation_attachments"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("workflow_definitions", sa.Column("stop_on_error", sa.Boolean(), nullable=False, server_default="1"))


def downgrade():
    op.drop_column("workflow_definitions", "stop_on_error")
