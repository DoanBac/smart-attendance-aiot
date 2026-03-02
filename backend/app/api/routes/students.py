from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from typing import List

from app.database.session import get_db
from app.models.student import Student
from app.models.admin import Admin
from app.core.security import get_current_admin
from app.schemas.student import StudentCreate, StudentUpdate, StudentResponse
from app.services.student_service import get_all_students, delete_student_data

router = APIRouter()

@router.get("/", response_model=List[StudentResponse])
async def list_students(
    class_id: int = None,
    db: AsyncSession = Depends(get_db),
    _: Admin = Depends(get_current_admin)
):
    stmt = select(Student)
    if class_id:
        stmt = stmt.where(Student.class_id == class_id)
    result = await db.execute(stmt.order_by(Student.full_name))
    students = result.scalars().all()
    return [
        StudentResponse(
            **{c.name: getattr(s, c.name) for c in Student.__table__.columns},
            has_face=s.face_embedding is not None
        ) for s in students
    ]

@router.post("/", response_model=StudentResponse, status_code=201)
async def create_student(
    data: StudentCreate,
    db: AsyncSession = Depends(get_db),
    _: Admin = Depends(get_current_admin)
):
    existing = await db.execute(select(Student).where(Student.student_code == data.student_code))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Student code already exists")
    student = Student(**data.model_dump())
    db.add(student)
    await db.flush()
    await db.refresh(student)
    return StudentResponse(
        **{c.name: getattr(student, c.name) for c in Student.__table__.columns},
        has_face=False
    )

@router.get("/{student_id}", response_model=StudentResponse)
async def get_student(
    student_id: int,
    db: AsyncSession = Depends(get_db),
    _: Admin = Depends(get_current_admin)
):
    result = await db.execute(select(Student).where(Student.id == student_id))
    student = result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    return StudentResponse(
        **{c.name: getattr(student, c.name) for c in Student.__table__.columns},
        has_face=student.face_embedding is not None
    )

@router.put("/{student_id}", response_model=StudentResponse)
async def update_student(
    student_id: int,
    data: StudentUpdate,
    db: AsyncSession = Depends(get_db),
    _: Admin = Depends(get_current_admin)
):
    result = await db.execute(select(Student).where(Student.id == student_id))
    student = result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    update_data = data.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No data to update")

    # Dùng UPDATE statement trực tiếp thay vì setattr → tránh MissingGreenlet
    await db.execute(
        update(Student)
        .where(Student.id == student_id)
        .values(**update_data)
    )
    await db.flush()

    # Re-query để lấy data mới nhất
    result = await db.execute(select(Student).where(Student.id == student_id))
    student = result.scalar_one()

    return StudentResponse(
        **{c.name: getattr(student, c.name) for c in Student.__table__.columns},
        has_face=student.face_embedding is not None
    )

@router.delete("/{student_id}", status_code=204)
async def delete_student(
    student_id: int,
    db: AsyncSession = Depends(get_db),
    current: Admin = Depends(get_current_admin)
):
    """GDPR Right to Erasure — deletes all biometric data."""
    if current.role not in ("superadmin", "admin"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    await delete_student_data(db, student_id)