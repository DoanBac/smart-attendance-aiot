from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime
from uuid import UUID


class ClassBrief(BaseModel):
    id: UUID
    class_code: str
    class_name: str
    subject: Optional[str] = None
    schedule: Optional[dict] = None

    class Config:
        from_attributes = True


class StudentCreate(BaseModel):
    # student_code is always auto-generated server-side (FSB000001, FSB000002, ...)
    full_name: str
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    class_ids: Optional[List[UUID]] = []   # enroll in multiple classes at creation


class StudentUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    status: Optional[str] = None   # "active" | "inactive"


class StudentResponse(BaseModel):
    id: UUID
    student_code: str
    full_name: str
    email: Optional[str]
    phone: Optional[str]
    class_id: Optional[UUID]          # legacy primary class
    status: str
    enrollment_date: Optional[datetime]
    has_face: bool = False
    enrolled_classes: List[ClassBrief] = []

    class Config:
        from_attributes = True


class EnrollRequest(BaseModel):
    class_id: UUID


class EmbeddingUpload(BaseModel):
    student_id: UUID
    # Base64-encoded raw float32 bytes (512 dims) - will be encrypted server-side
    embedding_b64: str
    quality_score: Optional[float] = None
