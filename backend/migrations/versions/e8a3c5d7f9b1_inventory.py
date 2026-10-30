"""inventory items and movements (replace unused resources tables)

Revision ID: e8a3c5d7f9b1
Revises: d2f6b8c4e5a7
Create Date: 2026-10-30 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e8a3c5d7f9b1'
down_revision = 'd2f6b8c4e5a7'
branch_labels = None
depends_on = None


def upgrade():
    # resources/project_resources were never exposed by the API. Refuse to drop them if anyone put data there.
    conn = op.get_bind()
    for table in ('project_resources', 'resources'):
        if conn.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar():
            raise RuntimeError(f"Table {table} has rows; migrate them to inventory_items by hand first.")
    with op.batch_alter_table('project_resources', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_project_resources_project_id'))
    op.drop_table('project_resources')
    with op.batch_alter_table('resources', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_resources_organization_id'))
    op.drop_table('resources')

    op.create_table('inventory_items',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('organization_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('sku', sa.String(length=60), nullable=True),
    sa.Column('unit', sa.String(length=20), nullable=False),
    sa.Column('unit_cost', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('quantity_on_hand', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('reorder_level', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('location', sa.String(length=120), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('archived', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('inventory_items', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_inventory_items_organization_id'), ['organization_id'], unique=False)

    op.create_table('inventory_movements',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('organization_id', sa.Integer(), nullable=False),
    sa.Column('item_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.Enum('RECEIVE', 'ISSUE', 'ADJUST', 'COUNT', name='movementkind'), nullable=False),
    sa.Column('quantity_delta', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('quantity_after', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=True),
    sa.Column('note', sa.String(length=500), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['item_id'], ['inventory_items.id'], ),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('inventory_movements', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_inventory_movements_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_inventory_movements_item_id'), ['item_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_inventory_movements_organization_id'), ['organization_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_inventory_movements_project_id'), ['project_id'], unique=False)


def downgrade():
    with op.batch_alter_table('inventory_movements', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_inventory_movements_project_id'))
        batch_op.drop_index(batch_op.f('ix_inventory_movements_organization_id'))
        batch_op.drop_index(batch_op.f('ix_inventory_movements_item_id'))
        batch_op.drop_index(batch_op.f('ix_inventory_movements_created_at'))
    op.drop_table('inventory_movements')
    sa.Enum(name='movementkind').drop(op.get_bind(), checkfirst=True)
    with op.batch_alter_table('inventory_items', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_inventory_items_organization_id'))
    op.drop_table('inventory_items')

    op.create_table('resources',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('organization_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('type', sa.String(length=60), nullable=True),
    sa.Column('unit_cost', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('resources', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_resources_organization_id'), ['organization_id'], unique=False)
    op.create_table('project_resources',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('resource_id', sa.Integer(), nullable=False),
    sa.Column('quantity', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('total_cost', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.ForeignKeyConstraint(['resource_id'], ['resources.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('project_resources', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_project_resources_project_id'), ['project_id'], unique=False)
