"""
Cloud-side face service theo Paper:
- Detection: RetinaFace ONNX (InsightFace)
- Embedding: ArcFace ONNX 512-dim
- Encryption: AES-256-GCM
- Enrollment: 5 góc weighted average → 1 master embedding
- Verify: Cosine Similarity ≥ 0.65
"""
import os
import io
import base64
import logging
import numpy as np
from typing import Tuple, List, Optional

import cv2
from PIL import Image
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.models.student import Student

logger = logging.getLogger(__name__)


# ── InsightFace lazy init ─────────────────────────────────────────────────────
_face_app = None

def get_face_app():
    global _face_app
    if _face_app is None:
        try:
            import insightface
            _face_app = insightface.app.FaceAnalysis(
                name="buffalo_sc",
                root=settings.MODEL_STORAGE_PATH,
                providers=["CPUExecutionProvider"]
            )
            _face_app.prepare(ctx_id=0, det_size=(640, 640))
            logger.info("InsightFace loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load InsightFace: {e}")
            raise
    return _face_app


# ══════════════════════════════════════════════════════════════════════
#  Crypto helpers - AES-256-GCM (Secure Enclave equivalent)
# ══════════════════════════════════════════════════════════════════════
def _get_aes_key() -> bytes:
    return bytes.fromhex(settings.AES_KEY)

def encrypt_embedding(embedding: np.ndarray) -> bytes:
    """AES-256-GCM: [12B nonce][ciphertext+16B tag]"""
    raw   = embedding.astype(np.float32).tobytes()
    nonce = os.urandom(12)
    ct    = AESGCM(_get_aes_key()).encrypt(nonce, raw, None)
    return nonce + ct

def decrypt_embedding(data: bytes) -> np.ndarray:
    raw = AESGCM(_get_aes_key()).decrypt(data[:12], data[12:], None)
    return np.frombuffer(raw, dtype=np.float32).copy()

def cosine_similarity(v1: np.ndarray, v2: np.ndarray) -> float:
    """Cosine similarity - Paper Section 5.3"""
    v1 = v1 / (np.linalg.norm(v1) + 1e-10)
    v2 = v2 / (np.linalg.norm(v2) + 1e-10)
    return float(np.dot(v1, v2))


