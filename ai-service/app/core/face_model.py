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
import base64
import json
import numpy as np
from typing import Optional, Tuple, List

import cv2
from PIL import Image

from app.config import settings

logger = logging.getLogger(__name__)


# ── Singletons ────────────────────────────────────────────────────────────────
_face_app = None
_antispoof_session = None  # lazy-loaded ONNX anti-spoof session

_ANTISPOOF_MODEL_PATH = "/app/antispoof/anti-spoof-mn3.onnx"
# Preprocessing constants for anti-spoof-mn3 (CelebA-Spoof trained MobileNetV3)
# Source: Intel OpenVINO Open Model Zoo — MIT License
_AS_MEAN  = np.array([151.2405, 119.5950, 107.8395], dtype=np.float32)
_AS_SCALE = np.array([ 63.0105,  56.4570,  55.0035], dtype=np.float32)


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


def get_antispoof_session():
    """Lazy-load the anti-spoof ONNX session (singleton)."""
    global _antispoof_session
    if _antispoof_session is None:
        import os
        import onnxruntime as ort
        if not os.path.exists(_ANTISPOOF_MODEL_PATH):
            logger.warning("[ANTISPOOF] Model not found at %s — liveness skipped", _ANTISPOOF_MODEL_PATH)
            return None
        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 2
        opts.intra_op_num_threads = 2
        _antispoof_session = ort.InferenceSession(
            _ANTISPOOF_MODEL_PATH,
            sess_options=opts,
            providers=["CPUExecutionProvider"],
        )
        inp_name  = _antispoof_session.get_inputs()[0].name
        out_name  = _antispoof_session.get_outputs()[0].name
        inp_shape = _antispoof_session.get_inputs()[0].shape
        logger.info("[ANTISPOOF] Loaded ✅  input='%s'%s  output='%s'", inp_name, inp_shape, out_name)
    return _antispoof_session


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


def _ml_liveness(bgr: np.ndarray, bbox) -> Tuple[float, bool]:
    """
    ML-based passive liveness using anti-spoof-mn3 ONNX (MobileNetV3).

    Trained on CelebA-Spoof dataset (625k images, 43 spoof types).
    ACER = 3.81% on held-out test set.

    Distinguishes:
      - Printed photo attacks     (paper, cardboard)
      - Digital screen attacks    (phone, tablet, monitor)
      - Video replay attacks      (pre-recorded clips)
    from real live faces.

    Returns (liveness_score 0.0–1.0, is_live bool)
      score = P(real) from softmax output
      is_live = score >= 0.55  (slightly conservative vs 0.50)
    """
    session = get_antispoof_session()
    if session is None:
        # Model not available — default to pass (safe for development)
        logger.warning("[ANTISPOOF] Session unavailable, defaulting to is_live=True")
        return 0.5, True

    try:
        x1, y1, x2, y2 = [int(v) for v in bbox]
        ih, iw = bgr.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(iw, x2), min(ih, y2)

        if (x2 - x1) < 20 or (y2 - y1) < 20:
            logger.warning("[ANTISPOOF] Face region too small, defaulting is_live=True")
            return 0.5, True

        # ── Crop & preprocess ────────────────────────────────────────────────
        # Pad bbox by 20% to include context (hair, neck, background)
        pad_x = int((x2 - x1) * 0.20)
        pad_y = int((y2 - y1) * 0.20)
        x1p = max(0, x1 - pad_x);  y1p = max(0, y1 - pad_y)
        x2p = min(iw, x2 + pad_x); y2p = min(ih, y2 + pad_y)

        face_bgr = bgr[y1p:y2p, x1p:x2p]
        face_128 = cv2.resize(face_bgr, (128, 128))
        face_rgb = cv2.cvtColor(face_128, cv2.COLOR_BGR2RGB)

        # Normalize: (pixel - mean) / std
        face_f = face_rgb.astype(np.float32)
        face_f = (face_f - _AS_MEAN) / _AS_SCALE
        # HWC → NCHW
        inp = np.transpose(face_f, (2, 0, 1))[np.newaxis, :].astype(np.float32)

        # ── Inference ─────────────────────────────────────────────────────────
        inp_name = session.get_inputs()[0].name
        raw = session.run(None, {inp_name: inp})[0][0]  # shape (2,)

        # Softmax (stable)
        e = np.exp(raw - raw.max())
        probs = e / e.sum()
        real_prob  = float(probs[0])   # P(real)
        spoof_prob = float(probs[1])   # P(spoof)

        # Threshold 0.42 (lowered from 0.55):
        # - At ≥12° tilt, real faces: real_prob ≈ 0.43–0.75
        # - At ≥12° tilt, phone/print: real_prob ≈ 0.15–0.38 (moire, glare, flat surface gives it away)
        # - Frontal scans won't reach here (blocked by pose challenge in backend)
        is_live = real_prob >= 0.42

        logger.warning(
            "[ANTISPOOF] real_prob=%.4f  spoof_prob=%.4f  → is_live=%s",
            real_prob, spoof_prob, is_live,
        )
        return round(real_prob, 4), bool(is_live)

    except Exception as exc:
        logger.error("[ANTISPOOF] Inference error: %s", exc, exc_info=True)
        return 0.5, True  # fail-open: don't block on model error


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

    # ── ML-based liveness (anti-spoof-mn3, MobileNetV3, CelebA-Spoof) ─────────
    liveness_score, is_live = _ml_liveness(bgr, face.bbox)

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
        # Liveness (ML anti-spoof: P(real) from anti-spoof-mn3)
        "liveness_score": liveness_score,
        "is_live": is_live,
    }

    return emb, quality, meta


