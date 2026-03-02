from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from typing import List, Optional

from app.database.session import get_db
from app.models.student import Student
from app.models.admin import Admin
from app.core.security import get_current_admin
from app.schemas.student import StudentCreate, StudentUpdate, StudentResponse
from app.services.student_service import (
    get_all_students, generate_student_code,
    soft_delete_student, delete_student_data,
)

router = APIRouter()


def _to_response(s: Student) -> StudentResponse:
    return StudentResponse(
        **{c.name: getattr(s, c.name) for c in Student.__table__.columns},
        has_face=s.face_embedding is not None,
    )


@router.get("/", response_model=List[StudentResponse])
async def list_students(
    class_id: Optional[int] = None,
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
    _: Admin = Depends(get_current_admin),
):
    stmt = select(Student)
    if class_id:
        stmt = stmt.where(Student.class_id == class_id)
    if not include_inactive:
        stmt = stmt.where(Student.status == "active")
    result = await db.execute(stmt.order_by(Student.student_code))
    return [_to_response(s) for s in result.scalars().all()]


@router.post("/", response_model=StudentResponse, status_code=201)
async def create_student(
    data: StudentCreate,
    db: AsyncSession = Depends(get_db),
    _: Admin = Depends(get_current_admin),
):
    # Auto-generate student_code if not provided
    code = data.student_code or await generate_student_code(db)

    existing = await db.execute(select(Student).where(Student.student_code == code))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Student code '{code}' already exists")

    payload = data.model_dump()
    payload["student_code"] = code
    student = Student(**payload)
    db.add(student)
    await db.flush()
    await db.refresh(student)
    return _to_response(student)

@router.get("/{student_id}", response_model=StudentResponse)
async def get_student(
    student_id: int,
    db: AsyncSession = Depends(get_db),
    _: Admin = Depends(get_current_admin),
):
    result = await db.execute(select(Student).where(Student.id == student_id))
    student = result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    return _to_response(student)


@router.put("/{student_id}", response_model=StudentResponse)
async def update_student(
    student_id: int,
    data: StudentUpdate,
    db: AsyncSession = Depends(get_db),
    _: Admin = Depends(get_current_admin),
):
    result = await db.execute(select(Student).where(Student.id == student_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Student not found")

    update_data = data.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No data to update")

    await db.execute(update(Student).where(Student.id == student_id).values(**update_data))
    await db.flush()

    result = await db.execute(select(Student).where(Student.id == student_id))
    return _to_response(result.scalar_one())


@router.patch("/{student_id}/deactivate", response_model=StudentResponse)
async def deactivate_student(
    student_id: int,
    db: AsyncSession = Depends(get_db),
    _: Admin = Depends(get_current_admin),
):
    """
    Soft-delete: set status=inactive, erase face embedding (GDPR).
    Attendance history is preserved for audit/reports.
    """
    await soft_delete_student(db, student_id)
    await db.commit()
    result = await db.execute(select(Student).where(Student.id == student_id))
    return _to_response(result.scalar_one())


@router.patch("/{student_id}/activate", response_model=StudentResponse)
async def activate_student(
    student_id: int,
    db: AsyncSession = Depends(get_db),
    _: Admin = Depends(get_current_admin),
):
    """Re-activate a previously deactivated student."""
    result = await db.execute(select(Student).where(Student.id == student_id))
    student = result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    await db.execute(update(Student).where(Student.id == student_id).values(status="active"))
    await db.flush()
    await db.commit()
    result = await db.execute(select(Student).where(Student.id == student_id))
    return _to_response(result.scalar_one())


@router.delete("/{student_id}", status_code=204)
async def delete_student(
    student_id: int,
    db: AsyncSession = Depends(get_db),
    current: Admin = Depends(get_current_admin),
):
    """Hard-delete (superadmin only). Permanently removes student + all attendance records."""
    if current.role not in ("superadmin", "admin"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    await delete_student_data(db, student_id)
    await db.commit()