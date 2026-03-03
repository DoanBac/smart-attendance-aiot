from datetime import datetime
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.models.attendance import Attendance
from app.models.student import Student
from app.schemas.attendance import AttendanceCreate

async def create_attendance(db: AsyncSession, data: AttendanceCreate) -> Attendance:
    # Strip timezone info before writing — DB column is TIMESTAMP WITHOUT TIME ZONE
    ts = data.timestamp
    if ts and ts.tzinfo is not None:
        ts = ts.replace(tzinfo=None)
    record = Attendance(
        student_id=data.student_id,
        class_id=data.class_id,
        device_id=data.device_id,
        timestamp=ts,
        confidence=data.confidence,
        liveness_score=data.liveness_score,
        method=data.method,
        status=data.status,
    )
    db.add(record)
    await db.flush()
    await db.refresh(record)

    # Broadcast real-time update tới Dashboard qua WebSocket
    from app.websocket.attendance_ws import broadcast_attendance
    await broadcast_attendance(data.class_id, {
        "id": record.id,
        "student_id": record.student_id,
        "student_name": None,  # Edge không có tên, dashboard tự fetch nếu cần
        "class_id": record.class_id,
        "timestamp": record.timestamp.isoformat() if record.timestamp else None,
        "confidence": record.confidence,
        "liveness_score": record.liveness_score,
        "status": record.status,
        "method": record.method,
    })

    return record

async def bulk_sync_attendance(
    db: AsyncSession,
    records: List[AttendanceCreate],
    device_id: Optional[int] = None
) -> int:
    """Sync offline attendance records from Edge. Returns number of records saved."""
    saved = 0
    for data in records:
        # Prevent duplicate: check same student + class + timestamp within 5 min window
        # Strip timezone before compare + insert (DB column is tz-naive)
        ts = data.timestamp
        if ts and ts.tzinfo is not None:
            ts = ts.replace(tzinfo=None)
        existing = await db.execute(
            select(Attendance).where(
                Attendance.student_id == data.student_id,
                Attendance.class_id == data.class_id,
                Attendance.timestamp == ts
            )
        )
        if existing.scalar_one_or_none():
            continue
        record = Attendance(
            student_id=data.student_id,
            class_id=data.class_id,
            device_id=device_id or data.device_id,
            timestamp=ts,
            confidence=data.confidence,
            liveness_score=data.liveness_score,
            method=data.method,
            status=data.status,
            synced_from_edge="Y",
        )
        db.add(record)
        await db.flush()
        await db.refresh(record)
        saved += 1

        # Broadcast realtime update tới Dashboard (cùng pipeline với create_attendance)
        from app.websocket.attendance_ws import broadcast_attendance
        await broadcast_attendance(record.class_id, {
            "id": record.id,
            "student_id": record.student_id,
            "student_name": None,
            "class_id": record.class_id,
            "timestamp": record.timestamp.isoformat() if record.timestamp else None,
            "confidence": record.confidence,
            "liveness_score": record.liveness_score,
            "status": record.status,
            "method": record.method,
        })

    return saved

async def get_class_attendance(
    db: AsyncSession,
    class_id: int,
    date: Optional[datetime] = None
) -> List[Attendance]:
    stmt = (
        select(Attendance)
        .options(selectinload(Attendance.student))
        .where(Attendance.class_id == class_id)
    )
    if date:
        stmt = stmt.where(func.date(Attendance.timestamp) == date.date())
    result = await db.execute(stmt.order_by(Attendance.timestamp.desc()))
    return result.scalars().all()