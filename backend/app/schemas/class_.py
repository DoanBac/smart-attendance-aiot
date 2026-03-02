from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class ClassCreate(BaseModel):
    class_code: str          # VD: "CNTT01"
    class_name: str          # VD: "Cong Nghe Thong Tin K1"
    description: Optional[str] = None
    teacher_id: Optional[int] = None
    semester: Optional[str] = None
    academic_year: Optional[str] = None

class ClassUpdate(BaseModel):
    class_name: Optional[str] = None
    description: Optional[str] = None
    teacher_id: Optional[int] = None
    semester: Optional[str] = None
    academic_year: Optional[str] = None
    status: Optional[str] = None

class ClassResponse(BaseModel):
    id: int
    class_code: str
    class_name: str
    description: Optional[str]
    teacher_id: Optional[int]
    semester: Optional[str]
    academic_year: Optional[str]
    status: str
    created_at: Optional[datetime]

    class Config:
        from_attributes = True