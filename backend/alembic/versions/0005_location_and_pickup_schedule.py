"""add tenant location and package scheduled pickup

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("tenants") as batch_op:
        batch_op.add_column(sa.Column("latitude", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("longitude", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("maps_url", sa.String(length=300), nullable=False, server_default=""))

    with op.batch_alter_table("packages") as batch_op:
        batch_op.add_column(sa.Column("scheduled_pickup_at", sa.String(length=120), nullable=False, server_default=""))


def downgrade() -> None:
    with op.batch_alter_table("packages") as batch_op:
        batch_op.drop_column("scheduled_pickup_at")

    with op.batch_alter_table("tenants") as batch_op:
        batch_op.drop_column("maps_url")
        batch_op.drop_column("longitude")
        batch_op.drop_column("latitude")
