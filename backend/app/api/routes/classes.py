from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from pydantic import BaseModel
from typing import Optional

from app.database.session import get_db
from app.models.class_ import Class
from app.models.admin import Admin
from app.core.security import get_current_admin

router = APIRouter()

class ClassCreate(BaseModel):
    class_code: str
    class_name: str
    subject: Optional[str] = None
    schedule: Optional[dict] = None
    room: Optional[str] = None
    teacher_id: Optional[int] = None
    semester: Optional[str] = None

class ClassResponse(BaseModel):
    id: int
    class_code: str
    class_name: str
    subject: Optional[str]
    room: Optional[str]
    semester: Optional[str]
    status: str

    class Config:
        from_attributes = True

@router.get("/", response_model=List[ClassResponse])
async def list_classes(
    db: AsyncSession = Depends(get_db),
    _: Admin = Depends(get_current_admin)
):
    result = await db.execute(select(Class).where(Class.status == "active"))
    return result.scalars().all()

@router.post("/", response_model=ClassResponse, status_code=201)
async def create_class(
    data: ClassCreate,
    db: AsyncSession = Depends(get_db),
    _: Admin = Depends(get_current_admin)
):
    existing = await db.execute(select(Class).where(Class.class_code == data.class_code))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Class code already exists")
    cls = Class(**data.model_dump())
    db.add(cls)
    await db.flush()
    await db.refresh(cls)
    return cls