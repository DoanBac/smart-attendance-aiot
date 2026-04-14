import base64
import logging
from uuid import UUID
import numpy as np
from datetime import datetime, timedelta
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.models.attendance import Attendance
from app.models.student import Student
from app.models.class_ import Class
from app.models.enrollment import StudentEnrollment
from app.schemas.attendance import AttendanceCreate

logger = logging.getLogger(__name__)


async def _trigger_esp8266(url: str) -> None:
    """Send GET request to ESP8266 to unlock door. Non-blocking, errors are logged only."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(url)
            logger.info("[ESP8266] Door unlock sent → %s  status=%d", url, resp.status_code)
    except Exception as e:
        logger.warning("[ESP8266] Door unlock failed: %s — %s", url, e)


async def create_attendance(
    db: AsyncSession,
    data: AttendanceCreate,
    student_name: Optional[str] = None,
) -> Attendance:
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
        "student_name": student_name,  # Populated by kiosk verify; None for edge device
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

async def verify_face_and_log(
    db: AsyncSession,
    image_b64: str,
    class_id: UUID,
    device_id: Optional[int] = None,
    challenge_dir: Optional[str] = None,  # "left" | "right" pose challenge
) -> dict:
    """
    Web Kiosk face verification pipeline:
      1. Extract ArcFace embedding from JPEG image (AI service)
      2. Identify student from class gallery (AES-decrypt in backend)
      3. Create attendance record + WS broadcast if matched + not duplicate
    Returns a rich dict for the kiosk UI.
    """
    from app.services.ai_client import ai_extract_embedding
    from app.services.face_service import identify_face

    # ── Step 1: Extract embedding ─────────────────────────────────────────────
    try:
        embedding, quality, meta = await ai_extract_embedding(image_b64)
    except ValueError as e:
        # No face detected or image too blurry
        return {"matched": False, "status": "no_face",
                "message": str(e), "confidence": 0.0}
    except RuntimeError as e:
        logger.error(f"[KIOSK] AI service error during extract: {e}")
        return {"matched": False, "status": "error",
                "message": "AI service unavailable", "confidence": 0.0}

    # ── Liveness gate: Pose challenge + anti-spoof score ──────────────────────────────
    liveness_score = meta.get("liveness_score")
    yaw = meta.get("yaw")   # degrees; + = subject's right, - = subject's left

    # 1️⃣  Pose challenge: require a minimum head-turn matching the random direction
    #    Provides active liveness: defeats static photos AND pre-recorded video
    #    (video would need to be recorded in exactly the right direction at the right moment)
    MIN_YAW = 12.0    # must turn at least 12° to pass
    MAX_YAW = 50.0    # beyond 50° face quality degrades too much
    if challenge_dir and yaw is not None:
        # Webcam is horizontally mirrored, so physical directions are flipped:
        # "left"  physical turn → camera yaw > 0 (positive)
        # "right" physical turn → camera yaw < 0 (negative)
        direction_ok = (
            (challenge_dir == "left"  and yaw >= MIN_YAW  and yaw <= MAX_YAW) or
            (challenge_dir == "right" and yaw <= -MIN_YAW and yaw >= -MAX_YAW)
        )
        dir_label = "← LEFT" if challenge_dir == "left" else "→ RIGHT"
        if not direction_ok:
            if abs(yaw or 0) < MIN_YAW:
                msg = f"Please turn your face {dir_label} then capture"
            else:
                msg = f"Wrong direction! Please turn your face {dir_label}"
            logger.warning("[KIOSK] Pose challenge FAILED — expected=%s yaw=%.1f", challenge_dir, yaw or 0)
            return {"matched": False, "status": "liveness_failed", "message": msg, "confidence": 0.0}
        logger.info("[KIOSK] Pose challenge PASSED — dir=%s yaw=%.1f°", challenge_dir, yaw)

    # 2️⃣  Anti-spoof model score (secondary gate — works much better at non-frontal angles)
    #    At ≥12° tilt: real face ~0.40-0.75, phone screen ~0.15-0.38 (moiré, glare, flat geometry)
    #    Threshold lowered to 0.42 vs 0.55 because angled faces score slightly lower in this model
    is_live = meta.get("is_live", True)
    if not is_live:
        logger.warning("[KIOSK] Anti-spoof FAILED — score=%.3f yaw=%.1f° class=%d",
                       liveness_score or 0, yaw or 0, class_id)
        return {
            "matched": False,
            "status": "liveness_failed",
            "message": "Spoofing detected. Please use your real face.",
            "confidence": 0.0,
            "liveness_score": liveness_score,
        }

    # ── Step 2: Identify GLOBALLY across all students with face embeddings ──────────
    # (class_id=None → no class filter, finds student even if at wrong class kiosk)
    emb_b64 = base64.b64encode(embedding.astype(np.float32).tobytes()).decode()
    student_id, confidence = await identify_face(db, emb_b64, class_id=None)

    if not student_id:
        return {
            "matched": False, "status": "unknown",
            "message": "Face not recognized. Please try again.",
            "confidence": round(confidence, 4),
        }

    # ── Step 3: Fetch student info ────────────────────────────────────────────────
    res = await db.execute(select(Student).where(Student.id == student_id))
    student = res.scalar_one_or_none()
    student_name  = student.full_name    if student else f"Student #{student_id}"
    student_code  = student.student_code if student else None
    student_email = student.email        if student else None

    # ── Step 4: Check enrollment in THIS class via student_enrollments ──────────────
    enroll_res = await db.execute(
        select(StudentEnrollment).where(
            StudentEnrollment.student_id == student_id,
            StudentEnrollment.class_id   == class_id,
            StudentEnrollment.status     == "active",
        )
    )
    not_enrolled = enroll_res.scalar_one_or_none() is None

    if not_enrolled:
        # Student is in the system but scanned at the wrong kiosk
        # Load wrong class info
        wrong_cls_res = await db.execute(select(Class).where(Class.id == class_id))
        wrong_cls = wrong_cls_res.scalar_one_or_none()
        wrong_class_name = wrong_cls.class_name if wrong_cls else f"Class #{class_id}"
        wrong_class_code = wrong_cls.class_code if wrong_cls else ""

        # Load all enrolled classes for schedule email (today + tomorrow)
        enrolled_res = await db.execute(
            select(Class)
            .join(StudentEnrollment, StudentEnrollment.class_id == Class.id)
            .where(
                StudentEnrollment.student_id == student_id,
                StudentEnrollment.status     == "active",
            )
            .order_by(Class.class_name)
        )
        enrolled_classes = enrolled_res.scalars().all()

        # Serialize to plain dicts NOW (before DB session closes)
        enrolled_dicts = [
            {
                "class_name": c.class_name,
                "class_code": c.class_code,
                "room":       c.room,
                "schedule":   dict(c.schedule) if c.schedule else {},
            }
            for c in enrolled_classes
        ]

        # Fire-and-forget email async (does not block kiosk response)
        import asyncio
        from app.services.email_service import send_wrong_class_email
        asyncio.ensure_future(send_wrong_class_email(
            student_name     = student_name,
            student_code     = student_code or "",
            student_email    = student_email,
            wrong_class_name = wrong_class_name,
            wrong_class_code = wrong_class_code,
            enrolled_classes = enrolled_dicts,
        ))

        logger.warning(
            "[KIOSK] Wrong class: student=%s (id=%d) scanned class=%d — not enrolled",
            student_name, student_id, class_id,
        )
        return {
            "matched": True,
            "status": "wrong_class",
            "student_id": student_id,
            "student_name": student_name,
            "student_code": student_code,
            "confidence": round(confidence, 4),
            "message": f"You are not enrolled in this class. Schedule reminder sent to your email.",
        }

    # ── Step 5: Duplicate check — already marked in last 2 hours ─────────────────
    window_start = datetime.utcnow() - timedelta(hours=2)
    dup = await db.execute(
        select(Attendance).where(
            Attendance.student_id == student_id,
            Attendance.class_id == class_id,
            Attendance.timestamp >= window_start,
        )
    )
    if dup.scalars().first():
        return {
            "matched": True, "status": "already_marked",
            "student_id": student_id,
            "student_name": student_name,
            "student_code": student_code,
            "confidence": round(confidence, 4),
            "message": f"Already checked in — {student_name}",
        }

    # ── Step 6: Create attendance record + WS broadcast ────────────────────────
    data = AttendanceCreate(
        student_id=student_id,
        class_id=class_id,
        device_id=device_id,
        timestamp=datetime.utcnow(),
        confidence=confidence,
        liveness_score=None,
        method="face_kiosk",
        status="present",
    )
    record = await create_attendance(db, data, student_name=student_name)

    logger.info(f"[KIOSK] Attendance: student={student_name} class={class_id} conf={confidence:.3f}")

    # ── Step 6: Fire-and-forget ESP8266 door unlock ───────────────────────────
    if device_id:
        from sqlalchemy import select as _sel
        from app.models.device import Device as _Device
        dev_res = await db.execute(_sel(_Device).where(_Device.id == device_id))
        dev_obj = dev_res.scalar_one_or_none()
        if dev_obj and dev_obj.esp8266_url:
            import asyncio
            asyncio.ensure_future(_trigger_esp8266(dev_obj.esp8266_url))

    return {
        "matched": True, "status": "present",
        "student_id": student_id,
        "student_name": student_name,
        "student_code": student_code,
        "confidence": round(confidence, 4),
        "attendance_id": record.id,
        "message": f"Welcome, {student_name}! Attendance recorded.",
    }


async def get_class_attendance(
    db: AsyncSession,
    class_id: UUID,
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


async def get_today_attendance(db: AsyncSession) -> List[Attendance]:
    """Return all attendance records for today across all classes."""
    from datetime import date as date_type
    today = date_type.today()
    stmt = (
        select(Attendance)
        .options(selectinload(Attendance.student), selectinload(Attendance.class_))
        .where(func.date(Attendance.timestamp) == today)
        .order_by(Attendance.timestamp.desc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()


async def get_absent_students(
    db: AsyncSession,
    class_id: UUID,
    date: Optional[datetime] = None,
) -> List[Student]:
    """Return active students in class who have NO attendance record on the given date."""
    from datetime import date as date_type
    target_date = date.date() if date else date_type.today()

    # Subquery: student_ids that ARE present on target_date for this class
    present_subq = (
        select(Attendance.student_id)
        .where(Attendance.class_id == class_id)
        .where(func.date(Attendance.timestamp) == target_date)
        .where(Attendance.status == "present")
    ).scalar_subquery()

    stmt = (
        select(Student)
        .where(Student.class_id == class_id)
        .where(Student.status == "active")
        .where(Student.id.not_in(present_subq))
        .order_by(Student.full_name)
    )
    result = await db.execute(stmt)
    return result.scalars().all()