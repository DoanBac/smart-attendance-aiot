from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func, and_, or_
from sqlalchemy.exc import IntegrityError
from typing import List, Optional

from app.database.session import get_db
from app.models.student import Student
from app.models.class_ import Class
from app.models.enrollment import StudentEnrollment
from app.models.admin import Admin
from app.core.security import get_current_admin
from app.schemas.student import (
    StudentCreate, StudentUpdate, StudentResponse, EnrollRequest, ClassBrief,
)
from app.services.student_service import (
    generate_student_code, soft_delete_student, delete_student_data,
)
from uuid import UUID

router = APIRouter()


async def _get_enrolled_classes(db: AsyncSession, student_id: UUID) -> List[ClassBrief]:
    stmt = (
        select(Class)
        .join(StudentEnrollment, StudentEnrollment.class_id == Class.id)
        .where(
            StudentEnrollment.student_id == student_id,
            StudentEnrollment.status == "active",
        )
        .order_by(Class.class_code)
    )
    result = await db.execute(stmt)
    return [ClassBrief.model_validate(c) for c in result.scalars().all()]


async def _to_response(db: AsyncSession, s: Student) -> StudentResponse:
    enrolled = await _get_enrolled_classes(db, s.id)
    return StudentResponse(
        **{c.name: getattr(s, c.name) for c in Student.__table__.columns},
        has_face=s.face_embedding is not None,
        enrolled_classes=enrolled,
    )


@router.get("/", response_model=List[StudentResponse])
async def list_students(
    search: Optional[str] = Query(None, description="Search by name, code or email"),
    class_id: Optional[int] = Query(None, description="Filter by enrolled class"),
    status: Optional[str] = Query(None, description="active | inactive"),
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
    _: Admin = Depends(get_current_admin),
):
    stmt = select(Student)

    if search:
        like = f"%{search}%"
        stmt = stmt.where(
            or_(
                Student.full_name.ilike(like),
                Student.student_code.ilike(like),
                Student.email.ilike(like),
            )
        )

    if class_id:
        stmt = stmt.join(
            StudentEnrollment,
            and_(
                StudentEnrollment.student_id == Student.id,
                StudentEnrollment.class_id == class_id,
                StudentEnrollment.status == "active",
            )
        )

    if status:
        stmt = stmt.where(Student.status == status)
    elif not include_inactive:
        stmt = stmt.where(Student.status == "active")

    result = await db.execute(stmt.order_by(Student.student_code))
    students = result.scalars().all()
    return [await _to_response(db, s) for s in students]


@router.post("/", response_model=StudentResponse, status_code=201)
async def create_student(
    data: StudentCreate,
    db: AsyncSession = Depends(get_db),
    _: Admin = Depends(get_current_admin),
):
    code = await generate_student_code(db)
    existing = await db.execute(select(Student).where(Student.student_code == code))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Student code '{code}' already exists")

    # Pre-check for duplicate email before hitting the DB constraint
    if data.email:
        dup = await db.execute(select(Student).where(Student.email == data.email))
        if dup.scalar_one_or_none():
            raise HTTPException(status_code=409, detail=f"A student with email '{data.email}' already exists")

    student = Student(
        student_code=code,
        full_name=data.full_name,
        email=data.email,
        phone=data.phone,
    )
    db.add(student)
    try:
        await db.flush()
    except IntegrityError as e:
        await db.rollback()
        detail = str(e.orig) if hasattr(e, "orig") else str(e)
        if "students_email_key" in detail or "email" in detail.lower():
            raise HTTPException(status_code=409, detail=f"A student with email '{data.email}' already exists")
        if "students_student_code_key" in detail or "student_code" in detail.lower():
            raise HTTPException(status_code=409, detail=f"Student code conflict — please retry")
        raise HTTPException(status_code=409, detail="Duplicate entry — please check the data and retry")

    for cid in (data.class_ids or []):
        cls = await db.get(Class, cid)
        if cls:
            db.add(StudentEnrollment(student_id=student.id, class_id=cid))
            if student.class_id is None:
                student.class_id = cid

    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Class enrollment conflict — student may already be enrolled")

    await db.refresh(student)
    return await _to_response(db, student)


