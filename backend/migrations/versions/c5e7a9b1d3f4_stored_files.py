"""uploaded files in the database, for hosts without a persistent disk

Revision ID: c5e7a9b1d3f4
Revises: b3d5f7a9c1e2
Create Date: 2026-11-24 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c5e7a9b1d3f4'
down_revision = 'b3d5f7a9c1e2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'stored_files',
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.Column('data', sa.LargeBinary(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('name'),
    )


def downgrade():
    op.drop_table('stored_files')
