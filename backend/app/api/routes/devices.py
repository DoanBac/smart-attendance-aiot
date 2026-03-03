from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from app.database.session import get_db
from app.models.admin import Admin
from app.models.device import Device
from app.core.security import get_current_admin, verify_device_token
from app.schemas.device import DeviceRegister, DeviceHeartbeat, DeviceResponse, DeviceUpdate
from app.services.device_service import register_device, update_heartbeat

router = APIRouter()

@router.post("/register", response_model=DeviceResponse, status_code=201)
async def register(
    data: DeviceRegister,
    db: AsyncSession = Depends(get_db),
    _: Admin = Depends(get_current_admin)
):
    device = await register_device(db, data)
    return device

@router.post("/heartbeat", response_model=dict)
async def heartbeat(
    data: DeviceHeartbeat,
    db: AsyncSession = Depends(get_db),
    device: Device = Depends(verify_device_token)
):
    await update_heartbeat(db, device, data)
    return {"status": "ok", "device_id": device.id}

@router.patch("/{device_id}", response_model=DeviceResponse)
async def update_device(
    device_id: int,
    data: DeviceUpdate,
    db: AsyncSession = Depends(get_db),
    _: Admin = Depends(get_current_admin),
):
    """Update device fields (name, location, class_id, esp8266_url)."""
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if device is None:
        from fastapi import HTTPException
        raise HTTPException(404, "Device not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(device, field, value)
    await db.flush()
    await db.refresh(device)
    return device


@router.post("/exit", response_model=dict)
async def door_exit(
    db: AsyncSession = Depends(get_db),
    device: Device = Depends(verify_device_token),
):
    """
    ESP8266 exit button: broadcast door_unlock WS event so other clients know,
    then return 200. Optionally log exit to a future access_log table.
    """
    from app.websocket.attendance_ws import broadcast_door
    class_id = device.class_id
    if class_id:
        await broadcast_door(class_id, {
            "event": "door_unlock",
            "class_id": class_id,
            "reason": "exit_button",
        })
    return {"status": "ok", "device_id": device.id, "class_id": class_id}


@router.get("/", response_model=List[DeviceResponse])
async def list_devices(
    db: AsyncSession = Depends(get_db),
    _: Admin = Depends(get_current_admin)
):
    result = await db.execute(select(Device).order_by(Device.created_at.desc()))
    return result.scalars().all()

@router.get("/embeddings/{class_id}")
async def get_embeddings_for_edge(
    class_id: int,
    db: AsyncSession = Depends(get_db),
    device: Device = Depends(verify_device_token)
):
    """
    Edge device requests encrypted embeddings for its class.
    Returns list of {student_id, student_code, full_name, embedding_b64 (AES encrypted)}.
    Edge must decrypt using shared AES key from env.
    """
    from sqlalchemy import select
    from app.models.student import Student
    import base64

    result = await db.execute(
        select(Student).where(
            Student.class_id == class_id,
            Student.face_embedding.isnot(None),
            Student.status == "active"
        )
    )
    students = result.scalars().all()
    payload = []
    for s in students:
        payload.append({
            "student_id": s.id,
            "student_code": s.student_code,
            "full_name": s.full_name,
            "embedding_enc_b64": base64.b64encode(s.face_embedding).decode()
        })
    return {"class_id": class_id, "count": len(payload), "students": payload}