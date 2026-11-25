"""add one payment per package

Revision ID: 0004
Revises: 0003
"""

from alembic import op


revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM payments
        WHERE id NOT IN (
            SELECT MIN(id) FROM payments GROUP BY package_id
        )
        """
    )
    with op.batch_alter_table("payments") as batch_op:
        batch_op.create_unique_constraint("uq_payments_package_id", ["package_id"])


def downgrade() -> None:
    with op.batch_alter_table("payments") as batch_op:
        batch_op.drop_constraint("uq_payments_package_id", type="unique")
