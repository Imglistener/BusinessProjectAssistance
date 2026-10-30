"""expense attachments; drop unused expenses.receipt_url

Revision ID: a7c2e4f6b8d0
Revises: f1b4d6e8a2c3
Create Date: 2026-10-31 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a7c2e4f6b8d0'
down_revision = 'f1b4d6e8a2c3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('attachments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('organization_id', sa.Integer(), nullable=False),
    sa.Column('expense_id', sa.Integer(), nullable=False),
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('stored_name', sa.String(length=64), nullable=False),
    sa.Column('content_type', sa.String(length=100), nullable=False),
    sa.Column('size', sa.Integer(), nullable=False),
    sa.Column('uploaded_by', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['expense_id'], ['expenses.id'], ),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ),
    sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('stored_name')
    )
    with op.batch_alter_table('attachments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_attachments_expense_id'), ['expense_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_attachments_organization_id'), ['organization_id'], unique=False)

    # receipt_url was never exposed by the API; refuse to drop it if something was stored there.
    if op.get_bind().execute(sa.text("SELECT COUNT(*) FROM expenses WHERE receipt_url IS NOT NULL")).scalar():
        raise RuntimeError("expenses.receipt_url has values; move them to attachments by hand first.")
    with op.batch_alter_table('expenses', schema=None) as batch_op:
        batch_op.drop_column('receipt_url')


def downgrade():
    with op.batch_alter_table('expenses', schema=None) as batch_op:
        batch_op.add_column(sa.Column('receipt_url', sa.String(length=500), nullable=True))
    with op.batch_alter_table('attachments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_attachments_organization_id'))
        batch_op.drop_index(batch_op.f('ix_attachments_expense_id'))
    op.drop_table('attachments')
