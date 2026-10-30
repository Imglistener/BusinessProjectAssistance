"""password reset tokens

Revision ID: c7e4a9b2d1f3
Revises: b5d2f8a1c3e6
Create Date: 2026-10-30 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c7e4a9b2d1f3'
down_revision = 'b5d2f8a1c3e6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('password_reset_tokens',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )
    with op.batch_alter_table('password_reset_tokens', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_password_reset_tokens_user_id'), ['user_id'], unique=False)


def downgrade():
    with op.batch_alter_table('password_reset_tokens', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_password_reset_tokens_user_id'))

    op.drop_table('password_reset_tokens')
