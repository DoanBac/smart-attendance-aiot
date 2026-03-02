from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.config import settings
from app.database.session import engine, Base
from app.api.routes import students, classes, attendance, devices, enrollment, auth
from app.websocket.attendance_ws import router as ws_router
from app.core.redis_client import get_redis, close_redis

import logging
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created/verified.")
    await get_redis()  # warm-up connection pool
    logger.info("Redis connected.")
    yield
    # Shutdown
    await close_redis()
    await engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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