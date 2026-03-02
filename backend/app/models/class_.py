from sqlalchemy import Column, Integer, String, JSON, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from app.database.session import Base

class Class(Base):
    __tablename__ = "classes"

    id          = Column(Integer, primary_key=True, index=True)
    class_code  = Column(String(20), unique=True, nullable=False, index=True)
    class_name  = Column(String(100), nullable=False)
    subject     = Column(String(100), nullable=True)
    # {"days": ["Mon","Wed"], "time": "08:00", "duration_minutes": 90}
    schedule    = Column(JSON, nullable=True)
    room        = Column(String(50), nullable=True)
    teacher_id  = Column(Integer, ForeignKey("admins.id"), nullable=True)
    semester    = Column(String(20), nullable=True)
    status      = Column(String(10), default="active")
    created_at  = Column(DateTime, default=func.now())

    # Relationships
    students    = relationship("Student", back_populates="class_")
    attendances = relationship("Attendance", back_populates="class_")
    devices     = relationship("Device", back_populates="class_")
    teacher     = relationship("Admin", back_populates="classes")