from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from typing import List

from app.models.student import Student
from app.models.attendance import Attendance

async def get_all_students(db: AsyncSession, class_id: int = None) -> List[Student]:
    stmt = select(Student)
    if class_id:
        stmt = stmt.where(Student.class_id == class_id)
    result = await db.execute(stmt)
    return result.scalars().all()

async def delete_student_data(db: AsyncSession, student_id: int):
    """GDPR: erase biometric data and all attendance records."""
    # First clear the embedding
    result = await db.execute(select(Student).where(Student.id == student_id))
    student = result.scalar_one_or_none()
    if not student:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Student not found")
    
    student.face_embedding = None  # Erase biometric
    student.status = "inactive"
    # Delete attendance history
    await db.execute(delete(Attendance).where(Attendance.student_id == student_id))
    await db.flush()