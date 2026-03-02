"""
Cloud-side Face Service — Backend layer.

Kiến trúc microservice (sau khi tách AI Face Service):
  Backend (port 8000)  → auth, DB, business logic, AES encryption
  AI Service (port 9000) → InsightFace inference, cosine similarity

Backend gọi AI Service qua HTTP (ai_client.py).
AES key KHÔNG rời khỏi backend process.
"""
import os
import base64
import logging
import numpy as np
from typing import Tuple, List, Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.models.student import Student
from app.services.ai_client import ai_extract_embedding, ai_identify

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
#  AES-256-GCM — Embedding Encryption (Paper Section 6)
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
    """Cosine similarity — dùng cho local fallback khi ai-service down."""
    v1 = v1 / (np.linalg.norm(v1) + 1e-10)
    v2 = v2 / (np.linalg.norm(v2) + 1e-10)
    return float(np.dot(v1, v2))


# NOTE: LivenessChecker chạy trên Edge Device (edge/src/ai/liveness/)
# Backend không cần chạy liveness — đó là việc của edge.


# ══════════════════════════════════════════════════════════════════════
#  FaceService — Business logic layer (no AI inference here)
# ══════════════════════════════════════════════════════════════════════
class FaceService:
    """
    Enrollment pipeline (browser webcam):
      JPEG bytes → POST ai-service /extract → embedding 512-dim
      → buffer in Redis → weighted average → AES-encrypt → DB

    Identify pipeline (edge device → cloud):
      probe embedding_b64 → decrypt gallery (AES, local)
      → POST ai-service /identify → (student_id, confidence)
    """

    ANGLE_WEIGHTS = {
        "center": 2.0,
        "left":   1.0,
        "right":  1.0,
        "up":     0.8,
        "down":   0.8,
    }

    def __init__(self):
        pass  # No local model — InsightFace runs in ai-service

    # ---------------------------------------------------------------- #
    #  extract_embedding — Enrollment (gọi ai-service)               #
    # ---------------------------------------------------------------- #
    async def extract_embedding(
        self,
        image_bytes: bytes,
        angle: str = "center",
        min_blur: float = 60.0,
    ) -> Tuple[np.ndarray, float, dict]:
        """
        Nhận raw JPEG bytes, gọi ai-service để extract ArcFace embedding.
        Returns: (embedding 512-dim, quality_score, meta)
        """
        image_b64 = base64.b64encode(image_bytes).decode()
        embedding, quality, meta = await ai_extract_embedding(
            image_b64=image_b64,
            min_blur=min_blur,
        )
        logger.info(
            f"[EXTRACT] angle={angle} quality={quality:.3f} "
            f"blur={meta.get('blur_variance', '?')}"
        )
        return embedding, quality, meta

    # ---------------------------------------------------------------- #
    #  fuse_embeddings — Multi-frame weighted average (Paper 3.1)      #
    # ---------------------------------------------------------------- #
    def fuse_embeddings(
        self,
        embeddings: List[np.ndarray],
        angles:     List[str],
        qualities:  List[float],
    ) -> Tuple[np.ndarray, float]:
        weighted_sum = np.zeros_like(embeddings[0], dtype=np.float64)
        total_w      = 0.0

        for emb, angle, qual in zip(embeddings, angles, qualities):
            w             = self.ANGLE_WEIGHTS.get(angle, 1.0) * qual
            weighted_sum += w * emb.astype(np.float64)
            total_w      += w

        master = (weighted_sum / total_w).astype(np.float32)
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
    #  verify — single image vs 1 encrypted embedding (async now)      #
    # ---------------------------------------------------------------- #
    async def verify(
        self,
        image_bytes:         bytes,
        encrypted_embedding: bytes,
        threshold:           float = None,
    ) -> Tuple[bool, float]:
        """Cosine similarity ≥ 0.65 → MATCH (gọi ai-service)"""
        threshold = threshold or settings.COSINE_SIMILARITY_THRESHOLD
        try:
            new_emb, _, _ = await self.extract_embedding(image_bytes, "center")
        except (ValueError, RuntimeError) as e:
            logger.warning(f"[VERIFY] Failed: {e}")
            return False, 0.0

        stored   = decrypt_embedding(encrypted_embedding)
        gallery  = [(0, stored)]
        result   = await ai_identify(new_emb, gallery, threshold=threshold)
        sim      = result["confidence"]
        is_match = result["matched"]
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
        So khớp probe embedding (từ Edge) vs gallery trong DB.
        Flow: fetch DB → AES decrypt (local) → POST ai-service /identify
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

        if not students:
            return None, 0.0

        # Decrypt embeddings — AES key chỉ trong backend process
        gallery: List[Tuple[int, np.ndarray]] = []
        for student in students:
            try:
                plain = decrypt_embedding(student.face_embedding)
                gallery.append((student.id, plain))
            except Exception as e:
                logger.warning(f"[IDENTIFY] Decrypt failed student_id={student.id}: {e}")

        if not gallery:
            return None, 0.0

        threshold = settings.COSINE_SIMILARITY_THRESHOLD
        try:
            res = await ai_identify(query_vec, gallery, threshold=threshold)
        except RuntimeError as e:
            logger.error(f"[IDENTIFY] ai-service error, using local fallback: {e}")
            # Fallback: local numpy cosine khi ai-service down
            best_id, best_score = None, 0.0
            for sid, emb in gallery:
                sim = cosine_similarity(query_vec, emb)
                if sim > best_score:
                    best_score, best_id = sim, sid
            return (best_id if best_score >= threshold else None), best_score

        matched    = res["matched"]
        student_id = res.get("student_id")
        confidence = res.get("confidence", 0.0)
        logger.info(f"[IDENTIFY] matched={matched} sid={student_id} conf={confidence:.4f}")
        return (student_id if matched else None), confidence

    def get_liveness_checker(self):
        """Liveness runs on Edge. This stub exists for backward compat."""
        return None


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