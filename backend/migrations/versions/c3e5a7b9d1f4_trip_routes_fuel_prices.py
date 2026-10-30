"""trip routes and fuel prices

Revision ID: c3e5a7b9d1f4
Revises: b9d1f3a5c7e2
Create Date: 2026-10-31 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3e5a7b9d1f4'
down_revision = 'b9d1f3a5c7e2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('trips', schema=None) as batch_op:
        batch_op.add_column(sa.Column('origin', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('origin_lat', sa.Numeric(precision=9, scale=6), nullable=True))
        batch_op.add_column(sa.Column('origin_lng', sa.Numeric(precision=9, scale=6), nullable=True))
        batch_op.add_column(sa.Column('destination_lat', sa.Numeric(precision=9, scale=6), nullable=True))
        batch_op.add_column(sa.Column('destination_lng', sa.Numeric(precision=9, scale=6), nullable=True))
        batch_op.add_column(sa.Column('distance_km', sa.Numeric(precision=9, scale=1), nullable=True))
        batch_op.add_column(sa.Column('distance_source', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('vehicle_type', sa.String(length=30), nullable=True))
        batch_op.add_column(sa.Column('vehicle_count', sa.Integer(), nullable=False, server_default='1'))
        batch_op.add_column(sa.Column('round_trip', sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.add_column(sa.Column('fuel_city', sa.String(length=80), nullable=True))

    op.create_table('fuel_prices',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('organization_id', sa.Integer(), nullable=False),
    sa.Column('city', sa.String(length=80), nullable=False),
    sa.Column('fuel_type', sa.Enum('PETROL', 'DIESEL', name='fueltype'), nullable=False),
    sa.Column('price_per_litre', sa.Numeric(precision=8, scale=2), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('as_of', sa.Date(), nullable=False),
    sa.Column('updated_by', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'city', 'fuel_type')
    )
    with op.batch_alter_table('fuel_prices', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_fuel_prices_organization_id'), ['organization_id'], unique=False)


def downgrade():
    with op.batch_alter_table('fuel_prices', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_fuel_prices_organization_id'))
    op.drop_table('fuel_prices')
    sa.Enum(name='fueltype').drop(op.get_bind(), checkfirst=True)
    with op.batch_alter_table('trips', schema=None) as batch_op:
        for col in ('fuel_city', 'round_trip', 'vehicle_count', 'vehicle_type', 'distance_source', 'distance_km',
                    'destination_lng', 'destination_lat', 'origin_lng', 'origin_lat', 'origin'):
            batch_op.drop_column(col)
