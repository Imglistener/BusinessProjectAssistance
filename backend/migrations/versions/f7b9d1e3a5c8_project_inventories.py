"""project inventories, warehouses and stock per warehouse

Revision ID: f7b9d1e3a5c8
Revises: e5a7c9b1d3f6
Create Date: 2026-11-01 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f7b9d1e3a5c8'
down_revision = 'e5a7c9b1d3f6'
branch_labels = None
depends_on = None

OLD_KINDS = ('RECEIVE', 'ISSUE', 'ADJUST', 'COUNT')
NEW_KINDS = ('TRANSFER', 'MOVE_OUT', 'MOVE_IN')


def upgrade():
    if op.get_bind().dialect.name == 'postgresql':
        # New values of the native enum; ALTER TYPE ... ADD VALUE can't run inside a transaction block.
        with op.get_context().autocommit_block():
            for kind in NEW_KINDS:
                op.execute(f"ALTER TYPE movementkind ADD VALUE IF NOT EXISTS '{kind}'")
    else:
        # Elsewhere the enum is a VARCHAR sized to the longest value; MOVE_OUT is longer than RECEIVE.
        with op.batch_alter_table('inventory_movements', schema=None) as batch_op:
            batch_op.alter_column(
                'kind',
                existing_type=sa.Enum(*OLD_KINDS, name='movementkind'),
                type_=sa.Enum(*OLD_KINDS, *NEW_KINDS, name='movementkind'),
                existing_nullable=False,
            )

    op.create_table(
        'warehouses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('address', sa.String(length=300), nullable=True),
        sa.Column('lat', sa.Float(), nullable=True),
        sa.Column('lng', sa.Float(), nullable=True),
        sa.Column('notes', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('warehouses', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_warehouses_organization_id'), ['organization_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_warehouses_project_id'), ['project_id'], unique=False)

    op.create_table(
        'inventory_stock',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('item_id', sa.Integer(), nullable=False),
        sa.Column('warehouse_id', sa.Integer(), nullable=False),
        sa.Column('quantity', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.ForeignKeyConstraint(['item_id'], ['inventory_items.id']),
        sa.ForeignKeyConstraint(['warehouse_id'], ['warehouses.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('item_id', 'warehouse_id', name='uq_inventory_stock_item_warehouse'),
    )
    with op.batch_alter_table('inventory_stock', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_inventory_stock_item_id'), ['item_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_inventory_stock_warehouse_id'), ['warehouse_id'], unique=False)

    # Existing items have no project: they become General stock.
    with op.batch_alter_table('inventory_items', schema=None) as batch_op:
        batch_op.add_column(sa.Column('project_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_inventory_items_project_id'), ['project_id'], unique=False)
        batch_op.create_foreign_key('fk_inventory_items_project_id', 'projects', ['project_id'], ['id'])

    with op.batch_alter_table('inventory_movements', schema=None) as batch_op:
        batch_op.add_column(sa.Column('warehouse_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('to_warehouse_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_inventory_movements_warehouse_id', 'warehouses', ['warehouse_id'], ['id'])
        batch_op.create_foreign_key('fk_inventory_movements_to_warehouse_id', 'warehouses', ['to_warehouse_id'], ['id'])


def downgrade():
    with op.batch_alter_table('inventory_movements', schema=None) as batch_op:
        batch_op.drop_constraint('fk_inventory_movements_to_warehouse_id', type_='foreignkey')
        batch_op.drop_constraint('fk_inventory_movements_warehouse_id', type_='foreignkey')
        batch_op.drop_column('to_warehouse_id')
        batch_op.drop_column('warehouse_id')

    with op.batch_alter_table('inventory_items', schema=None) as batch_op:
        batch_op.drop_constraint('fk_inventory_items_project_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_inventory_items_project_id'))
        batch_op.drop_column('project_id')

    with op.batch_alter_table('inventory_stock', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_inventory_stock_warehouse_id'))
        batch_op.drop_index(batch_op.f('ix_inventory_stock_item_id'))
    op.drop_table('inventory_stock')

    with op.batch_alter_table('warehouses', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_warehouses_project_id'))
        batch_op.drop_index(batch_op.f('ix_warehouses_organization_id'))
    op.drop_table('warehouses')
    if op.get_bind().dialect.name == 'postgresql':
        pass  # Postgres can't drop enum values; TRANSFER / MOVE_OUT / MOVE_IN stay in movementkind (unused).
    else:
        with op.batch_alter_table('inventory_movements', schema=None) as batch_op:
            batch_op.alter_column(
                'kind',
                existing_type=sa.Enum(*OLD_KINDS, *NEW_KINDS, name='movementkind'),
                type_=sa.Enum(*OLD_KINDS, name='movementkind'),
                existing_nullable=False,
            )