# ══════════════════════════════════════════════════════════════════════
#  Liveness Detection - Paper Section 4
# ══════════════════════════════════════════════════════════════════════
class LivenessChecker:
    """
    Liveness Detection 3 tầng:
    Tầng 1: Blink Detection (EAR)       - 40%
    Tầng 2: Head Pose Estimation (PnP)  - 35%
    Tầng 3: Depth score                 - 25%
    """

    EAR_THRESHOLD = 0.25

    FACE_3D_MODEL = np.array([
        [0.0,    0.0,    0.0   ],  # Mũi
        [0.0,   -330.0, -65.0 ],  # Cằm
        [-225.0, 170.0, -135.0],  # Khóe mắt trái
        [225.0,  170.0, -135.0],  # Khóe mắt phải
        [-150.0,-150.0, -125.0],  # Khóe miệng trái
        [150.0, -150.0, -125.0],  # Khóe miệng phải
    ], dtype=np.float64)

    def compute_ear(self, eye_landmarks: np.ndarray) -> float:
        """EAR = (||p2-p6|| + ||p3-p5||) / (2 × ||p1-p4||)"""
        p1, p2, p3, p4, p5, p6 = eye_landmarks
        v1 = np.linalg.norm(p2 - p6)
        v2 = np.linalg.norm(p3 - p5)
        h  = np.linalg.norm(p1 - p4)
        return (v1 + v2) / (2.0 * h + 1e-6)

    def check_blink(self, ear_history: List[float]) -> bool:
        """Pattern: cao → thấp → cao = 1 lần chớp mắt"""
        if len(ear_history) < 3:
            return False
        for i in range(1, len(ear_history) - 1):
            if (ear_history[i]     < self.EAR_THRESHOLD and
                ear_history[i - 1] >= self.EAR_THRESHOLD and
                ear_history[i + 1] >= self.EAR_THRESHOLD):
                return True
        return False

    def estimate_head_pose(
        self, landmarks_2d: np.ndarray, img_w: int, img_h: int
    ) -> Tuple[float, float, float]:
        """PnP → yaw, pitch, roll"""
        focal  = float(img_w)
        cam_mat = np.array([
            [focal, 0, img_w / 2],
            [0, focal, img_h / 2],
            [0, 0, 1],
        ], dtype=np.float64)
        ok, rvec, _ = cv2.solvePnP(
            self.FACE_3D_MODEL,
            landmarks_2d.astype(np.float64),
            cam_mat,
            np.zeros((4, 1)),
            flags=cv2.SOLVEPNP_ITERATIVE,
        )
        if not ok:
            return 0.0, 0.0, 0.0
        rmat, _ = cv2.Rodrigues(rvec)
        angles, *_ = cv2.RQDecomp3x3(rmat)
        return float(angles[1]), float(angles[0]), float(angles[2])

    def check_head_movement(
        self, pose_history: List[Tuple[float, float, float]], angle: str
    ) -> bool:
        if len(pose_history) < 5:
            return False
        yaws   = [p[0] for p in pose_history]
        pitchs = [p[1] for p in pose_history]
        return (
            (angle == "left"  and max(yaws)   >  20) or
            (angle == "right" and min(yaws)   < -20) or
            (angle == "up"    and min(pitchs) < -15) or
            (angle == "down"  and max(pitchs) >  15)
        )

    def estimate_liveness_score(
        self, blink_detected: bool, head_moved: bool, depth_score: float = 1.0
    ) -> float:
        score = 0.0
        if blink_detected: score += 0.40
        if head_moved:     score += 0.35
        score += depth_score * 0.25
        return min(score, 1.0)


