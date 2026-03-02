from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from app.database.session import Base

class Device(Base):
    __tablename__ = "devices"

    id               = Column(Integer, primary_key=True, index=True)
    device_token     = Column(String(64), unique=True, nullable=False, index=True)
    device_name      = Column(String(100), nullable=True)
    ip_address       = Column(String(45), nullable=True)
    location         = Column(String(100), nullable=True)
    class_id         = Column(Integer, ForeignKey("classes.id"), nullable=True)
    last_heartbeat   = Column(DateTime, nullable=True)
    status           = Column(String(10), default="active")   # active | inactive | error
    firmware_version = Column(String(20), nullable=True)
    model_version    = Column(String(20), nullable=True)
    created_at       = Column(DateTime, default=func.now())

    # Relationships
    class_      = relationship("Class", back_populates="devices")
    attendances = relationship("Attendance", back_populates="device")