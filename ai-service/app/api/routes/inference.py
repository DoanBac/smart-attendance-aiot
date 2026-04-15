"""
POST /extract   — JPEG image → embedding 512-dim + quality
POST /identify  — probe embedding + gallery → match result
"""
import base64
import logging
from typing import List, Optional, Tuple

import numpy as np
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel

from app.config import settings
from app.core.face_model import extract_embedding, batch_identify, extract_sequence

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Auth helper ───────────────────────────────────────────────────────────────
def _verify_service_key(key: Optional[str]):
    """Internal service authentication — only backend can call AI service."""
    if key != settings.SERVICE_SECRET_KEY:
        raise HTTPException(status_code=403, detail="Invalid service key")


# ── Schemas ───────────────────────────────────────────────────────────────────
class ExtractRequest(BaseModel):
    image_b64: str          # Raw base64 JPEG (no data:image prefix)
    min_blur: Optional[float] = None


class BurstRequest(BaseModel):
    images_b64: List[str]   # List of Raw base64 JPEG (no data:image prefix)
    min_blur: Optional[float] = None


class ExtractResponse(BaseModel):
    embedding_b64: str      # base64(float32 bytes) — 512-dim raw embedding
    quality: float
    meta: dict


class GalleryItem(BaseModel):
    student_id: int
    embedding_b64: str      # base64(float32 bytes) — plain (backend đã decrypt)


class IdentifyRequest(BaseModel):
    probe_b64: str          # base64(float32 bytes) of probe embedding
    gallery: List[GalleryItem]
    threshold: Optional[float] = None


class IdentifyResponse(BaseModel):
    matched: bool
    student_id: Optional[int]
    confidence: float
    top_matches: List[dict]


# ── Encoding helpers ──────────────────────────────────────────────────────────
def _emb_to_b64(emb: np.ndarray) -> str:
    return base64.b64encode(emb.astype(np.float32).tobytes()).decode()


def _b64_to_emb(b64: str) -> np.ndarray:
    try:
        raw = base64.b64decode(b64)
        return np.frombuffer(raw, dtype=np.float32)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid embedding_b64")


# ── Endpoints ─────────────────────────────────────────────────────────────────
@router.post("/extract", response_model=ExtractResponse)
async def extract_endpoint(
    body: ExtractRequest,
    x_service_key: Optional[str] = Header(default=None, alias="X-Service-Key"),
):
    """
    Nhận JPEG image (base64), trả về:
    - embedding_b64: ArcFace 512-dim embedding (plain, chưa mã hóa)
    - quality: điểm chất lượng 0.0 – 1.0
    - meta: bbox, det_score, blur_variance, image_size

    Backend sẽ nhận embedding này rồi AES-encrypt trước khi lưu DB.
    """
    _verify_service_key(x_service_key)

    try:
        img_bytes = base64.b64decode(body.image_b64)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid image_b64 — cannot base64-decode")

    try:
        emb, quality, meta = extract_embedding(img_bytes, min_blur=body.min_blur)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.exception("Unexpected error in extract_embedding")
        raise HTTPException(status_code=500, detail=f"AI inference error: {e}")

    return ExtractResponse(
        embedding_b64=_emb_to_b64(emb),
        quality=quality,
        meta=meta,
    )


@router.post("/identify", response_model=IdentifyResponse)
async def identify_endpoint(
    body: IdentifyRequest,
    x_service_key: Optional[str] = Header(default=None, alias="X-Service-Key"),
):
    """
    Nhận probe embedding + gallery (plain embeddings đã decrypt từ DB),
    trả về kết quả nhận diện: matched, student_id, confidence, top_matches.

    Quan trọng: Backend chịu trách nhiệm decrypt AES trước khi gửi gallery sang đây.
    AI service không biết AES key — chỉ làm toán cosine similarity.
    """
    _verify_service_key(x_service_key)

    probe = _b64_to_emb(body.probe_b64)
    if probe.shape[0] != 512:
        raise HTTPException(status_code=400, detail=f"probe must be 512-dim, got {probe.shape[0]}")

    gallery: List[Tuple[int, np.ndarray]] = []
    for item in body.gallery:
        emb = _b64_to_emb(item.embedding_b64)
        if emb.shape[0] != 512:
            raise HTTPException(
                status_code=400,
                detail=f"gallery student_id={item.student_id} embedding must be 512-dim"
            )
        gallery.append((item.student_id, emb))

    result = batch_identify(probe, gallery, threshold=body.threshold)
    return IdentifyResponse(**result)


@router.post("/extract-burst", response_model=ExtractResponse)
async def extract_burst_endpoint(
    body: BurstRequest,
    x_service_key: Optional[str] = Header(default=None, alias="X-Service-Key"),
):
    """
    Nhận mảng JPEG images (base64) để kiểm tra chớp mắt (Liveness).
    Nếu chớp mắt thành công, trả về embedding của khung hình phù hợp nhất.
    """
    _verify_service_key(x_service_key)

    try:
        emb, quality, meta = extract_sequence(body.images_b64, min_blur=body.min_blur)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.exception("Unexpected error in extract_sequence")
        raise HTTPException(status_code=500, detail=f"AI inference error: {e}")

    return ExtractResponse(
        embedding_b64=_emb_to_b64(emb),
        quality=quality,
        meta=meta,
    )