# ══════════════════════════════════════════════════════════════════════
#  FaceService - Pipeline chính theo Paper Section 5
# ══════════════════════════════════════════════════════════════════════
class FaceService:
    """
    Enrollment pipeline:
      5 góc ảnh → RetinaFace detect → ArcFace 512-dim
      → weighted average → AES-256-GCM encrypt → DB

    Verify pipeline:
      1 ảnh → ArcFace 512-dim → cosine similarity ≥ 0.65 → MATCH
    """

    ANGLE_INSTRUCTIONS = {
        "center": "Nhìn thẳng vào camera",
        "left":   "Từ từ xoay mặt sang TRÁI (~30°)",
        "right":  "Từ từ xoay mặt sang PHẢI (~30°)",
        "up":     "Từ từ ngẩng mặt lên TRÊN (~20°)",
        "down":   "Từ từ cúi mặt xuống DƯỚI (~20°)",
    }

    ANGLE_WEIGHTS = {
        "center": 2.0,
        "left":   1.0,
        "right":  1.0,
        "up":     0.8,
        "down":   0.8,
    }

    def __init__(self):
        self._face_app = None
        self._liveness = LivenessChecker()

    # ---------------------------------------------------------------- #
    #  Load InsightFace (lazy)                                          #
    # ---------------------------------------------------------------- #
    def _get_app(self):
        if self._face_app is None:
            try:
                from insightface.app import FaceAnalysis
                import onnxruntime as ort

                opts = ort.SessionOptions()
                opts.intra_op_num_threads = 4
                opts.graph_optimization_level = (
                    ort.GraphOptimizationLevel.ORT_ENABLE_ALL
                )

                self._face_app = FaceAnalysis(
                    name      = "buffalo_sc",
                    root      = settings.MODEL_STORAGE_PATH,
                    providers = ["CPUExecutionProvider"],
                )
                # 320×320 tối ưu RPi - Paper Section 8.2
                self._face_app.prepare(ctx_id=0, det_size=(320, 320))
                logger.info("✅ InsightFace: RetinaFace + ArcFace loaded")
            except Exception as e:
                logger.error(f"❌ InsightFace load failed: {e}")
                raise RuntimeError(f"Face engine unavailable: {e}")
        return self._face_app

    # ---------------------------------------------------------------- #
    #  Blur check - Paper Section 3.2                                   #
    # ---------------------------------------------------------------- #
    def _check_blur(self, img_np: np.ndarray) -> float:
        gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())

    # ---------------------------------------------------------------- #
    #  Core: Image → ArcFace Embedding                                  #
    # ---------------------------------------------------------------- #
    def extract_embedding(
        self,
        image_bytes: bytes,
        angle: str = "center",
        min_blur: float = 100.0,
    ) -> Tuple[np.ndarray, float, dict]:
        """
        RetinaFace detect → ArcFace 512-dim embedding
        Returns: (l2_normalized_embedding, quality_score, meta)
        """
        try:
            img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            img_np  = np.array(img_pil)
        except Exception:
            raise ValueError("File ảnh không hợp lệ")

        blur = self._check_blur(img_np)
        if angle == "center" and blur < min_blur:
            raise ValueError(
                f"Ảnh bị mờ (score={blur:.1f}). Đảm bảo đủ sáng và giữ yên camera"
            )

        img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
        faces   = self._get_app().get(img_bgr)

        if len(faces) == 0:
            raise ValueError(
                f"Không phát hiện khuôn mặt ở góc '{angle}'. "
                "Đảm bảo đủ sáng, nhìn vào camera"
            )
        if len(faces) > 1:
            raise ValueError(
                f"Phát hiện {len(faces)} khuôn mặt. Chỉ 1 người khi đăng ký"
            )

        face     = faces[0]
        quality  = float(face.det_score)
        min_conf = 0.5 if angle == "center" else 0.35

        if quality < min_conf:
            raise ValueError(
                f"Góc '{angle}': chất lượng thấp ({quality:.2f}). Cần đủ sáng hơn"
            )

        embedding = face.normed_embedding.copy()   # 512-dim, đã L2 normalize

        meta = {
            "quality_score": quality,
            "blur_score":    round(blur, 1),
            "bbox":          [round(x, 1) for x in face.bbox.tolist()],
            "embedding_dim": len(embedding),
            "landmarks":     face.kps.tolist() if face.kps is not None else [],
        }

        logger.info(f"[EXTRACT] angle={angle} det={quality:.3f} blur={blur:.1f}")
        return embedding, quality, meta

    # ---------------------------------------------------------------- #
    #  Fuse 5 góc → 1 master embedding - Paper Section 3.1             #
    # ---------------------------------------------------------------- #
    def fuse_embeddings(
        self,
        embeddings: List[np.ndarray],
        angles:     List[str],
        qualities:  List[float],
    ) -> Tuple[np.ndarray, float]:
        weighted_sum = np.zeros_like(embeddings[0])
        total_w      = 0.0

        for emb, angle, qual in zip(embeddings, angles, qualities):
            w             = self.ANGLE_WEIGHTS.get(angle, 1.0) * qual
            weighted_sum += w * emb
            total_w      += w

        master = weighted_sum / total_w
        norm   = np.linalg.norm(master)
        if norm > 0:
            master = master / norm   # Re-normalize L2

        avg_q = float(np.mean(qualities))
        logger.info(f"[FUSE] {len(embeddings)} angles → master avg_q={avg_q:.3f}")
        return master, avg_q

    # ---------------------------------------------------------------- #
    #  Finalize enrollment → encrypt → DB                              #
    # ---------------------------------------------------------------- #
    def finalize_enrollment(
        self,
        embeddings: List[np.ndarray],
        angles:     List[str],
        qualities:  List[float],
    ) -> Tuple[bytes, float]:
        master, avg_q = self.fuse_embeddings(embeddings, angles, qualities)
        return encrypt_embedding(master), avg_q

    # ---------------------------------------------------------------- #
    #  Verify - Paper Section 5.3                                       #
    # ---------------------------------------------------------------- #
    def verify(
        self,
        image_bytes:         bytes,
        encrypted_embedding: bytes,
        threshold:           float = None,
    ) -> Tuple[bool, float]:
        """Cosine similarity ≥ 0.65 → MATCH"""
        threshold = threshold or settings.COSINE_SIMILARITY_THRESHOLD

        try:
            new_emb, _, _ = self.extract_embedding(image_bytes, "center")
        except (ValueError, RuntimeError) as e:
            logger.warning(f"[VERIFY] Failed: {e}")
            return False, 0.0

        stored     = decrypt_embedding(encrypted_embedding)
        sim        = cosine_similarity(new_emb, stored)
        is_match   = sim >= threshold

        logger.info(f"[VERIFY] sim={sim:.4f} threshold={threshold} match={is_match}")
        return is_match, sim

    # ---------------------------------------------------------------- #
    #  DB helpers (dùng cho attendance route)                           #
    # ---------------------------------------------------------------- #
    async def store_embedding(
        self, db: AsyncSession, student_id: int, embedding_b64: str
    ) -> bool:
        """Nhận base64 embedding từ ESP32 → encrypt → lưu DB"""
        raw  = base64.b64decode(embedding_b64)
        emb  = np.frombuffer(raw, dtype=np.float32).copy()

        if emb.shape[0] != 512:
            raise ValueError(f"Expected 512-dim, got {emb.shape[0]}")

        emb = emb / (np.linalg.norm(emb) + 1e-10)
        enc = encrypt_embedding(emb)

        result  = await db.execute(select(Student).where(Student.id == student_id))
        student = result.scalar_one_or_none()
        if not student:
            raise ValueError(f"Student {student_id} not found")

        student.face_embedding = enc
        await db.flush()
        return True

    async def identify_face(
        self,
        db:                  AsyncSession,
        query_embedding_b64: str,
        class_id:            Optional[int] = None,
    ) -> Tuple[Optional[int], float]:
        """
        So khớp embedding từ ESP32 vs tất cả sinh viên trong lớp.
        Returns: (student_id, similarity) hoặc (None, score)
        """
        raw       = base64.b64decode(query_embedding_b64)
        query_vec = np.frombuffer(raw, dtype=np.float32).copy()
        query_vec = query_vec / (np.linalg.norm(query_vec) + 1e-10)

        stmt = select(Student).where(
            Student.face_embedding.isnot(None),
            Student.status == "active",
        )
        if class_id:
            stmt = stmt.where(Student.class_id == class_id)

        result   = await db.execute(stmt)
        students = result.scalars().all()

        best_id    : Optional[int] = None
        best_score : float         = 0.0

        for student in students:
            try:
                stored = decrypt_embedding(student.face_embedding)
                sim    = cosine_similarity(query_vec, stored)
                if sim > best_score:
                    best_score = sim
                    best_id    = student.id
            except Exception:
                continue

        threshold = settings.COSINE_SIMILARITY_THRESHOLD
        if best_score >= threshold:
            return best_id, best_score
        return None, best_score

    def get_liveness_checker(self) -> LivenessChecker:
        return self._liveness


# Singleton
face_service = FaceService()

# ── Module-level aliases (dùng cho enrollment.py import) ─────────────────────
async def store_embedding(
    db: "AsyncSession",
    student_id: int,
    embedding_b64: str
) -> bool:
    """Proxy → face_service.store_embedding"""
    return await face_service.store_embedding(db, student_id, embedding_b64)


async def identify_face(
    db: "AsyncSession",
    query_embedding_b64: str,
    class_id: "Optional[int]" = None,
) -> "Tuple[Optional[int], float]":
    """Proxy → face_service.identify_face"""
    return await face_service.identify_face(db, query_embedding_b64, class_id)