"""Migrate all integer PKs and FKs to UUID

Revision ID: 20260305_0001
Revises: 20260304_0001
Create Date: 2026-03-05 00:01:00.000000

Strategy:
  1. Enable uuid-ossp extension
  2. Add new uuid columns to all tables
  3. Populate FK uuid shadow columns by joining parent tables
  4. Drop old FK constraints
  5. Swap integer PKs/FKs for UUID ones
  6. Re-add FK constraints as UUID→UUID
"""
from alembic import op
import sqlalchemy as sa

revision = '20260305_0001'
down_revision = '20260304_0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # ── Step 1: Enable uuid-ossp ──────────────────────────────────────────── #
    conn.execute(sa.text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))

    # ── Step 2: Add uuid_id PKs to all tables ────────────────────────────── #
    for table in ('admins', 'classes', 'students', 'devices', 'attendance', 'student_enrollments'):
        conn.execute(sa.text(
            f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS uuid_id UUID DEFAULT uuid_generate_v4()'
        ))

    # ── Step 3: Add UUID FK shadow columns ───────────────────────────────── #
    conn.execute(sa.text('ALTER TABLE classes ADD COLUMN IF NOT EXISTS teacher_uuid UUID'))
    conn.execute(sa.text('ALTER TABLE students ADD COLUMN IF NOT EXISTS class_uuid UUID'))
    conn.execute(sa.text('ALTER TABLE devices  ADD COLUMN IF NOT EXISTS class_uuid UUID'))
    conn.execute(sa.text('ALTER TABLE attendance ADD COLUMN IF NOT EXISTS student_uuid UUID'))
    conn.execute(sa.text('ALTER TABLE attendance ADD COLUMN IF NOT EXISTS class_uuid UUID'))
    conn.execute(sa.text('ALTER TABLE attendance ADD COLUMN IF NOT EXISTS device_uuid UUID'))
    conn.execute(sa.text('ALTER TABLE student_enrollments ADD COLUMN IF NOT EXISTS student_uuid UUID'))
    conn.execute(sa.text('ALTER TABLE student_enrollments ADD COLUMN IF NOT EXISTS class_uuid UUID'))

    # ── Step 4: Populate FK shadow cols from parent tables ───────────────── #
    conn.execute(sa.text('''
        UPDATE classes c
        SET teacher_uuid = a.uuid_id
        FROM admins a
        WHERE a.id = c.teacher_id
          AND c.teacher_id IS NOT NULL
    '''))
    conn.execute(sa.text('''
        UPDATE students s
        SET class_uuid = c.uuid_id
        FROM classes c
        WHERE c.id = s.class_id
          AND s.class_id IS NOT NULL
    '''))
    conn.execute(sa.text('''
        UPDATE devices d
        SET class_uuid = c.uuid_id
        FROM classes c
        WHERE c.id = d.class_id
          AND d.class_id IS NOT NULL
    '''))
    conn.execute(sa.text('''
        UPDATE attendance att
        SET student_uuid = s.uuid_id,
            class_uuid   = c.uuid_id,
            device_uuid  = (SELECT d.uuid_id FROM devices d WHERE d.id = att.device_id)
        FROM students s, classes c
        WHERE s.id = att.student_id
          AND c.id = att.class_id
    '''))
    conn.execute(sa.text('''
        UPDATE student_enrollments se
        SET student_uuid = s.uuid_id,
            class_uuid   = c.uuid_id
        FROM students s, classes c
        WHERE s.id = se.student_id
          AND c.id = se.class_id
    '''))

    # ── Step 5: Drop FK constraints ───────────────────────────────────────── #
    for constraint, table in [
        ('classes_teacher_id_fkey',                  'classes'),
        ('students_class_id_fkey',                    'students'),
        ('devices_class_id_fkey',                     'devices'),
        ('attendance_student_id_fkey',                'attendance'),
        ('attendance_class_id_fkey',                  'attendance'),
        ('attendance_device_id_fkey',                 'attendance'),
        ('student_enrollments_student_id_fkey',       'student_enrollments'),
        ('student_enrollments_class_id_fkey',         'student_enrollments'),
    ]:
        conn.execute(sa.text(
            f'ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {constraint}'
        ))

    # Also drop unique constraint on student_enrollments before column swap
    conn.execute(sa.text(
        'ALTER TABLE student_enrollments DROP CONSTRAINT IF EXISTS uq_student_class'
    ))

    # ── Step 6: Swap integer PKs/FKs for UUID ────────────────────────────── #
    # admins
    conn.execute(sa.text('ALTER TABLE admins DROP CONSTRAINT IF EXISTS admins_pkey'))
    conn.execute(sa.text('ALTER TABLE admins DROP COLUMN id'))
    conn.execute(sa.text('ALTER TABLE admins RENAME COLUMN uuid_id TO id'))
    conn.execute(sa.text('ALTER TABLE admins ADD PRIMARY KEY (id)'))
    conn.execute(sa.text('ALTER TABLE admins ALTER COLUMN id SET DEFAULT uuid_generate_v4()'))

    # classes
    conn.execute(sa.text('ALTER TABLE classes DROP CONSTRAINT IF EXISTS classes_pkey'))
    conn.execute(sa.text('ALTER TABLE classes DROP COLUMN id'))
    conn.execute(sa.text('ALTER TABLE classes DROP COLUMN teacher_id'))
    conn.execute(sa.text('ALTER TABLE classes RENAME COLUMN uuid_id TO id'))
    conn.execute(sa.text('ALTER TABLE classes RENAME COLUMN teacher_uuid TO teacher_id'))
    conn.execute(sa.text('ALTER TABLE classes ADD PRIMARY KEY (id)'))
    conn.execute(sa.text('ALTER TABLE classes ALTER COLUMN id SET DEFAULT uuid_generate_v4()'))

    # students
    conn.execute(sa.text('ALTER TABLE students DROP CONSTRAINT IF EXISTS students_pkey'))
    conn.execute(sa.text('ALTER TABLE students DROP COLUMN id'))
    conn.execute(sa.text('ALTER TABLE students DROP COLUMN class_id'))
    conn.execute(sa.text('ALTER TABLE students RENAME COLUMN uuid_id TO id'))
    conn.execute(sa.text('ALTER TABLE students RENAME COLUMN class_uuid TO class_id'))
    conn.execute(sa.text('ALTER TABLE students ADD PRIMARY KEY (id)'))
    conn.execute(sa.text('ALTER TABLE students ALTER COLUMN id SET DEFAULT uuid_generate_v4()'))

    # devices
    conn.execute(sa.text('ALTER TABLE devices DROP CONSTRAINT IF EXISTS devices_pkey'))
    conn.execute(sa.text('ALTER TABLE devices DROP COLUMN id'))
    conn.execute(sa.text('ALTER TABLE devices DROP COLUMN class_id'))
    conn.execute(sa.text('ALTER TABLE devices RENAME COLUMN uuid_id TO id'))
    conn.execute(sa.text('ALTER TABLE devices RENAME COLUMN class_uuid TO class_id'))
    conn.execute(sa.text('ALTER TABLE devices ADD PRIMARY KEY (id)'))
    conn.execute(sa.text('ALTER TABLE devices ALTER COLUMN id SET DEFAULT uuid_generate_v4()'))

    # attendance
    conn.execute(sa.text('ALTER TABLE attendance DROP CONSTRAINT IF EXISTS attendance_pkey'))
    conn.execute(sa.text('ALTER TABLE attendance DROP COLUMN id'))
    conn.execute(sa.text('ALTER TABLE attendance DROP COLUMN student_id'))
    conn.execute(sa.text('ALTER TABLE attendance DROP COLUMN class_id'))
    conn.execute(sa.text('ALTER TABLE attendance DROP COLUMN device_id'))
    conn.execute(sa.text('ALTER TABLE attendance RENAME COLUMN uuid_id TO id'))
    conn.execute(sa.text('ALTER TABLE attendance RENAME COLUMN student_uuid TO student_id'))
    conn.execute(sa.text('ALTER TABLE attendance RENAME COLUMN class_uuid TO class_id'))
    conn.execute(sa.text('ALTER TABLE attendance RENAME COLUMN device_uuid TO device_id'))
    conn.execute(sa.text('ALTER TABLE attendance ADD PRIMARY KEY (id)'))
    conn.execute(sa.text('ALTER TABLE attendance ALTER COLUMN id SET DEFAULT uuid_generate_v4()'))

    # student_enrollments
    conn.execute(sa.text('ALTER TABLE student_enrollments DROP CONSTRAINT IF EXISTS student_enrollments_pkey'))
    conn.execute(sa.text('ALTER TABLE student_enrollments DROP COLUMN id'))
    conn.execute(sa.text('ALTER TABLE student_enrollments DROP COLUMN student_id'))
    conn.execute(sa.text('ALTER TABLE student_enrollments DROP COLUMN class_id'))
    conn.execute(sa.text('ALTER TABLE student_enrollments RENAME COLUMN uuid_id TO id'))
    conn.execute(sa.text('ALTER TABLE student_enrollments RENAME COLUMN student_uuid TO student_id'))
    conn.execute(sa.text('ALTER TABLE student_enrollments RENAME COLUMN class_uuid TO class_id'))
    conn.execute(sa.text('ALTER TABLE student_enrollments ADD PRIMARY KEY (id)'))
    conn.execute(sa.text('ALTER TABLE student_enrollments ALTER COLUMN id SET DEFAULT uuid_generate_v4()'))

    # ── Step 7: Re-add UUID FK constraints ───────────────────────────────── #
    conn.execute(sa.text('''
        ALTER TABLE classes
        ADD CONSTRAINT classes_teacher_id_fkey
        FOREIGN KEY (teacher_id) REFERENCES admins(id) ON DELETE SET NULL
    '''))
    conn.execute(sa.text('''
        ALTER TABLE students
        ADD CONSTRAINT students_class_id_fkey
        FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE SET NULL
    '''))
    conn.execute(sa.text('''
        ALTER TABLE devices
        ADD CONSTRAINT devices_class_id_fkey
        FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE SET NULL
    '''))
    conn.execute(sa.text('''
        ALTER TABLE attendance
        ADD CONSTRAINT attendance_student_id_fkey
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
    '''))
    conn.execute(sa.text('''
        ALTER TABLE attendance
        ADD CONSTRAINT attendance_class_id_fkey
        FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE
    '''))
    conn.execute(sa.text('''
        ALTER TABLE attendance
        ADD CONSTRAINT attendance_device_id_fkey
        FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE SET NULL
    '''))
    conn.execute(sa.text('''
        ALTER TABLE student_enrollments
        ADD CONSTRAINT student_enrollments_student_id_fkey
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
    '''))
    conn.execute(sa.text('''
        ALTER TABLE student_enrollments
        ADD CONSTRAINT student_enrollments_class_id_fkey
        FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE
    '''))
    conn.execute(sa.text('''
        ALTER TABLE student_enrollments
        ADD CONSTRAINT uq_student_class UNIQUE (student_id, class_id)
    '''))

    # ── Step 8: Recreate indexes ──────────────────────────────────────────── #
    conn.execute(sa.text('CREATE INDEX IF NOT EXISTS ix_students_id ON students(id)'))
    conn.execute(sa.text('CREATE INDEX IF NOT EXISTS ix_classes_id ON classes(id)'))
    conn.execute(sa.text('CREATE INDEX IF NOT EXISTS ix_devices_id ON devices(id)'))
    conn.execute(sa.text('CREATE INDEX IF NOT EXISTS ix_attendance_id ON attendance(id)'))
    conn.execute(sa.text('CREATE INDEX IF NOT EXISTS ix_attendance_student_id ON attendance(student_id)'))
    conn.execute(sa.text('CREATE INDEX IF NOT EXISTS ix_attendance_class_id ON attendance(class_id)'))
    conn.execute(sa.text('CREATE INDEX IF NOT EXISTS ix_student_enrollments_student_id ON student_enrollments(student_id)'))
    conn.execute(sa.text('CREATE INDEX IF NOT EXISTS ix_student_enrollments_class_id ON student_enrollments(class_id)'))


def downgrade() -> None:
    # Downgrade is intentionally not implemented for this migration.
    # The Integer → UUID migration requires data transformation that is not
    # cleanly reversible. To downgrade, restore from a database backup.
    raise NotImplementedError(
        "Downgrade from UUID to Integer PKs is not supported. "
        "Please restore from a backup."
    )
