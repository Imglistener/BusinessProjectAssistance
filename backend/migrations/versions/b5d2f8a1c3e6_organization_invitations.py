"""organization invitations

Revision ID: b5d2f8a1c3e6
Revises: a3c9e1f2b7d4
Create Date: 2026-10-30 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'b5d2f8a1c3e6'
down_revision = 'a3c9e1f2b7d4'
branch_labels = None
depends_on = None


def upgrade():
    # The 'role' enum type already exists (created with organization_members); reuse it.
    role = postgresql.ENUM('OWNER', 'PROJECT_MANAGER', 'CONTRIBUTOR', 'VIEWER', 'SYSTEM_ADMIN', name='role', create_type=False)
    op.create_table('organization_invitations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('organization_id', sa.Integer(), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('role', role, nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('invited_by', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['invited_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )
    with op.batch_alter_table('organization_invitations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_organization_invitations_email'), ['email'], unique=False)
        batch_op.create_index(batch_op.f('ix_organization_invitations_organization_id'), ['organization_id'], unique=False)


def downgrade():
    with op.batch_alter_table('organization_invitations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_organization_invitations_organization_id'))
        batch_op.drop_index(batch_op.f('ix_organization_invitations_email'))

    op.drop_table('organization_invitations')
