"""trips, itinerary items, travelers; expenses.trip_id

Revision ID: f1b4d6e8a2c3
Revises: e8a3c5d7f9b1
Create Date: 2026-10-30 22:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f1b4d6e8a2c3'
down_revision = 'e8a3c5d7f9b1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('trips',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('destination', sa.String(length=200), nullable=False),
    sa.Column('purpose', sa.Text(), nullable=True),
    sa.Column('start_date', sa.Date(), nullable=False),
    sa.Column('end_date', sa.Date(), nullable=False),
    sa.Column('status', sa.Enum('PLANNED', 'BOOKED', 'COMPLETED', 'CANCELLED', name='tripstatus'), nullable=False),
    sa.Column('budget', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('trips', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_trips_project_id'), ['project_id'], unique=False)

    op.create_table('trip_items',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('trip_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.Enum('FLIGHT', 'TRAIN', 'CAR', 'HOTEL', 'MEETING', 'OTHER', name='tripitemkind'), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('start_time', sa.String(length=5), nullable=True),
    sa.Column('end_time', sa.String(length=5), nullable=True),
    sa.Column('location', sa.String(length=200), nullable=True),
    sa.Column('confirmation', sa.String(length=100), nullable=True),
    sa.Column('estimated_cost', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['trip_id'], ['trips.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('trip_items', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_trip_items_trip_id'), ['trip_id'], unique=False)

    op.create_table('trip_travelers',
    sa.Column('trip_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['trip_id'], ['trips.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('trip_id', 'user_id')
    )

    with op.batch_alter_table('expenses', schema=None) as batch_op:
        batch_op.add_column(sa.Column('trip_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_expenses_trip_id'), ['trip_id'], unique=False)
        batch_op.create_foreign_key('fk_expenses_trip_id', 'trips', ['trip_id'], ['id'])


def downgrade():
    with op.batch_alter_table('expenses', schema=None) as batch_op:
        batch_op.drop_constraint('fk_expenses_trip_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_expenses_trip_id'))
        batch_op.drop_column('trip_id')
    op.drop_table('trip_travelers')
    with op.batch_alter_table('trip_items', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_trip_items_trip_id'))
    op.drop_table('trip_items')
    with op.batch_alter_table('trips', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_trips_project_id'))
    op.drop_table('trips')
    sa.Enum(name='tripitemkind').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='tripstatus').drop(op.get_bind(), checkfirst=True)
