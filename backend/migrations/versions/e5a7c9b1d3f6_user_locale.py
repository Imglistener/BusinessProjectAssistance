"""user locale for emails and notifications

Revision ID: e5a7c9b1d3f6
Revises: d4f6b8c0e2a5
Create Date: 2026-10-31 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5a7c9b1d3f6'
down_revision = 'd4f6b8c0e2a5'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('locale', sa.String(length=5), nullable=False, server_default='en'))


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('locale')
