"""
FaceModel — InsightFace wrapper cho AI Inference Service.

Trách nhiệm:
  1. Lazy-load InsightFace buffalo_sc một lần duy nhất (singleton)
  2. extract_embedding(): JPEG bytes → (embedding 512-dim, quality score, bbox)
  3. batch_identify(): probe embedding + gallery → (student_id match, confidence)

Không làm: mã hóa, DB, auth — đó là việc của backend.
"""
import io
import logging
import numpy as np
from typing import Optional, Tuple, List

import cv2
from PIL import Image

from app.config import settings

logger = logging.getLogger(__name__)


# ── Singleton ─────────────────────────────────────────────────────────────────
_face_app = None


def get_face_app():
    """Lazy-load InsightFace — chỉ khởi tạo 1 lần, thread-safe với GIL Python."""
    global _face_app
    if _face_app is None:
        import insightface
        logger.info(f"Loading InsightFace model '{settings.MODEL_NAME}' ...")
        _face_app = insightface.app.FaceAnalysis(
            name=settings.MODEL_NAME,
            root=settings.MODEL_STORAGE_PATH,
            providers=["CPUExecutionProvider"],
        )
        _face_app.prepare(ctx_id=0, det_size=(settings.DET_SIZE, settings.DET_SIZE))
        logger.info("InsightFace loaded ✅")
    return _face_app


# ── Helpers ───────────────────────────────────────────────────────────────────
def _decode_image(img_bytes: bytes) -> np.ndarray:
    """JPEG/PNG bytes → BGR ndarray (OpenCV format)."""
    arr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Cannot decode image — invalid bytes or unsupported format")
    return img


def _blur_score(gray: np.ndarray) -> float:
    """Laplacian variance — số lớn = ảnh sắc nét."""
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity giữa 2 vectors đã L2-normalize."""
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))


# ── Core functions ────────────────────────────────────────────────────────────
def extract_embedding(
    img_bytes: bytes,
    min_blur: Optional[float] = None,
) -> Tuple[np.ndarray, float, dict]:
    """
    Nhận JPEG bytes, trả về (embedding 512-dim, quality_score, metadata).

    Raise ValueError nếu:
      - Không detect được khuôn mặt
      - Ảnh quá mờ (Laplacian variance < min_blur)
      - Khuôn mặt quá nhỏ so với kích thước ảnh

    Parameters
    ----------
    img_bytes : bytes   raw JPEG/PNG data
    min_blur  : float   ngưỡng Laplacian variance (default từ config)

    Returns
    -------
    embedding : np.ndarray  shape (512,), float32, L2-normalised
    quality   : float       điểm 0–1 (kết hợp blur + độ tin cậy detection)
    meta      : dict        bbox, det_score, image_size
    """
    min_blur = min_blur if min_blur is not None else settings.MIN_BLUR_VAR

    bgr = _decode_image(img_bytes)
    h, w = bgr.shape[:2]
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    # Blur check
    blur_var = _blur_score(gray)
    if blur_var < min_blur:
        raise ValueError(f"Image too blurry (Laplacian={blur_var:.1f} < {min_blur})")

    app = get_face_app()
    faces = app.get(bgr)

    if not faces:
        raise ValueError("No face detected in image")

    # Chọn khuôn mặt lớn nhất
    face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))

    # Kiểm tra kích thước khuôn mặt so với ảnh
    x1, y1, x2, y2 = face.bbox
    face_area = (x2 - x1) * (y2 - y1)
    img_area = w * h
    if face_area / img_area < settings.MIN_FACE_RATIO:
        raise ValueError(
            f"Face too small ({face_area/img_area*100:.1f}% of image, min {settings.MIN_FACE_RATIO*100:.0f}%)"
        )

    emb = face.normed_embedding.astype(np.float32)  # 512-dim, already L2-normalised

    # Quality score: kết hợp det_score + blur (normalize về 0-1)
    det_score = float(face.det_score)
    blur_norm = min(1.0, blur_var / 500.0)  # 500 = ảnh rất sắc
    quality = round(0.6 * det_score + 0.4 * blur_norm, 4)

    # ── Head pose estimation ──────────────────────────────────────────────────
    # InsightFace computes pose from 5-point landmarks via solvePnP.
    # face.pose = [pitch, yaw, roll] in degrees.
    #   yaw  > 0 → head turned to subject's RIGHT  (camera sees left cheek)
    #   yaw  < 0 → head turned to subject's LEFT   (camera sees right cheek)
    #   pitch> 0 → head tilted DOWN (chin down)
    #   pitch< 0 → head tilted UP   (chin up)
    yaw: Optional[float] = None
    pitch: Optional[float] = None
    roll: Optional[float] = None
    if hasattr(face, "pose") and face.pose is not None:
        pose = face.pose  # shape (3,) or list
        pitch = round(float(pose[0]), 2)
        yaw   = round(float(pose[1]), 2)
        roll  = round(float(pose[2]), 2)

    meta = {
        "bbox": [float(x) for x in face.bbox],
        "det_score": det_score,
        "blur_variance": round(blur_var, 2),
        "image_size": [w, h],
        "face_area_ratio": round(face_area / img_area, 4),
        # Head pose angles in degrees (None if model does not support pose)
        "yaw": yaw,
        "pitch": pitch,
        "roll": roll,
    }

    return emb, quality, meta


def batch_identify(
    probe: np.ndarray,
    gallery: List[Tuple[int, np.ndarray]],
    threshold: Optional[float] = None,
) -> dict:
    """
    So sánh probe embedding với gallery — trả về kết quả nhận diện.

    Parameters
    ----------
    probe   : np.ndarray            shape (512,) embedding cần nhận diện
    gallery : List[(student_id, embedding)]   danh sách embeddings từ DB
    threshold : float               ngưỡng cosine similarity (default 0.65)

    Returns
    -------
    dict với keys:
      matched    : bool
      student_id : int | None
      confidence : float
      top_matches: list[dict]  (top-3 cho debug)
    """
    threshold = threshold if threshold is not None else settings.COSINE_THRESHOLD

    if not gallery:
        return {"matched": False, "student_id": None, "confidence": 0.0, "top_matches": []}

    scores = []
    for student_id, gallery_emb in gallery:
        sim = _cosine_similarity(probe, gallery_emb)
        scores.append((student_id, sim))

    # Sắp xếp theo confidence giảm dần
    scores.sort(key=lambda x: x[1], reverse=True)

    best_id, best_score = scores[0]
    matched = best_score >= threshold

    top_matches = [
        {"student_id": sid, "confidence": round(sim, 4)}
        for sid, sim in scores[:3]
    ]

    return {
        "matched": matched,
        "student_id": int(best_id) if matched else None,
        "confidence": round(best_score, 4),
        "top_matches": top_matches,
    }
