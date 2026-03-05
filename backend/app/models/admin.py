import uuid
from sqlalchemy import Column, String, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database.session import Base

class Admin(Base):
    __tablename__ = "admins"

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    username      = Column(String(50), unique=True, nullable=True, index=True)
    email         = Column(String(150), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name     = Column(String(100), nullable=True)
    role          = Column(String(20), default="admin")
    is_active     = Column(Boolean, default=True)
    created_at    = Column(DateTime, server_default=func.now())

    # Relationships
    classes = relationship("Class", back_populates="teacher")