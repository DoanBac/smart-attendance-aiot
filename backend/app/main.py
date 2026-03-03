from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.config import settings
from app.database.session import engine
from app.api.routes import students, classes, attendance, devices, enrollment, auth
from app.websocket.attendance_ws import router as ws_router, start_redis_subscriber, stop_redis_subscriber
from app.core.redis_client import get_redis, close_redis
from app.api.middleware.rate_limiter import RateLimitMiddleware

import logging
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    # NOTE: DB schema is managed by Alembic (start.sh runs `alembic upgrade head`
    # before uvicorn starts, so tables are ready before any request is served).
    await get_redis()  # warm-up connection pool
    logger.info("Redis connected.")
    start_redis_subscriber()  # starts Redis Pub/Sub → WS broadcast task
    logger.info("WS Redis subscriber started.")
    yield
    # Shutdown
    stop_redis_subscriber()
    await close_redis()
    await engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# CORS — controlled via ALLOWED_ORIGINS in config / .env
# When ALLOWED_ORIGINS=["*"] (demo/local), allow all via regex (supports credentials).
# In production: set explicit origins, e.g. ["https://your-domain.com"].
_origins = settings.ALLOWED_ORIGINS
_wildcard = "*" in _origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=[] if _wildcard else _origins,
    allow_origin_regex=".*" if _wildcard else None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting — Redis-backed sliding window (100 req/min per IP by default)
app.add_middleware(
    RateLimitMiddleware,
    calls=settings.RATE_LIMIT_PER_MINUTE,
    period=60,
)

app.include_router(auth.router,       prefix="/api/auth",       tags=["auth"])
app.include_router(students.router,   prefix="/api/students",   tags=["students"])
app.include_router(classes.router,    prefix="/api/classes",    tags=["classes"])
app.include_router(attendance.router, prefix="/api/attendance", tags=["attendance"])
app.include_router(devices.router,    prefix="/api/devices",    tags=["devices"])
app.include_router(enrollment.router, prefix="/api/enrollment", tags=["enrollment"])

# WebSocket — prefix /ws agar cocok dengan frontend: ws://host/ws/attendance/{class_id}
app.include_router(ws_router, prefix="/ws")


@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": settings.APP_VERSION}