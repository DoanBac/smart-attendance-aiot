from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func
from typing import List, Optional
from uuid import UUID

from app.models.student import Student
from app.models.attendance import Attendance

# ---------------------------------------------------------------------------
# Student code format: FSB001, FSB002, ... FSB999, FSB1000 (grows naturally)
# Prefix can be overridden via PREFIX constant if school changes branding.
# ---------------------------------------------------------------------------
STUDENT_CODE_PREFIX = "FSB"


async def generate_student_code(db: AsyncSession) -> str:
    """
    Auto-generate next student_code in format FSBxxx.
    Queries MAX numeric suffix of existing codes and increments by 1.
    Thread-safe under async single-process; for multi-process use a DB sequence.
    """
    result = await db.execute(
        select(Student.student_code).where(
            Student.student_code.like(f"{STUDENT_CODE_PREFIX}%")
        )
    )
    codes = result.scalars().all()

    max_num = 0
    for code in codes:
        suffix = code[len(STUDENT_CODE_PREFIX):]
        if suffix.isdigit():
            max_num = max(max_num, int(suffix))

    next_num = max_num + 1
    # Zero-pad to 6 digits minimum: FSB000001 … FSB999999, then grows naturally
    width = max(6, len(str(next_num)))
    return f"{STUDENT_CODE_PREFIX}{str(next_num).zfill(width)}"


async def get_all_students(db: AsyncSession, class_id: UUID = None) -> List[Student]:
    stmt = select(Student)
    if class_id:
        stmt = stmt.where(Student.class_id == class_id)
    result = await db.execute(stmt)
    return result.scalars().all()


async def soft_delete_student(db: AsyncSession, student_id: UUID):
    """
    Soft-delete: set status='inactive', erase face biometric (GDPR compliance).
    Attendance history is KEPT for reporting/audit purposes.
    The student record itself is kept so historical attendance still resolves a name.
    """
    result = await db.execute(select(Student).where(Student.id == student_id))
    student = result.scalar_one_or_none()
    if not student:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Student not found")

    student.face_embedding = None   # Erase biometric data
    student.status = "inactive"
    await db.flush()


async def delete_student_data(db: AsyncSession, student_id: UUID):
    """
    Hard-delete (GDPR Right to Erasure): removes all records permanently.
    Use with caution — attendance history will also be removed.
    """
    result = await db.execute(select(Student).where(Student.id == student_id))
    student = result.scalar_one_or_none()
    if not student:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Student not found")

    # Delete attendance records first (foreign key)
    await db.execute(delete(Attendance).where(Attendance.student_id == student_id))
    await db.delete(student)
    await db.flush()