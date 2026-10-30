"""audit log project id

Revision ID: d2f6b8c4e5a7
Revises: c7e4a9b2d1f3
Create Date: 2026-10-30 18:00:00.000000

"""
import json

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd2f6b8c4e5a7'
down_revision = 'c7e4a9b2d1f3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('project_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_audit_logs_project_id'), ['project_id'], unique=False)
        batch_op.create_foreign_key('fk_audit_logs_project_id', 'projects', ['project_id'], ['id'])

    # Backfill existing entries with the same rule as services.audit.project_id_for.
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, entity_type, entity_id, meta FROM audit_logs")).fetchall()
    for row_id, entity_type, entity_id, meta in rows:
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except ValueError:
                meta = None
        project_id = None
        if entity_type == 'project':
            project_id = entity_id
        elif isinstance(meta, dict) and isinstance(meta.get('project_id'), int):
            project_id = meta['project_id']
        if project_id is not None:
            conn.execute(
                sa.text("UPDATE audit_logs SET project_id = :p WHERE id = :i"), {"p": project_id, "i": row_id}
            )


def downgrade():
    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        batch_op.drop_constraint('fk_audit_logs_project_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_audit_logs_project_id'))
        batch_op.drop_column('project_id')
