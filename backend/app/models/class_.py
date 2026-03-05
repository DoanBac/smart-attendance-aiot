import uuid
from sqlalchemy import Column, Integer, String, JSON, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database.session import Base

class Class(Base):
    __tablename__ = "classes"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    class_code  = Column(String(20), unique=True, nullable=False, index=True)
    class_name  = Column(String(100), nullable=False)
    subject     = Column(String(100), nullable=True)
    room        = Column(String(50), nullable=True)
    capacity    = Column(Integer, nullable=True)        # max students
    teacher_id  = Column(UUID(as_uuid=True), ForeignKey("admins.id"), nullable=True)
    semester    = Column(String(20), nullable=True)
    academic_year = Column(String(20), nullable=True)
    # schedule: {"days": ["Mon","Wed"], "start_time": "08:00", "end_time": "09:30"}
    schedule    = Column(JSON, nullable=True)
    status      = Column(String(10), default="active")
    created_at  = Column(DateTime, default=func.now())
    updated_at  = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    students    = relationship("Student", back_populates="class_", foreign_keys="Student.class_id")
    enrollments = relationship("StudentEnrollment", back_populates="class_", cascade="all, delete-orphan")
    attendances = relationship("Attendance", back_populates="class_")
    devices     = relationship("Device", back_populates="class_")
    teacher     = relationship("Admin", back_populates="classes")