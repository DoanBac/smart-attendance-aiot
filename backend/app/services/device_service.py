import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.device import Device
from app.schemas.device import DeviceRegister, DeviceHeartbeat

async def register_device(db: AsyncSession, data: DeviceRegister) -> Device:
    device_token = uuid.uuid4().hex
    device = Device(
        device_token=device_token,
        device_name=data.device_name,
        location=data.location,
        class_id=data.class_id,
        status="active",
    )
    db.add(device)
    await db.flush()
    await db.refresh(device)
    return device

async def update_heartbeat(
    db: AsyncSession,
    device: Device,
    data: DeviceHeartbeat
) -> Device:
    device.last_heartbeat = datetime.utcnow()  # ← naive UTC, khớp với DB column
    device.status = data.status
    if data.firmware_version:
        device.firmware_version = data.firmware_version
    if data.model_version:
        device.model_version = data.model_version
    if data.ip_address:
        device.ip_address = data.ip_address
    await db.flush()
    return device