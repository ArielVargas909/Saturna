"""add processed whatsapp messages

Revision ID: 0002
Revises: 0001
"""

from alembic import op
import sqlalchemy as sa


revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "processed_messages",
        sa.Column("message_id", sa.String(length=120), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("message_id"),
    )
    op.create_index(
        op.f("ix_processed_messages_tenant_id"),
        "processed_messages",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_processed_messages_tenant_id"), table_name="processed_messages")
    op.drop_table("processed_messages")
