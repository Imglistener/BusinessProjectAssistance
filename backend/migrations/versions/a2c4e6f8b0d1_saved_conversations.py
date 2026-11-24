"""saved assistant conversations: organization, title, last activity, draft count

Revision ID: a2c4e6f8b0d1
Revises: f7b9d1e3a5c8
Create Date: 2026-11-21 15:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a2c4e6f8b0d1'
down_revision = 'f7b9d1e3a5c8'
branch_labels = None
depends_on = None


def upgrade():
    # The tables were created early but never written to; clear them so the new columns can be required.
    op.execute("DELETE FROM ai_messages")
    op.execute("DELETE FROM ai_conversations")
    with op.batch_alter_table('ai_conversations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('organization_id', sa.Integer(), nullable=False))
        batch_op.add_column(sa.Column('title', sa.String(length=120), nullable=False))
        batch_op.add_column(sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False))
        batch_op.create_foreign_key('fk_ai_conversations_organization_id', 'organizations', ['organization_id'], ['id'])
        batch_op.create_index(batch_op.f('ix_ai_conversations_organization_id'), ['organization_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ai_conversations_updated_at'), ['updated_at'], unique=False)
    with op.batch_alter_table('ai_messages', schema=None) as batch_op:
        batch_op.add_column(sa.Column('drafts', sa.Integer(), nullable=False, server_default='0'))


def downgrade():
    with op.batch_alter_table('ai_messages', schema=None) as batch_op:
        batch_op.drop_column('drafts')
    with op.batch_alter_table('ai_conversations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ai_conversations_updated_at'))
        batch_op.drop_index(batch_op.f('ix_ai_conversations_organization_id'))
        batch_op.drop_constraint('fk_ai_conversations_organization_id', type_='foreignkey')
        batch_op.drop_column('updated_at')
        batch_op.drop_column('title')
        batch_op.drop_column('organization_id')
