from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from uuid import UUID


class ScheduleSchema(BaseModel):
    days: Optional[List[str]] = []       # ["Mon", "Wed", "Fri"]
    start_time: Optional[str] = None     # "08:00"
    end_time: Optional[str] = None       # "09:30"


class ClassCreate(BaseModel):
    class_code: Optional[str] = None   # If omitted, auto-generated as UUID8 (e.g. a3f9c2b1)
    class_name: str
    subject: Optional[str] = None
    room: Optional[str] = None
    capacity: Optional[int] = None
    teacher_id: Optional[UUID] = None
    semester: Optional[str] = None
    academic_year: Optional[str] = None
    schedule: Optional[ScheduleSchema] = None


class ClassUpdate(BaseModel):
    class_name: Optional[str] = None
    subject: Optional[str] = None
    room: Optional[str] = None
    capacity: Optional[int] = None
    teacher_id: Optional[UUID] = None
    semester: Optional[str] = None
    academic_year: Optional[str] = None
    schedule: Optional[ScheduleSchema] = None
    status: Optional[str] = None


class ClassResponse(BaseModel):
    id: UUID
    class_code: str
    class_name: str
    subject: Optional[str] = None
    room: Optional[str] = None
    capacity: Optional[int] = None
    teacher_id: Optional[UUID] = None
    semester: Optional[str] = None
    academic_year: Optional[str] = None
    schedule: Optional[dict] = None
    status: str
    student_count: int = 0
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
