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


# ── Head pose from 5-point keypoints (geometric method) ─────────────────────
#
# InsightFace 5-point keypoints order:
#   0: left_eye, 1: right_eye, 2: nose_tip, 3: left_mouth, 4: right_mouth
# "left/right" = from the SUBJECT's perspective.
#   In a raw (unmirrored) camera frame:
#     left_eye → appears on the RIGHT side of the image
#     right_eye → appears on the LEFT side of the image
#
# Geometric yaw/pitch estimation (stable, no solvePnP 180° ambiguity):
#   yaw  ∝ horizontal asymmetry between nose and the eye midpoint
#   pitch ∝ vertical position of nose between eye-line and mouth-line


def _estimate_pose_geometric(
    kps: np.ndarray,
    img_w: int,
    img_h: int,
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """
    Estimate head yaw/pitch from 5 facial keypoints using geometry only.
    No solvePnP — avoids 180° disambiguation issues entirely.

    Yaw convention (raw camera frame, no mirror):
      yaw > 0  → nose shifted LEFT in image  → subject turned to THEIR right
      yaw < 0  → nose shifted RIGHT in image → subject turned to THEIR left
    Pitch convention:
      pitch > 0 → chin down (nose below midline)
      pitch < 0 → chin up   (nose above midline)

    Returns (yaw_deg, pitch_deg, None) or (None, None, None) on failure.
    """
    try:
        kps = np.array(kps, dtype=np.float64)
        if kps.shape[0] < 5:
            return None, None, None

        left_eye   = kps[0]   # subject's left  = image right
        right_eye  = kps[1]   # subject's right = image left
        nose       = kps[2]
        left_mouth = kps[3]
        right_mouth= kps[4]

        # ── Yaw ──────────────────────────────────────────────────────────────
        # Eye midpoint horizontal position
        eye_mid_x = (left_eye[0] + right_eye[0]) / 2.0
        # Mouth midpoint horizontal position
        mouth_mid_x = (left_mouth[0] + right_mouth[0]) / 2.0
        # Interocular distance (pixel width between the two eyes)
        eye_dist = abs(left_eye[0] - right_eye[0]) + 1e-6

        # Horizontal offset of nose from the eye midpoint, normalized by eye_dist
        # When face looks straight: nose_x ≈ eye_mid_x → offset ≈ 0
        # When face turns right (subject): nose moves toward right_eye (image LEFT)
        #   → left_eye moves right, right_eye moves left-ish, nose moves left
        #   → (eye_mid_x - nose_x) > 0 → yaw_raw > 0 (turning to their right)
        yaw_raw = (eye_mid_x - nose[0]) / eye_dist
        # Scale to degrees: empirically, 0.5 offset ≈ 45°
        yaw_deg = float(np.clip(yaw_raw * 90.0, -90.0, 90.0))

        # ── Pitch ─────────────────────────────────────────────────────────────
        # Vertical midpoint of eyes and mouth
        eye_mid_y   = (left_eye[1] + right_eye[1]) / 2.0
        mouth_mid_y = (left_mouth[1] + right_mouth[1]) / 2.0
        face_height = abs(mouth_mid_y - eye_mid_y) + 1e-6

        # Where is the nose's Y relative to the eye-mouth vertical span?
        # Neutral: nose_y ≈ eye_mid_y + 0.5 * face_height → t_raw ≈ 0.5
        t_raw = (nose[1] - eye_mid_y) / face_height
        # Shift so that 0.5 maps to 0° pitch
        # t_raw < 0.5 → nose above midline → chin up → pitch < 0
        # t_raw > 0.5 → nose below midline → chin down → pitch > 0
        pitch_deg = float(np.clip((t_raw - 0.5) * 120.0, -90.0, 90.0))

        return round(yaw_deg, 2), round(pitch_deg, 2), None

    except Exception as exc:
        logger.debug("geometric pose failed: %s", exc)
        return None, None, None


def _estimate_pose_solvepnp(
    kps: np.ndarray,
    img_w: int,
    img_h: int,
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """Alias kept for backward compat — delegates to geometric method."""
    return _estimate_pose_geometric(kps, img_w, img_h)


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
    logger.warning("[BLUR] image=%dx%d blur_var=%.1f threshold=%.1f %s",
                   w, h, blur_var, min_blur, "PASS" if blur_var >= min_blur else "FAIL")
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

    # ── Head pose estimation via solvePnP ─────────────────────────────────────
    # buffalo_sc does NOT include a pose model (1k3d68.onnx), so face.pose is
    # always None.  We compute yaw/pitch/roll ourselves using cv2.solvePnP with
    # the 5 facial keypoints (face.kps) that the detection model always provides.
    #
    # Coordinate convention (camera-centric, raw webcam frame):
    #   +X = image RIGHT   +Y = image DOWN   +Z = depth (away from camera)
    #   Subject's LEFT eye appears on the image RIGHT → placed at +X in 3D model.
    #   Subject's RIGHT eye appears on the image LEFT → placed at -X in 3D model.
    #
    # Sign convention for angles:
    #   yaw   > 0 → face points to camera's RIGHT  = subject's physical LEFT
    #   yaw   < 0 → face points to camera's LEFT   = subject's physical RIGHT
    #   pitch > 0 → face tilts DOWN (chin toward chest)
    #   pitch < 0 → face tilts UP   (chin raised)
    #
    # The enrollment frontend displays the video with CSS scaleX(-1) (mirror),
    # so from the user's point of view:
    #   "Turn LEFT"  → physical LEFT → yaw > 0 in raw frame
    #   "Turn RIGHT" → physical RIGHT → yaw < 0 in raw frame
    yaw: Optional[float] = None
    pitch: Optional[float] = None
    roll: Optional[float] = None

    # Prefer native pose if model supports it (buffalo_l / antelopev2)
    if hasattr(face, "pose") and face.pose is not None:
        pose = face.pose
        pitch = round(float(pose[0]), 2)
        yaw   = round(float(pose[1]), 2)
        roll  = round(float(pose[2]), 2)
    elif hasattr(face, "kps") and face.kps is not None and len(face.kps) >= 5:
        yaw, pitch, roll = _estimate_pose_solvepnp(face.kps, w, h)

    meta = {
        "bbox": [float(x) for x in face.bbox],
        "det_score": det_score,
        "blur_variance": round(blur_var, 2),
        "image_size": [w, h],
        "face_area_ratio": round(face_area / img_area, 4),
        # Head pose angles in degrees
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
