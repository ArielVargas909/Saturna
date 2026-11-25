"""add simulated notification state

Revision ID: 0003
Revises: 0002
"""

from alembic import op
import sqlalchemy as sa


revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("notifications") as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=sa.String(length=10),
            type_=sa.String(length=12),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "meta_message_id",
            existing_type=sa.String(length=120),
            nullable=True,
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("notifications") as batch_op:
        batch_op.alter_column(
            "meta_message_id",
            existing_type=sa.String(length=120),
            nullable=False,
            existing_nullable=True,
        )
        batch_op.alter_column(
            "status",
            existing_type=sa.String(length=12),
            type_=sa.String(length=10),
            existing_nullable=False,
        )
