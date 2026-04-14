from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import StreamingResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
import httpx

from app.database.session import get_db
from app.models.admin import Admin
from app.models.device import Device
from app.core.security import get_current_admin, verify_device_token
from app.schemas.device import DeviceRegister, DeviceHeartbeat, DeviceResponse, DeviceUpdate
from app.services.device_service import register_device, update_heartbeat
from uuid import UUID

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

    # Fetch class info so edge can hot-reload its config without manual .env edits
    class_name: str | None = None
    if device.class_id:
        from app.models.class_ import Class
        cls_result = await db.execute(select(Class).where(Class.id == device.class_id))
        cls = cls_result.scalar_one_or_none()
        class_name = cls.class_name if cls else None

    return {
        "status": "ok",
        "device_id": str(device.id),
        "device_name": device.device_name,
        "class_id": str(device.class_id) if device.class_id else None,
        "class_name": class_name,
    }

@router.patch("/{device_id}", response_model=DeviceResponse)
async def update_device(
    device_id: UUID,
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
    class_id: UUID,
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


# ──────────────────────────────────────────────────────────────────────────────
# Edge stream proxy — lets HTTPS kiosk page access HTTP edge device via backend
# ──────────────────────────────────────────────────────────────────────────────

async def _get_device_for_proxy(request: Request, db: AsyncSession) -> Device:
    """Authenticate via X-Device-Token header or ?token= query param."""
    device_token = request.headers.get("X-Device-Token") or request.query_params.get("token")
    if not device_token:
        raise HTTPException(status_code=401, detail="Device token required")
    result = await db.execute(select(Device).where(Device.device_token == device_token))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=403, detail="Invalid device token")
    if not device.ip_address:
        raise HTTPException(status_code=503, detail="Device has no IP address recorded — send a heartbeat first")
    return device


@router.get("/by-class/{class_code}/edge-snapshot")
async def edge_snapshot_proxy(
    class_code: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Proxy a single JPEG snapshot from the edge device.
    Allows an HTTPS kiosk page to capture frames without Mixed-Content errors.
    Auth: X-Device-Token header or ?token= query param.
    """
    device = await _get_device_for_proxy(request, db)
    edge_url = f"http://{device.ip_address}:5000/snapshot"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(edge_url)
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Edge returned {resp.status_code}")
        return Response(
            content=resp.content,
            media_type="image/jpeg",
            headers={"Cache-Control": "no-cache, no-store", "Access-Control-Allow-Origin": "*"},
        )
    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail=f"Cannot reach edge device: {e}")


@router.get("/by-class/{class_code}/edge-stream")
async def edge_stream_proxy(
    class_code: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Proxy the MJPEG stream from the edge device.
    Allows an HTTPS kiosk page to display live video without Mixed-Content errors.
    Auth: X-Device-Token header or ?token= query param.
    """
    device = await _get_device_for_proxy(request, db)
    edge_url = f"http://{device.ip_address}:5000/video"

    async def _proxy():
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(None)) as client:
                async with client.stream("GET", edge_url) as resp:
                    async for chunk in resp.aiter_bytes(4096):
                        yield chunk
        except Exception:
            return  # client disconnected or edge went away

    return StreamingResponse(
        _proxy(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-cache, no-store", "Access-Control-Allow-Origin": "*"},
    )