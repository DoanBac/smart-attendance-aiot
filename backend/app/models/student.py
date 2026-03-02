from sqlalchemy import Column, Integer, String, LargeBinary, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from app.database.session import Base

class Student(Base):
    __tablename__ = "students"

    id              = Column(Integer, primary_key=True, index=True)
    student_code    = Column(String(20), unique=True, nullable=False, index=True)
    full_name       = Column(String(100), nullable=False)
    email           = Column(String(150), unique=True, nullable=True)
    phone           = Column(String(20), nullable=True)
    class_id        = Column(Integer, ForeignKey("classes.id"), nullable=True)
    # AES-256-GCM encrypted 512-dim float32 vector stored as bytes
    face_embedding  = Column(LargeBinary, nullable=True)
    enrollment_date = Column(DateTime, default=func.now())
    status          = Column(String(10), default="active")   # active | inactive
    created_at      = Column(DateTime, default=func.now())
    updated_at      = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    class_          = relationship("Class", back_populates="students")
    attendances     = relationship("Attendance", back_populates="student")