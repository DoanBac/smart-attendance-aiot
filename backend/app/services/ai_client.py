"""
AI Service HTTP Client — backend giao tiếp với ai-service (port 9000).

Toàn bộ việc gọi /api/v1/extract và /api/v1/identify qua đây.
Mã hóa AES vẫn xảy ra ở backend (ai-service không biết AES key).
"""
import logging
from typing import Optional, List, Tuple

import httpx
import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)

# Timeout: 30s (InsightFace inference ~200ms trên CPU, nhưng cold-start lần đầu lâu hơn)
_HTTP_TIMEOUT = 30.0


def _headers() -> dict:
    return {"X-Service-Key": settings.AI_SERVICE_SECRET_KEY}


def _emb_to_b64(emb: np.ndarray) -> str:
    import base64
    return base64.b64encode(emb.astype(np.float32).tobytes()).decode()


def _b64_to_emb(b64: str) -> np.ndarray:
    import base64
    raw = base64.b64decode(b64)
    return np.frombuffer(raw, dtype=np.float32).copy()


async def ai_extract_embedding(
    image_b64: str,
    min_blur: Optional[float] = None,
) -> Tuple[np.ndarray, float, dict]:
    """
    Gọi POST /api/v1/extract trên ai-service.

    Parameters
    ----------
    image_b64 : str   Raw base64 JPEG (không có tiền tố data:image/...)
    min_blur  : float Ngưỡng blur (None → dùng default của ai-service)

    Returns
    -------
    embedding : np.ndarray  512-dim float32
    quality   : float
    meta      : dict        bbox, det_score, ...

    Raise
    -----
    ValueError  nếu ai-service trả 422 (no face / too blurry)
    RuntimeError nếu ai-service không available hoặc lỗi 5xx
    """
    payload: dict = {"image_b64": image_b64}
    if min_blur is not None:
        payload["min_blur"] = min_blur

    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.post(
                f"{settings.AI_SERVICE_URL}/api/v1/extract",
                json=payload,
                headers=_headers(),
            )
    except httpx.ConnectError:
        raise RuntimeError(
            "Cannot connect to AI service. "
            f"Make sure ai-service is running on {settings.AI_SERVICE_URL}"
        )
    except httpx.TimeoutException:
        raise RuntimeError("AI service timed out during embedding extraction")

    if resp.status_code == 422:
        detail = resp.json().get("detail", "Face extraction failed")
        raise ValueError(detail)

    if resp.status_code != 200:
        raise RuntimeError(f"AI service error {resp.status_code}: {resp.text}")

    data = resp.json()
    embedding = _b64_to_emb(data["embedding_b64"])
    return embedding, data["quality"], data["meta"]


async def ai_identify(
    probe: np.ndarray,
    gallery: List[Tuple],   # (student_id: any, plain_embedding: np.ndarray)
    threshold: Optional[float] = None,
) -> dict:
    """
    Gọi POST /api/v1/identify trên ai-service.

    Backend đã decrypt AES → gửi plain embeddings sang đây.
    ai-service chỉ làm cosine similarity, không biết AES key.

    Returns
    -------
    dict: { matched, student_id, confidence, top_matches }
    """
    gallery_items = [
        {"student_id": str(sid), "embedding_b64": _emb_to_b64(emb)}
        for sid, emb in gallery
    ]

    payload: dict = {
        "probe_b64": _emb_to_b64(probe),
        "gallery": gallery_items,
    }
    if threshold is not None:
        payload["threshold"] = threshold

    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.post(
                f"{settings.AI_SERVICE_URL}/api/v1/identify",
                json=payload,
                headers=_headers(),
            )
    except httpx.ConnectError:
        raise RuntimeError(
            f"Cannot connect to AI service ({settings.AI_SERVICE_URL})"
        )
    except httpx.TimeoutException:
        raise RuntimeError("AI service timed out during identify")

    if resp.status_code != 200:
        raise RuntimeError(f"AI service error {resp.status_code}: {resp.text}")

    return resp.json()
