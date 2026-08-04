'''add department and year to attendance_sessions

Revision ID: 7a546000beed
Revises: ac0d76fbe1b5
Create Date: 2026-08-03 14:29:58.820358

'''
from alembic import op
import sqlalchemy as sa

revision = '7a546000beed'
down_revision = 'ac0d76fbe1b5'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    conn.execute(sa.text('PRAGMA foreign_keys = OFF'))
    with op.batch_alter_table('attendance_sessions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('department', sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column('year', sa.Integer(), nullable=True))
        batch_op.drop_constraint(batch_op.f('uq_session_name_date'), type_='unique')
        batch_op.create_index(batch_op.f('ix_attendance_sessions_department'), ['department'], unique=False)
        batch_op.create_index(batch_op.f('ix_attendance_sessions_year'), ['year'], unique=False)
        batch_op.create_unique_constraint('uq_session_name_dept_date', ['name', 'department', 'session_date'])
    conn.execute(sa.text('PRAGMA foreign_keys = ON'))


def downgrade():
    conn = op.get_bind()
    conn.execute(sa.text('PRAGMA foreign_keys = OFF'))
    with op.batch_alter_table('attendance_sessions', schema=None) as batch_op:
        batch_op.drop_constraint('uq_session_name_dept_date', type_='unique')
        batch_op.drop_index(batch_op.f('ix_attendance_sessions_year'))
        batch_op.drop_index(batch_op.f('ix_attendance_sessions_department'))
        batch_op.create_unique_constraint(batch_op.f('uq_session_name_date'), ['name', 'session_date'])
        batch_op.drop_column('year')
        batch_op.drop_column('department')
    conn.execute(sa.text('PRAGMA foreign_keys = ON'))
