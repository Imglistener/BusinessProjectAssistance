"""fuel price source and fetch time

Revision ID: d4f6b8c0e2a5
Revises: c3e5a7b9d1f4
Create Date: 2026-10-31 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4f6b8c0e2a5'
down_revision = 'c3e5a7b9d1f4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('fuel_prices', schema=None) as batch_op:
        batch_op.add_column(sa.Column('source', sa.String(length=20), nullable=False, server_default='manual'))
        batch_op.add_column(sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    with op.batch_alter_table('fuel_prices', schema=None) as batch_op:
        batch_op.drop_column('fetched_at')
        batch_op.drop_column('source')
