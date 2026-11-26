"""add scheduled QR dispatch timestamps on packages

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("packages") as batch_op:
        batch_op.add_column(sa.Column("scheduled_qr_send_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("scheduled_qr_sent_at", sa.DateTime(), nullable=True))
        batch_op.create_index("ix_packages_scheduled_qr_send_at", ["scheduled_qr_send_at"])


def downgrade() -> None:
    with op.batch_alter_table("packages") as batch_op:
        batch_op.drop_index("ix_packages_scheduled_qr_send_at")
        batch_op.drop_column("scheduled_qr_sent_at")
        batch_op.drop_column("scheduled_qr_send_at")
