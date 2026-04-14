import io
import asyncio
import httpx
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from uuid import UUID
from datetime import datetime


async def _notify_esp(esp_url: str, path: str) -> None:
    """Fire-and-forget HTTP POST to ESP8266. Timeout 1s, errors silently ignored."""
    try:
        async with httpx.AsyncClient(timeout=1.0) as client:
            await client.post(f"{esp_url.rstrip('/')}{path}")
    except Exception:
        pass

from app.database.session import get_db
from app.models.admin import Admin
from app.models.device import Device
from app.core.security import get_current_admin, verify_device_token
from app.schemas.attendance import (
    AttendanceCreate, AttendanceResponse, AttendanceBulkSync,
    VerifyFaceRequest, VerifyFaceResponse,
)
from app.services.attendance_service import (
    create_attendance, bulk_sync_attendance, get_class_attendance,
    get_today_attendance, verify_face_and_log, get_absent_students,
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


@router.post("/verify-face", response_model=VerifyFaceResponse)
async def verify_face(
    data: VerifyFaceRequest,
    db: AsyncSession = Depends(get_db),
    device: Device = Depends(verify_device_token),
):
    """
    Web Kiosk: nhận ảnh JPEG (base64) từ browser, nhận diện khuôn mặt,
    điểm danh tự động và broadcast realtime tới Dashboard.
    Auth: X-Device-Token header (cùng cơ chế với Edge device).
    """
    from app.websocket.attendance_ws import broadcast_attendance

    esp = device.esp8266_url  # e.g. "http://192.168.1.50" or None

    # ── Notify ESP8266: scan started → red LED blinks (fire-and-forget) ──────
    if esp:
        asyncio.create_task(_notify_esp(esp, "/door/scan"))

    result = await verify_face_and_log(
        db, data.image_b64, data.class_id,
        device_id=device.id,
        challenge_dir=data.challenge_dir,
    )

    # ── Notify ESP8266: result → open or deny ─────────────────────────────────
    if esp:
        status = result.get("status", "")
        if status in ("present", "already_marked"):
            asyncio.create_task(_notify_esp(esp, "/door/open"))
        elif status in ("unknown", "no_face", "liveness_failed", "error"):
            asyncio.create_task(_notify_esp(esp, "/door/deny"))

    # ── Enrich result with class info for WS broadcast ────────────────────────
    from sqlalchemy import select as sa_select
    from app.models.class_ import Class
    _cls_res = await db.execute(sa_select(Class).where(Class.id == data.class_id))
    _cls = _cls_res.scalar_one_or_none()
    result["class_id"]   = data.class_id
    result["class_name"] = _cls.class_name if _cls else f"Class #{data.class_id}"
    result["class_code"] = _cls.class_code if _cls else ""

    # ── Broadcast WS for dashboard realtime feed ──────────────────────────────
    await broadcast_attendance(data.class_id, result)

    return VerifyFaceResponse(**result)

@router.get("/today", response_model=List[AttendanceResponse])
async def get_today(
    db: AsyncSession = Depends(get_db),
    _: Admin = Depends(get_current_admin)
):
    """All attendance records for today across every class — used by dashboard real-time feed."""
    records = await get_today_attendance(db)
    return [
        AttendanceResponse(
            id=r.id,
            student_id=r.student_id,
            student_name=r.student.full_name if r.student else None,
            class_id=r.class_id,
            class_name=r.class_.class_name if r.class_ else None,
            class_code=r.class_.class_code if r.class_ else None,
            timestamp=r.timestamp,
            confidence=r.confidence,
            liveness_score=r.liveness_score,
            status=r.status,
            method=r.method,
        )
        for r in records
    ]


@router.get("/class/{class_id}", response_model=List[AttendanceResponse])
async def get_attendance(
    class_id: UUID,
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


@router.get("/class/{class_id}/absent")
async def get_absent(
    class_id: UUID,
    date: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
    _: Admin = Depends(get_current_admin),
):
    """Return active students who have no 'present' record for the given date."""
    students = await get_absent_students(db, class_id, date)
    return [
        {
            "student_id": s.id,
            "student_code": s.student_code,
            "student_name": s.full_name,
            "email": s.email,
        }
        for s in students
    ]


@router.get("/export")
async def export_attendance_excel(
    class_id: UUID = Query(...),
    date: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
    _: Admin = Depends(get_current_admin),
):
    """
    Download attendance records for a class/date as an Excel workbook (.xlsx).
    Includes two sheets: 'Present' and 'Absent'.
    """
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from datetime import date as date_type
    from sqlalchemy import select as sa_select
    from app.models.class_ import Class

    target_date = date.date() if date else date_type.today()

    # ── Fetch class name ──────────────────────────────────────────────────────
    cls_result = await db.execute(sa_select(Class).where(Class.id == class_id))
    cls_obj = cls_result.scalar_one_or_none()
    class_name = cls_obj.class_name if cls_obj else f"Class {class_id}"

    # ── Fetch attendance data ─────────────────────────────────────────────────
    present_records = await get_class_attendance(db, class_id, date)
    absent_students = await get_absent_students(db, class_id, date)

    # ── Build workbook ────────────────────────────────────────────────────────
    wb = openpyxl.Workbook()

    # Helpers
    header_font   = Font(bold=True, color="FFFFFF")
    green_fill    = PatternFill("solid", fgColor="217346")   # Excel green
    red_fill      = PatternFill("solid", fgColor="C00000")
    center        = Alignment(horizontal="center", vertical="center")
    thin          = Border(
        left=Side(style="thin"), right=Side(style="thin"),
        top=Side(style="thin"), bottom=Side(style="thin"),
    )

    def _style_header(ws, headers, fill):
        ws.append(headers)
        for cell in ws[1]:
            cell.font      = header_font
            cell.fill      = fill
            cell.alignment = center
            cell.border    = thin

    def _style_row(ws, row_idx):
        for cell in ws[row_idx]:
            cell.alignment = center
            cell.border    = thin

    # ── Sheet 1: Present ──────────────────────────────────────────────────────
    ws_present = wb.active
    ws_present.title = "Present"
    _style_header(ws_present, ["#", "Student ID", "Full Name", "Time", "Confidence (%)", "Method"], green_fill)
    ws_present.column_dimensions["C"].width = 28
    ws_present.column_dimensions["D"].width = 22
    ws_present.column_dimensions["E"].width = 16
    ws_present.column_dimensions["F"].width = 14

    for idx, r in enumerate(present_records, start=1):
        conf_pct = round(r.confidence * 100, 1) if r.confidence is not None else ""
        time_str = r.timestamp.strftime("%H:%M:%S") if r.timestamp else ""
        ws_present.append([
            idx,
            r.student.student_code if r.student else r.student_id,
            r.student.full_name if r.student else f"Student #{r.student_id}",
            time_str,
            conf_pct,
            r.method or "",
        ])
        _style_row(ws_present, idx + 1)

    # ── Sheet 2: Absent ───────────────────────────────────────────────────────
    ws_absent = wb.create_sheet("Absent")
    _style_header(ws_absent, ["#", "Student Code", "Full Name", "Email"], red_fill)
    ws_absent.column_dimensions["C"].width = 28
    ws_absent.column_dimensions["D"].width = 32

    for idx, s in enumerate(absent_students, start=1):
        ws_absent.append([
            idx,
            s.student_code,
            s.full_name,
            s.email or "",
        ])
        _style_row(ws_absent, idx + 1)

    # ── Meta sheet ─────────────────────────────────────────────────────────────
    ws_meta = wb.create_sheet("Summary", 0)
    ws_meta.append(["Report", "Attendance Report"])
    ws_meta.append(["Class", class_name])
    ws_meta.append(["Date", str(target_date)])
    ws_meta.append(["Present", len(present_records)])
    ws_meta.append(["Absent", len(absent_students)])
    ws_meta.append(["Generated", datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")])
    for row in ws_meta.iter_rows():
        for cell in row:
            if cell.column == 1:
                cell.font = Font(bold=True)
    ws_meta.column_dimensions["A"].width = 14
    ws_meta.column_dimensions["B"].width = 32

    # ── Stream response ───────────────────────────────────────────────────────
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"attendance_{class_name.replace(' ', '_')}_{target_date}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )