from pydantic import BaseModel, ConfigDict, field_validator
from typing import Optional
from datetime import datetime


class DeviceRegister(BaseModel):
    device_name: str
    location: Optional[str] = None
    class_id: Optional[int] = None


class DeviceHeartbeat(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    firmware_version: Optional[str] = None
    model_version: Optional[str] = None
    ip_address: Optional[str] = None
    status: str = "active"


class DeviceResponse(BaseModel):
    model_config = ConfigDict(
        protected_namespaces=(),
        from_attributes=True,
    )

    id: int
    device_name: Optional[str] = None
    device_token: str
    class_id: Optional[int] = None
    ip_address: Optional[str] = None
    location: Optional[str] = None
    firmware_version: Optional[str] = None
    model_version: Optional[str] = None
    status: str
    last_heartbeat: Optional[datetime] = None
    created_at: Optional[datetime] = None