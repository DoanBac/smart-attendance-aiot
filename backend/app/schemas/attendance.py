from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from uuid import UUID

class AttendanceCreate(BaseModel):
    student_id: UUID
    class_id: UUID
    device_id: Optional[UUID] = None
    timestamp: datetime
    confidence: Optional[float] = None
    liveness_score: Optional[float] = None
    method: str = "face"
    status: str = "present"

class AttendanceBulkSync(BaseModel):
    """Used by Edge device to sync offline queue."""
    records: List[AttendanceCreate]
    device_token: str

class AttendanceResponse(BaseModel):
    id: UUID
    student_id: UUID
    student_name: Optional[str] = None
    class_id: UUID
    class_name: Optional[str] = None
    class_code: Optional[str] = None
    timestamp: datetime
    confidence: Optional[float]
    liveness_score: Optional[float]
    status: str
    method: str

    class Config:
        from_attributes = True

class AttendanceReport(BaseModel):
    class_id: UUID
    class_name: str
    total_sessions: int
    student_stats: List[dict]


# ── Web Kiosk Verify ─────────────────────────────────────────────────────────
class VerifyFaceRequest(BaseModel):
    image_b64: str          # Raw base64 JPEG
    class_id: UUID
    challenge_dir: Optional[str] = None  # "left" | "right" — pose liveness challenge


class VerifySequenceRequest(BaseModel):
    images_b64: List[str]   # Burst frames for blink liveness
    class_id: UUID


class VerifyFaceResponse(BaseModel):
    matched: bool
    student_id: Optional[UUID] = None
    student_name: Optional[str] = None
    student_code: Optional[str] = None
    confidence: float = 0.0
    # "present" | "already_marked" | "unknown" | "no_face" | "error"
    status: str
    message: str
    attendance_id: Optional[UUID] = None