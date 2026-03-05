"""
WebSocket endpoint for real-time attendance updates to Admin Dashboard.

Multi-worker architecture (--workers N):
  When uvicorn runs N workers, each process has its OWN ConnectionManager.
  A POST /api/attendance/ on worker-2 must reach WS clients on worker-1.

  Solution: Redis Pub/Sub
  ┌─────────────────────────────────────────────────────┐
  │  attendance_service  ──publish──▶  Redis channel    │
  │                                   ws:attendance:{id}│
  │  worker-1 subscriber ◀─receive──  Redis channel    │
  │      └─▶ broadcast to local WS clients             │
  │  worker-2 subscriber ◀─receive──  Redis channel    │
  │      └─▶ broadcast to local WS clients (0 here)    │
  └─────────────────────────────────────────────────────┘
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, List
import json
import asyncio
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

REDIS_CHANNEL_PREFIX = "ws:attendance:"
GLOBAL_CLASS_ID = "0"   # virtual id used for the "all classes" dashboard channel


class ConnectionManager:
    def __init__(self):
        # class_id → list of websocket connections (local to this worker)
        self.active: Dict[str, List[WebSocket]] = {}

    async def connect(self, ws: WebSocket, class_id):
        await ws.accept()
        class_id = str(class_id)
        self.active.setdefault(class_id, []).append(ws)
        logger.info(f"WS connected for class {class_id}  (total: {len(self.active[class_id])})")

    def disconnect(self, ws: WebSocket, class_id):
        class_id = str(class_id)
        if class_id in self.active:
            try:
                self.active[class_id].remove(ws)
            except ValueError:
                pass

    async def broadcast_local(self, class_id, message: dict):
        """Send to all WS clients connected to THIS worker."""
        class_id = str(class_id)
        dead = []
        for ws in self.active.get(class_id, []):
            try:
                await ws.send_text(json.dumps(message))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws, class_id)


manager = ConnectionManager()


# ── Redis Pub/Sub subscriber (runs as background asyncio task per worker) ─────

async def _redis_subscriber():
    """
    Subscribe to ws:attendance:* on Redis.
    On each message, forward to local WS clients in this worker.
    Re-connects automatically on Redis error.
    """
    import redis.asyncio as aioredis
    from app.config import settings

    while True:
        try:
            r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
            pubsub = r.pubsub()
            await pubsub.psubscribe(f"{REDIS_CHANNEL_PREFIX}*")
            logger.info("WS Redis subscriber started (psubscribe ws:attendance:*)")

            async for message in pubsub.listen():
                if message["type"] != "pmessage":
                    continue
                try:
                    # channel = "ws:attendance:5" → class_id = 5
                    channel: str = message["channel"]
                    class_id = channel.split(":")[-1]
                    data = json.loads(message["data"])
                    await manager.broadcast_local(class_id, data)
                except Exception as e:
                    logger.warning(f"WS subscriber parse error: {e}")

        except asyncio.CancelledError:
            logger.info("WS Redis subscriber cancelled.")
            return
        except Exception as e:
            logger.warning(f"WS Redis subscriber error: {e} — reconnecting in 3s")
            await asyncio.sleep(3)


_subscriber_task: asyncio.Task | None = None


def start_redis_subscriber():
    """Called from main.py lifespan startup — starts subscriber in background."""
    global _subscriber_task
    loop = asyncio.get_event_loop()
    _subscriber_task = loop.create_task(_redis_subscriber())
    logger.info("WS Redis subscriber task created.")


def stop_redis_subscriber():
    """Called from main.py lifespan shutdown."""
    global _subscriber_task
    if _subscriber_task and not _subscriber_task.done():
        _subscriber_task.cancel()


# ── REST → Redis publish ──────────────────────────────────────────────────────

def _json_default(obj):
    """Custom JSON serializer for UUID and datetime objects."""
    import uuid
    from datetime import datetime
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


async def broadcast_attendance(class_id: str, record: dict):
    """
    Called by attendance_service after a new record is saved.
    Publishes to Redis so ALL workers (with WS clients) receive it.
    Also publishes to the global channel (GLOBAL_CLASS_ID=0) for dashboard.
    """
    from app.core.redis_client import get_redis
    payload = json.dumps({"event": "attendance", "data": record}, default=_json_default)
    try:
        redis = await get_redis()
        channel = f"{REDIS_CHANNEL_PREFIX}{class_id}"
        await redis.publish(channel, payload)
        # Also broadcast to global dashboard channel
        if class_id != GLOBAL_CLASS_ID:
            await redis.publish(f"{REDIS_CHANNEL_PREFIX}{GLOBAL_CLASS_ID}", payload)
        logger.debug(f"Published attendance to Redis channel {channel} + global")
    except Exception as e:
        # Fallback: broadcast locally if Redis publish fails
        logger.warning(f"Redis publish failed ({e}), falling back to local broadcast")
        await manager.broadcast_local(class_id, {"event": "attendance", "data": record})
        await manager.broadcast_local(GLOBAL_CLASS_ID, {"event": "attendance", "data": record})


# ── WebSocket endpoint ────────────────────────────────────────────────────────

@router.websocket("/attendance/all")
async def attendance_ws_all(websocket: WebSocket):
    """Global dashboard channel — receives events from ALL classes."""
    await manager.connect(websocket, GLOBAL_CLASS_ID)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket, GLOBAL_CLASS_ID)
        logger.info("WS disconnected from global dashboard channel")


@router.websocket("/attendance/{class_id}")
async def attendance_ws(websocket: WebSocket, class_id: str):
    await manager.connect(websocket, class_id)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket, class_id)
        logger.info(f"WS disconnected for class {class_id}")
