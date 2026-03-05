"""student_enrollments table + classes capacity & schedule columns

Revision ID: 20260304_0001
Revises: 20260303_0001
Create Date: 2026-03-04 00:01:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '20260304_0001'
down_revision = '20260303_0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add capacity + schedule detail columns to classes (use IF NOT EXISTS to be idempotent)
    conn = op.get_bind()
    conn.execute(sa.text("ALTER TABLE classes ADD COLUMN IF NOT EXISTS capacity INTEGER"))
    conn.execute(sa.text("ALTER TABLE classes ADD COLUMN IF NOT EXISTS subject VARCHAR(100)"))
    conn.execute(sa.text("ALTER TABLE classes ADD COLUMN IF NOT EXISTS room VARCHAR(50)"))
    conn.execute(sa.text("ALTER TABLE classes ADD COLUMN IF NOT EXISTS academic_year VARCHAR(20)"))
    conn.execute(sa.text("ALTER TABLE classes ADD COLUMN IF NOT EXISTS schedule JSON"))
    conn.execute(sa.text("ALTER TABLE classes ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP"))

    # 2. Create student_enrollments pivot table (many-to-many)
    op.create_table(
        'student_enrollments',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('student_id', sa.Integer(), sa.ForeignKey('students.id', ondelete='CASCADE'), nullable=False),
        sa.Column('class_id',   sa.Integer(), sa.ForeignKey('classes.id',  ondelete='CASCADE'), nullable=False),
        sa.Column('status',     sa.String(10), nullable=False, server_default='active'),  # active | dropped
        sa.Column('enrolled_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_student_enrollments_student_id', 'student_enrollments', ['student_id'])
    op.create_index('ix_student_enrollments_class_id',   'student_enrollments', ['class_id'])
    op.create_unique_constraint(
        'uq_student_class', 'student_enrollments', ['student_id', 'class_id']
    )

    # 3. Migrate existing student.class_id → student_enrollments
    op.execute("""
        INSERT INTO student_enrollments (student_id, class_id, status)
        SELECT id, class_id, 'active'
        FROM students
        WHERE class_id IS NOT NULL
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.drop_table('student_enrollments')
    op.drop_column('classes', 'updated_at')
    op.drop_column('classes', 'capacity')
    op.drop_column('classes', 'academic_year')
    op.drop_column('classes', 'room')
    op.drop_column('classes', 'subject')
