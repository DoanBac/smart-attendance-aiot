from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func, or_
from typing import List, Optional
import uuid

from app.database.session import get_db
from app.models.class_ import Class
from app.models.enrollment import StudentEnrollment
from app.models.admin import Admin
from app.core.security import get_current_admin, verify_device_token
from app.models.device import Device
from app.schemas.class_ import ClassCreate, ClassUpdate, ClassResponse
from uuid import UUID

router = APIRouter()


async def _student_count(db: AsyncSession, class_id: UUID) -> int:
    return (await db.execute(
        select(func.count()).select_from(StudentEnrollment).where(
            StudentEnrollment.class_id == class_id,
            StudentEnrollment.status == "active",
        )
    )).scalar_one()


async def _to_response(db: AsyncSession, cls: Class) -> ClassResponse:
    count = await _student_count(db, cls.id)
    data = {c.name: getattr(cls, c.name) for c in Class.__table__.columns}
    return ClassResponse(**data, student_count=count)


@router.get("/by-code/{class_code}")
async def get_class_by_code(
    class_code: str,
    db: AsyncSession = Depends(get_db),
    _device: Device = Depends(verify_device_token),
):
    """Lightweight lookup used by the kiosk (authenticated with X-Device-Token)."""
    result = await db.execute(select(Class).where(Class.class_code == class_code))
    cls = result.scalar_one_or_none()
    if not cls:
        raise HTTPException(status_code=404, detail="Class not found")
    return {"id": cls.id, "class_code": cls.class_code, "class_name": cls.class_name}


@router.get("/", response_model=List[ClassResponse])
async def list_classes(
    search: Optional[str] = Query(None, description="Search by code, name or subject"),
    semester: Optional[str] = Query(None),
    academic_year: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="active | inactive"),
    db: AsyncSession = Depends(get_db),
    _: Admin = Depends(get_current_admin),
):
    stmt = select(Class)

    if search:
        like = f"%{search}%"
        stmt = stmt.where(
            or_(
                Class.class_code.ilike(like),
                Class.class_name.ilike(like),
                Class.subject.ilike(like),
            )
        )
    if semester:
        stmt = stmt.where(Class.semester == semester)
    if academic_year:
        stmt = stmt.where(Class.academic_year == academic_year)
    if status:
        stmt = stmt.where(Class.status == status)
    else:
        stmt = stmt.where(Class.status == "active")

    result = await db.execute(stmt.order_by(Class.class_code))
    classes = result.scalars().all()
    return [await _to_response(db, c) for c in classes]


@router.post("/", response_model=ClassResponse, status_code=201)
async def create_class(
    data: ClassCreate,
    db: AsyncSession = Depends(get_db),
    _: Admin = Depends(get_current_admin),
):
    # Auto-generate a short UUID code if not provided
    code = (data.class_code or "").strip() or uuid.uuid4().hex[:8].upper()

    existing = await db.execute(select(Class).where(Class.class_code == code))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Class code already exists")

    payload = data.model_dump()
    payload["class_code"] = code
    if payload.get("schedule") and hasattr(payload["schedule"], "model_dump"):
        payload["schedule"] = payload["schedule"].model_dump()

    cls = Class(**payload)
    db.add(cls)
    await db.flush()
    await db.refresh(cls)
    return await _to_response(db, cls)


@router.get("/{class_id}", response_model=ClassResponse)
async def get_class(
    class_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: Admin = Depends(get_current_admin),
):
    result = await db.execute(select(Class).where(Class.id == class_id))
    cls = result.scalar_one_or_none()
    if not cls:
        raise HTTPException(status_code=404, detail="Class not found")
    return await _to_response(db, cls)


@router.put("/{class_id}", response_model=ClassResponse)
async def update_class(
    class_id: UUID,
    data: ClassUpdate,
    db: AsyncSession = Depends(get_db),
    _: Admin = Depends(get_current_admin),
):
    result = await db.execute(select(Class).where(Class.id == class_id))
    cls = result.scalar_one_or_none()
    if not cls:
        raise HTTPException(status_code=404, detail="Class not found")

    update_data = data.model_dump(exclude_none=True)
    if "schedule" in update_data and update_data["schedule"] is not None:
        sched = update_data["schedule"]
        update_data["schedule"] = sched.model_dump() if hasattr(sched, "model_dump") else sched

    for key, value in update_data.items():
        setattr(cls, key, value)

    await db.flush()
    await db.refresh(cls)
    return await _to_response(db, cls)


@router.delete("/{class_id}", status_code=204)
async def delete_class(
    class_id: UUID,
    db: AsyncSession = Depends(get_db),
    current: Admin = Depends(get_current_admin),
):
    result = await db.execute(select(Class).where(Class.id == class_id))
    cls = result.scalar_one_or_none()
    if not cls:
        raise HTTPException(status_code=404, detail="Class not found")
    cls.status = "inactive"
    await db.flush()