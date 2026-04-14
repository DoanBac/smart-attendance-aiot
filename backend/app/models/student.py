import uuid
from sqlalchemy import Column, String, LargeBinary, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database.session import Base

class Student(Base):
    __tablename__ = "students"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    student_code    = Column(String(20), unique=True, nullable=False, index=True)
    full_name       = Column(String(100), nullable=False)
    email           = Column(String(150), unique=True, nullable=True)
    phone           = Column(String(20), nullable=True)
    class_id        = Column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=True)  # legacy — primary class
    # AES-256-GCM encrypted 512-dim float32 vector stored as bytes
    face_embedding  = Column(LargeBinary, nullable=True)
    enrollment_date = Column(DateTime, default=func.now())
    status          = Column(String(10), default="active")   # active | inactive
    created_at      = Column(DateTime, default=func.now())
    updated_at      = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    class_          = relationship("Class", back_populates="students", foreign_keys=[class_id])
    enrollments     = relationship("StudentEnrollment", back_populates="student", cascade="all, delete-orphan")
    attendances     = relationship("Attendance", back_populates="student")