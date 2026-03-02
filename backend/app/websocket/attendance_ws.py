"""
WebSocket endpoint for real-time attendance updates to Admin Dashboard.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, List
import json
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

class ConnectionManager:
    def __init__(self):
        # class_id → list of websocket connections
        self.active: Dict[int, List[WebSocket]] = {}

    async def connect(self, ws: WebSocket, class_id: int):
        await ws.accept()
        self.active.setdefault(class_id, []).append(ws)
        logger.info(f"WS connected for class {class_id}")

    def disconnect(self, ws: WebSocket, class_id: int):
        if class_id in self.active:
            try:
                self.active[class_id].remove(ws)
            except ValueError:
                pass

    async def broadcast(self, class_id: int, message: dict):
        for ws in self.active.get(class_id, []):
            try:
                await ws.send_text(json.dumps(message))
            except Exception:
                pass

manager = ConnectionManager()

@router.websocket("/attendance/{class_id}")
async def attendance_ws(websocket: WebSocket, class_id: int):
    await manager.connect(websocket, class_id)
    try:
        while True:
            # Keep connection alive; Edge pushes via REST, server broadcasts via manager
            data = await websocket.receive_text()
            # Optionally handle ping/pong
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket, class_id)

async def broadcast_attendance(class_id: int, record: dict):
    """Called by attendance_service after a new record is saved."""
    await manager.broadcast(class_id, {"event": "attendance", "data": record})