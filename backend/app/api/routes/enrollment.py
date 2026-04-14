import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional, List, Tuple
import base64
import json
import numpy as np

from app.database.session import get_db
from app.models.admin import Admin
from app.core.security import get_current_admin
from app.core.redis_client import get_redis
from app.schemas.student import EmbeddingUpload
from app.services.face_service import store_embedding, identify_face, face_service
from uuid import UUID

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Blur threshold ─────────────────────────────────────────────────────────────
# Set to 0.0 to disable blur check entirely for debugging.
# Once enrollment works, raise back to 15.0-25.0.
MIN_BLUR_ENROLLMENT = 20.0   # Laplacian variance threshold — frames below this are blurry

# Redis key pattern: enrollment:{student_id} -> JSON list of base64-encoded embeddings
# TTL: 30 minutes - session auto-deleted if admin abandons enrollment
ENROLLMENT_TTL_SECONDS = 1800

_INF = float("inf")

# ── Step pose configuration ────────────────────────────────────────────────────
# Maps step_index → expected head pose ranges in degrees.
#
# InsightFace pose convention (standard Euler angles from solvePnP):
#   yaw   > 0  → subject turned to THEIR RIGHT  (camera sees subject's left cheek)
#   yaw   < 0  → subject turned to THEIR LEFT   (camera sees subject's right cheek)
#   pitch > 0  → head tilted DOWN (chin toward chest)
#   pitch < 0  → head tilted UP   (chin raised)
#
# "slightly" = 10–35° away from neutral.
# Raise the |min| threshold if students need to turn more; lower it if the
# model's values are smaller than expected.
POSE_STEP_CONFIG = [
    # Geometric landmark method — yaw/pitch centered at 0° for frontal face.
    #
    # Yaw sign (InsightFace raw frame, webcam mirrored):
    #   physical LEFT turn  → nose moves to RIGHT side of image → yaw > 0
    #   physical RIGHT turn → nose moves to LEFT  side of image → yaw < 0
    #
    # step 0 — Look straight
    {
        "instruction": "Please look straight at the camera",
        "yaw_range":   (-20.0,  20.0),
        "pitch_range": (-20.0,  20.0),
    },
    # step 1 — Turn head LEFT (physical left → raw frame yaw > 0)
    {
        "instruction": "Please turn your head to the LEFT",
        "yaw_range":   (20.0,  _INF),
        "pitch_range": (-40.0,  40.0),
    },
    # step 2 — Turn head RIGHT (physical right → raw frame yaw < 0)
    {
        "instruction": "Please turn your head to the RIGHT",
        "yaw_range":   (-_INF, -20.0),
        "pitch_range": (-40.0,  40.0),
    },
    # step 3 — Tilt UP (chin raised)
    {
        "instruction": "Please tilt your head UP (raise your chin)",
        "yaw_range":   (-35.0,  35.0),
        "pitch_range": (20.0,  _INF),
    },
    # step 4 — Tilt DOWN (lower chin) → pitch < 0
    {
        "instruction": "Please tilt your head DOWN (lower your chin)",
        "yaw_range":   (-35.0,  35.0),
        "pitch_range": (-_INF, -20.0),
    },
    # step 5 — Straight again (confirm)
    {
        "instruction": "Please look straight at the camera again",
        "yaw_range":   (-20.0,  20.0),
        "pitch_range": (-20.0,  20.0),
    },
]


def _redis_key(student_id: UUID) -> str:
    return f"enrollment:{student_id}"


def _check_pose(meta: dict, step_index: int) -> Tuple[bool, str]:
    """
    Validate that the head pose in `meta` matches the expected direction for
    the given enrollment step.

    Returns (ok, reason):
      ok=True  → pose is correct, frame can be accepted
      ok=False → pose is wrong; `reason` is the human-readable instruction
                 that will be displayed to the student.

    If the AI service did not return pose data (yaw/pitch are None), pose
    validation is skipped and the frame is accepted on quality alone.
    """
    if step_index < 0 or step_index >= len(POSE_STEP_CONFIG):
        return True, ""

    yaw   = meta.get("yaw")
    pitch = meta.get("pitch")

    # Degraded mode: model does not support pose estimation → skip check
    if yaw is None or pitch is None:
        return True, ""

    cfg = POSE_STEP_CONFIG[step_index]
    yaw_min,   yaw_max   = cfg["yaw_range"]
    pitch_min, pitch_max = cfg["pitch_range"]

    if not (yaw_min <= yaw <= yaw_max):
        return False, cfg["instruction"]

    if not (pitch_min <= pitch <= pitch_max):
        return False, cfg["instruction"]

    return True, ""


