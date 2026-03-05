import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, func, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database.session import Base


class StudentEnrollment(Base):
    __tablename__ = "student_enrollments"
    __table_args__ = (UniqueConstraint("student_id", "class_id", name="uq_student_class"),)

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id  = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    class_id    = Column(UUID(as_uuid=True), ForeignKey("classes.id",  ondelete="CASCADE"), nullable=False, index=True)
    status      = Column(String(10), nullable=False, default="active")   # active | dropped
    enrolled_at = Column(DateTime, default=func.now())

    student = relationship("Student", back_populates="enrollments")
    class_  = relationship("Class",   back_populates="enrollments")
