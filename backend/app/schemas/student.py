from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime

class StudentCreate(BaseModel):
    student_code: str
    full_name: str
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    class_id: Optional[int] = None

class StudentUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    class_id: Optional[int] = None
    status: Optional[str] = None

class StudentResponse(BaseModel):
    id: int
    student_code: str
    full_name: str
    email: Optional[str]
    phone: Optional[str]
    class_id: Optional[int]
    status: str
    enrollment_date: Optional[datetime]
    has_face: bool = False

    class Config:
        from_attributes = True

class EmbeddingUpload(BaseModel):
    student_id: int
    # Base64-encoded raw float32 bytes (512 dims) — will be encrypted server-side
    embedding_b64: str
    quality_score: Optional[float] = None