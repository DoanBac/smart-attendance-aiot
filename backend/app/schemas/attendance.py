from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class AttendanceCreate(BaseModel):
    student_id: int
    class_id: int
    device_id: Optional[int] = None
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
    id: int
    student_id: int
    student_name: Optional[str] = None
    class_id: int
    timestamp: datetime
    confidence: Optional[float]
    liveness_score: Optional[float]
    status: str
    method: str

    class Config:
        from_attributes = True

class AttendanceReport(BaseModel):
    class_id: int
    class_name: str
    total_sessions: int
    student_stats: List[dict]