class CaptureFrameRequest(BaseModel):
    student_id: UUID
    frame_b64: str          # raw base64 JPEG (no data:image prefix)
    step_index: int


class FinalizeRequest(BaseModel):
    student_id: UUID


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
            min_blur=MIN_BLUR_ENROLLMENT,
        )
    except ValueError as e:
        # Face not detected, too blurry, or face too small
        reason = str(e)
        logger.warning("[enrollment] step=%d quality-rejected — %s", data.step_index, reason)
        return {"accepted": False, "reason": reason, "buffered": 0}
    except RuntimeError as e:
        # AI service temporarily unavailable — tell frontend to retry, not crash
        reason = "AI service unavailable — retrying…"
        logger.warning("[enrollment] step=%d AI service error: %s", data.step_index, e)
        return {"accepted": False, "reason": reason, "buffered": 0}
    except Exception as e:
        reason = "Internal error — retrying…"
        logger.exception("[enrollment] step=%d unexpected error: %s", data.step_index, e)
        return {"accepted": False, "reason": reason, "buffered": 0}

    # ── Head pose validation ───────────────────────────────────────────────────
    pose_ok, pose_reason = _check_pose(meta, data.step_index)
    if not pose_ok:
        yaw_val = meta.get("yaw")
        pitch_val = meta.get("pitch")
        logger.warning(
            "[enrollment] step=%d pose-rejected — yaw=%s pitch=%s — %s",
            data.step_index, yaw_val, pitch_val, pose_reason,
        )
        reason_with_pose = (
            f"{pose_reason} (yaw={yaw_val:.0f}° pitch={pitch_val:.0f}°)"
            if yaw_val is not None and pitch_val is not None
            else pose_reason
        )
        return {
            "accepted": False,
            "reason": reason_with_pose,
            "buffered": 0,
            "pose": {"yaw": yaw_val, "pitch": pitch_val},
        }

    # ── Anti-spoof / liveness validation ───────────────────────────────────────
    is_live = meta.get("is_live", True)
    liveness_score = meta.get("liveness_score")
    if not is_live:
        logger.warning(
            "[enrollment] step=%d spoof-rejected — score=%s",
            data.step_index,
            liveness_score,
        )
        reason = (
            f"Spoof detected (liveness={liveness_score:.2f}). Please use your real face, not a photo or screen."
            if isinstance(liveness_score, (int, float))
            else "Spoof detected. Please use your real face, not a photo or screen."
        )
        return {
            "accepted": False,
            "reason": reason,
            "buffered": 0,
            "liveness_score": liveness_score,
        }

    # Serialize embedding to base64 string for JSON storage in Redis
    emb_b64 = base64.b64encode(emb.astype(np.float32).tobytes()).decode()

    redis = await get_redis()
    key = _redis_key(data.student_id)

    # Append to list, reset TTL
    raw = await redis.get(key)
    session: List[str] = json.loads(raw) if raw else []
    session.append(emb_b64)
    await redis.set(key, json.dumps(session), ex=ENROLLMENT_TTL_SECONDS)

    logger.warning(
        "[enrollment] step=%d ACCEPTED — quality=%.3f blur=%.1f yaw=%s pitch=%s buffered=%d",
        data.step_index, quality, meta.get("blur_variance", 0),
        meta.get("yaw"), meta.get("pitch"), len(session),
    )

    return {
        "accepted": True,
        "quality": round(quality, 4),
        "buffered": len(session),
        # Debug fields — frontend displays these to help diagnose issues
        "blur_variance": meta.get("blur_variance"),
        "det_score": meta.get("det_score"),
        "yaw": meta.get("yaw"),
        "pitch": meta.get("pitch"),
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
    class_id: UUID = None,
    db: AsyncSession = Depends(get_db),
):
    """Cloud-side identification (used when Edge cannot match locally)."""
    student_id, score = await identify_face(db, data.embedding_b64, class_id)
    if student_id:
        return {"matched": True, "student_id": student_id, "confidence": round(score, 4)}
    return {"matched": False, "student_id": None, "confidence": round(score, 4)}
