"""
AI Face Inference Service — FastAPI app entry point.

Endpoints:
  GET  /health          — liveness/readiness check
  POST /extract         — JPEG image → ArcFace 512-dim embedding
  POST /identify        — probe embedding × gallery → match result

Internal service: chỉ backend mới gọi được (X-Service-Key header).
Không expose ra internet trực tiếp.
"""
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.inference import router as inference_router
from app.core.face_model import get_face_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

_startup_time = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Warm-up InsightFace model on startup — tránh cold-start khi request đầu tiên đến."""
    logger.info("🚀 AI Service starting up — pre-loading InsightFace model...")
    try:
        get_face_app()   # trigger lazy init ngay khi boot
        logger.info("✅ InsightFace model ready")
    except Exception as e:
        logger.error(f"❌ Failed to pre-load InsightFace: {e}")
        # Không crash — model có thể load lại ở request đầu tiên

    yield

    logger.info("AI Service shutting down")


app = FastAPI(
    title="AI Face Inference Service",
    description=(
        "Internal microservice xử lý inference khuôn mặt: "
        "extract ArcFace embedding, cosine similarity matching. "
        "Chỉ gọi được từ backend (X-Service-Key auth)."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — chỉ cho phép internal Docker network (backend service)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://backend:8000", "http://localhost:8000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Routes
app.include_router(inference_router, prefix="/api/v1", tags=["inference"])


@app.get("/health", tags=["health"])
async def health():
    """Readiness probe — k8s / docker healthcheck gọi endpoint này."""
    uptime = round(time.time() - _startup_time, 1)
    model_loaded = True
    try:
        from app.core.face_model import _face_app
        model_loaded = _face_app is not None
    except Exception:
        model_loaded = False

    return {
        "status": "healthy",
        "service": "ai-face-inference",
        "version": "1.0.0",
        "model_loaded": model_loaded,
        "uptime_seconds": uptime,
    }