@router.get("/{student_id}", response_model=StudentResponse)
async def get_student(
    student_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: Admin = Depends(get_current_admin),
):
    result = await db.execute(select(Student).where(Student.id == student_id))
    student = result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    return await _to_response(db, student)


@router.put("/{student_id}", response_model=StudentResponse)
async def update_student(
    student_id: UUID,
    data: StudentUpdate,
    db: AsyncSession = Depends(get_db),
    _: Admin = Depends(get_current_admin),
):
    result = await db.execute(select(Student).where(Student.id == student_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Student not found")

    update_data = data.model_dump(exclude_none=True)
    if update_data:
        await db.execute(update(Student).where(Student.id == student_id).values(**update_data))
        await db.flush()

    result = await db.execute(select(Student).where(Student.id == student_id))
    return await _to_response(db, result.scalar_one())


# ── Enrollment endpoints ────────────────────────────────────────────────────

@router.post("/{student_id}/enroll", response_model=StudentResponse, status_code=201)
async def enroll_student(
    student_id: UUID,
    data: EnrollRequest,
    db: AsyncSession = Depends(get_db),
    _: Admin = Depends(get_current_admin),
):
    """Enroll a student in an additional class."""
    student = (await db.execute(select(Student).where(Student.id == student_id))).scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    cls = await db.get(Class, data.class_id)
    if not cls:
        raise HTTPException(status_code=404, detail="Class not found")

    if cls.capacity:
        count = (await db.execute(
            select(func.count()).select_from(StudentEnrollment).where(
                StudentEnrollment.class_id == data.class_id,
                StudentEnrollment.status == "active",
            )
        )).scalar_one()
        if count >= cls.capacity:
            raise HTTPException(status_code=409, detail=f"Class is full ({cls.capacity} students)")

    existing_enroll = (await db.execute(
        select(StudentEnrollment).where(
            StudentEnrollment.student_id == student_id,
            StudentEnrollment.class_id == data.class_id,
        )
    )).scalar_one_or_none()

    if existing_enroll:
        if existing_enroll.status == "dropped":
            existing_enroll.status = "active"
    else:
        db.add(StudentEnrollment(student_id=student_id, class_id=data.class_id))

    if student.class_id is None:
        await db.execute(update(Student).where(Student.id == student_id).values(class_id=data.class_id))

    await db.flush()
    result = await db.execute(select(Student).where(Student.id == student_id))
    return await _to_response(db, result.scalar_one())


@router.delete("/{student_id}/classes/{class_id}", response_model=StudentResponse)
async def unenroll_student(
    student_id: UUID,
    class_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: Admin = Depends(get_current_admin),
):
    """Remove a student from a specific class."""
    enrollment = (await db.execute(
        select(StudentEnrollment).where(
            StudentEnrollment.student_id == student_id,
            StudentEnrollment.class_id == class_id,
        )
    )).scalar_one_or_none()

    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")

    enrollment.status = "dropped"
    await db.flush()

    result = await db.execute(select(Student).where(Student.id == student_id))
    return await _to_response(db, result.scalar_one())


# ── Status management ───────────────────────────────────────────────────────

@router.patch("/{student_id}/deactivate", response_model=StudentResponse)
async def deactivate_student(
    student_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: Admin = Depends(get_current_admin),
):
    await soft_delete_student(db, student_id)
    await db.commit()
    result = await db.execute(select(Student).where(Student.id == student_id))
    return await _to_response(db, result.scalar_one())


@router.patch("/{student_id}/activate", response_model=StudentResponse)
async def activate_student(
    student_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: Admin = Depends(get_current_admin),
):
    result = await db.execute(select(Student).where(Student.id == student_id))
    student = result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    await db.execute(update(Student).where(Student.id == student_id).values(status="active"))
    await db.flush()
    await db.commit()
    result = await db.execute(select(Student).where(Student.id == student_id))
    return await _to_response(db, result.scalar_one())


@router.delete("/{student_id}", status_code=204)
async def delete_student(
    student_id: UUID,
    db: AsyncSession = Depends(get_db),
    current: Admin = Depends(get_current_admin),
):
    """Hard-delete (admin only). Permanently removes student + all attendance records."""
    if current.role not in ("superadmin", "admin"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    await delete_student_data(db, student_id)
    await db.commit()