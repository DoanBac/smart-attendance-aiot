from sqlalchemy import Column, Integer, Float, String, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from app.database.session import Base

class Attendance(Base):
    __tablename__ = "attendance"

    id              = Column(Integer, primary_key=True, index=True)
    student_id      = Column(Integer, ForeignKey("students.id"), nullable=False, index=True)
    class_id        = Column(Integer, ForeignKey("classes.id"), nullable=False, index=True)
    device_id       = Column(Integer, ForeignKey("devices.id"), nullable=True)
    timestamp       = Column(DateTime, nullable=False, index=True)
    confidence      = Column(Float, nullable=True)   # Cosine similarity score
    liveness_score  = Column(Float, nullable=True)   # Liveness detection score
    method          = Column(String(20), default="face")   # face | manual | qr
    status          = Column(String(10), default="present")  # present | absent | late
    synced_from_edge = Column(String(1), default="N")  # Y if synced from offline queue
    created_at      = Column(DateTime, default=func.now())

    # Relationships
    student = relationship("Student", back_populates="attendances")
    class_  = relationship("Class", back_populates="attendances")
    device  = relationship("Device", back_populates="attendances")