from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import datetime

from app.database.session import get_db
from app.models.admin import Admin
from app.models.device import Device
from app.core.security import get_current_admin, verify_device_token
from app.schemas.attendance import AttendanceCreate, AttendanceResponse, AttendanceBulkSync
from app.services.attendance_service import (
    create_attendance, bulk_sync_attendance, get_class_attendance
)

router = APIRouter()

@router.post("/", response_model=AttendanceResponse, status_code=201)
async def mark_attendance(
    data: AttendanceCreate,
    db: AsyncSession = Depends(get_db),
    device: Device = Depends(verify_device_token)
):
    """Called by Edge device after successful face recognition."""
    data.device_id = device.id
    record = await create_attendance(db, data)
    return record

@router.post("/bulk-sync", response_model=dict)
async def bulk_sync(
    data: AttendanceBulkSync,
    db: AsyncSession = Depends(get_db),
    device: Device = Depends(verify_device_token)
):
    """Sync offline attendance queue from Edge device."""
    saved = await bulk_sync_attendance(db, data.records, device_id=device.id)
    return {"synced": saved, "total": len(data.records)}

@router.get("/class/{class_id}", response_model=List[AttendanceResponse])
async def get_attendance(
    class_id: int,
    date: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
    _: Admin = Depends(get_current_admin)
):
    records = await get_class_attendance(db, class_id, date)
    return [
        AttendanceResponse(
            id=r.id,
            student_id=r.student_id,
            student_name=r.student.full_name if r.student else None,
            class_id=r.class_id,
            timestamp=r.timestamp,
            confidence=r.confidence,
            liveness_score=r.liveness_score,
            status=r.status,
            method=r.method,
        )
        for r in records
    ]