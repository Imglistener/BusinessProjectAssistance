"""AI provider choice: exhausted providers, and which one answered

Revision ID: b3d5f7a9c1e2
Revises: a2c4e6f8b0d1
Create Date: 2026-11-24 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b3d5f7a9c1e2'
down_revision = 'a2c4e6f8b0d1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'ai_provider_status',
        sa.Column('provider', sa.String(length=30), nullable=False),
        sa.Column('exhausted_until', sa.DateTime(timezone=True), nullable=False),
        sa.Column('daily', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('provider'),
    )
    with op.batch_alter_table('ai_messages', schema=None) as batch_op:
        batch_op.add_column(sa.Column('provider', sa.String(length=30), nullable=True))


def downgrade():
    with op.batch_alter_table('ai_messages', schema=None) as batch_op:
        batch_op.drop_column('provider')
    op.drop_table('ai_provider_status')
