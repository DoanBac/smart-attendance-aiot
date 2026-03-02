from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional, List
import base64
import json
import numpy as np

from app.database.session import get_db
from app.models.admin import Admin
from app.core.security import get_current_admin
from app.core.redis_client import get_redis
from app.schemas.student import EmbeddingUpload
from app.services.face_service import store_embedding, identify_face, face_service

router = APIRouter()

# Redis key pattern: enrollment:{student_id} -> JSON list of base64-encoded embeddings
# TTL: 30 minutes - session auto-deleted if admin abandons enrollment
ENROLLMENT_TTL_SECONDS = 1800


def _redis_key(student_id: int) -> str:
    return f"enrollment:{student_id}"


class CaptureFrameRequest(BaseModel):
    student_id: int
    frame_b64: str          # raw base64 JPEG (no data:image prefix)
    step_index: int


class FinalizeRequest(BaseModel):
    student_id: int


@router.post("/capture-frame", response_model=dict)
async def capture_frame(
    data: CaptureFrameRequest,
    db: AsyncSession = Depends(get_db),
    _: Admin = Depends(get_current_admin)
):
    """
    Receive 1 JPEG frame from browser camera.
    Detect face -> extract ArcFace embedding -> buffer into Redis session.
    Session auto-expires after 30 minutes if not finalized.
    """
    try:
        img_bytes = base64.b64decode(data.frame_b64)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid frame_b64")

    try:
        emb, quality, meta = await face_service.extract_embedding(
            img_bytes,
            angle="center",
            min_blur=60.0,
        )
    except ValueError as e:
        return {"accepted": False, "reason": str(e), "buffered": 0}

    # Serialize embedding to base64 string for JSON storage in Redis
    emb_b64 = base64.b64encode(emb.astype(np.float32).tobytes()).decode()

    redis = await get_redis()
    key = _redis_key(data.student_id)

    # Append to list, reset TTL
    raw = await redis.get(key)
    session: List[str] = json.loads(raw) if raw else []
    session.append(emb_b64)
    await redis.set(key, json.dumps(session), ex=ENROLLMENT_TTL_SECONDS)

    return {
        "accepted": True,
        "quality": round(quality, 4),
        "buffered": len(session),
    }


@router.post("/finalize", response_model=dict)
async def finalize_enrollment(
    data: FinalizeRequest,
    db: AsyncSession = Depends(get_db),
    _: Admin = Depends(get_current_admin)
):
    """
    Aggregate all buffered Redis embeddings -> create master embedding -> save to DB.
    """
    redis = await get_redis()
    key = _redis_key(data.student_id)

    raw = await redis.get(key)
    if not raw:
        raise HTTPException(
            status_code=422,
            detail="No enrollment session found. Please capture frames first."
        )

    session: List[str] = json.loads(raw)
    if len(session) < 5:
        raise HTTPException(
            status_code=422,
            detail=f"Only {len(session)} valid frames captured. Need at least 5. "
                   "Ensure face is clearly visible and well-lit."
        )

    # Deserialize embeddings from base64
    embeddings = [
        np.frombuffer(base64.b64decode(e), dtype=np.float32)
        for e in session
    ]

    # Weighted average -> re-normalize (FaceID-style)
    mean_emb = np.mean(embeddings, axis=0)
    mean_emb = mean_emb / (np.linalg.norm(mean_emb) + 1e-10)
    emb_b64 = base64.b64encode(mean_emb.astype(np.float32).tobytes()).decode()

    try:
        await store_embedding(db, data.student_id, emb_b64)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Clear Redis session
    await redis.delete(key)

    return {
        "success": True,
        "student_id": data.student_id,
        "frames_used": len(embeddings),
        "message": f"Enrollment successful from {len(embeddings)} high-quality frames",
    }


@router.post("/upload-embedding", response_model=dict)
async def upload_embedding(
    data: EmbeddingUpload,
    db: AsyncSession = Depends(get_db),
    _: Admin = Depends(get_current_admin)
):
    """
    Receive base64-encoded 512-dim float32 embedding directly.
    Server encrypts with AES-256-GCM and stores.
    """
    try:
        await store_embedding(db, data.student_id, data.embedding_b64)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"message": "Embedding stored successfully", "student_id": data.student_id}


@router.post("/identify", response_model=dict)
async def identify(
    data: EmbeddingUpload,
    class_id: int = None,
    db: AsyncSession = Depends(get_db),
):
    """Cloud-side identification (used when Edge cannot match locally)."""
    student_id, score = await identify_face(db, data.embedding_b64, class_id)
    if student_id:
        return {"matched": True, "student_id": student_id, "confidence": round(score, 4)}
    return {"matched": False, "student_id": None, "confidence": round(score, 4)}