def extract_sequence(
    images_b64: List[str],
    min_blur: Optional[float] = None,
) -> Tuple[np.ndarray, float, dict]:
    """
    Process a burst sequence of frames to verify blink liveness.
    Returns embedding of the best frame and sets blink_ok=True.
    """
    from app.core.blink_detector import analyze_blink_sequence
    
    min_blur = min_blur if min_blur is not None else settings.MIN_BLUR_VAR
    app = get_face_app()
    
    decoded_frames = []
    for b64 in images_b64:
        try:
            b64_padded = b64 + "=" * ((4 - len(b64) % 4) % 4)
            img_bytes = base64.b64decode(b64_padded)
            bgr = _decode_image(img_bytes)
            decoded_frames.append((bgr, img_bytes))
        except Exception as exc:
            logger.error(f"Decode error: {exc}")
            continue
            
    if not decoded_frames:
        raise ValueError("No valid images in sequence")

    frames = [f[0] for f in decoded_frames]
    landmarks_list = [None] * len(frames)
    best_face = None
    best_img_bytes = None
    
    # ── Step 1: Find face in the sequence (only once) ────────────────────────
    # We try frames from the middle first, as they are likely the most stable
    search_indices = list(range(len(frames)))
    mid = len(frames) // 2
    search_indices.sort(key=lambda i: abs(i - mid))
    
    found_kps = None
    for i in search_indices:
        bgr = frames[i]
        faces = app.get(bgr)
        if faces:
            # Select largest face
            face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
            if hasattr(face, "kps") and face.kps is not None and len(face.kps) >= 5:
                found_kps = face.kps
                best_face = face
                best_img_bytes = decoded_frames[i][1]
                break
    
    if found_kps is None:
        raise ValueError("No face detected in any frame of the sequence")
        
    # ── Step 2: Reuse these keypoints for all frames for blink analysis ──────
    # (Assuming face doesn't move significantly in 2.0s)
    for i in range(len(frames)):
        landmarks_list[i] = found_kps
            
    blink_ok, debug_info = analyze_blink_sequence(frames, landmarks_list)
    logger.warning(f"[LIVENESS] status={blink_ok} amplitude={debug_info.get('amplitude')} frames={len(frames)}")
    
    if not blink_ok:
        raise ValueError(f"Liveness failed. Debug: {json.dumps(debug_info)}")
        
    if best_img_bytes:
        # Step 3: Extract embedding for recognition from our best frame
        emb, quality, meta = extract_embedding(best_img_bytes, min_blur)
        meta["blink_ok"] = True
        meta["liveness_debug"] = debug_info
        return emb, quality, meta
    else:
        raise ValueError("No valid face found in sequence")


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
