"""
Full Face Recognition Pipeline for Edge device.
Implements the 7-step pipeline from Paper_v2.md Section 5.
"""
import time
import random
import logging
import numpy as np
from typing import Optional, Tuple, List, Dict, Any

from edge.src.config import config
from edge.src.ai.face_detection import FaceDetector
from edge.src.ai.face_alignment import align_face, enhance_image
from edge.src.ai.face_embedding import FaceEmbedder
from edge.src.ai.liveness.blink_detection import BlinkDetector
from edge.src.ai.liveness.head_movement import HeadPoseEstimator, HeadMovementChecker
from edge.src.ai.liveness.depth_estimation import DepthLivenessChecker

logger = logging.getLogger(__name__)

class LivenessSession:
    """Tracks liveness state across multiple frames."""
    def __init__(self, fps: int = 10):
        self.blink = BlinkDetector(
            ear_threshold=config.LIVENESS_BLINK_THRESHOLD, fps=fps
        )
        movement = random.choice(["left", "right", "nod"])
        self.head = HeadMovementChecker(required=movement)
        self.required_movement = movement
        self.depth_passed = False
        self._started_at = time.time()

    @property
    def timeout(self) -> bool:
        return (time.time() - self._started_at) > 6.0   # 6-second window

    def is_complete(self) -> bool:
        return self.blink._blinks.__len__() >= 1 and self.head._done and self.depth_passed

    def liveness_score(self) -> float:
        score = 0.0
        if self.blink._blinks:
            score += 0.35
        if self.head._done:
            score += 0.35
        if self.depth_passed:
            score += 0.30
        return score


class AttendancePipeline:
    def __init__(self):
        logger.info("Loading AI models...")
        self.detector  = FaceDetector()
        self.embedder  = FaceEmbedder()
        self.pose_est  = HeadPoseEstimator(config.FRAME_WIDTH, config.FRAME_HEIGHT)
        self.depth_chk = DepthLivenessChecker()

        # Local embedding cache: student_id → (student_code, name, vector)
        self._embed_cache: Dict[int, Tuple[str, str, np.ndarray]] = {}
        logger.info("Pipeline ready.")

    def load_local_embeddings(self, rows):
        """
        Load decrypted embeddings into memory from local_db rows.
        rows: list of (student_id, student_code, full_name, embedding_vec: np.ndarray)
        """
        self._embed_cache.clear()
        for row in rows:
            sid, code, name, vec = row
            self._embed_cache[sid] = (code, name, vec)
        logger.info(f"Loaded {len(self._embed_cache)} embeddings into cache.")

    def match_embedding(self, query: np.ndarray) -> Tuple[Optional[int], Optional[str], float]:
        """
        Linear cosine similarity search in local cache.
        Returns (student_id, full_name, score) or (None, None, 0.0).
        """
        best_id, best_name, best_score = None, None, 0.0
        for sid, (code, name, vec) in self._embed_cache.items():
            sim = float(np.dot(query, vec))  # Both L2-normalized
            if sim > best_score:
                best_score = sim
                best_id = sid
                best_name = name

        if best_score >= config.COSINE_THRESHOLD:
            return best_id, best_name, best_score
        return None, None, best_score

    def process_frame_attendance(
        self,
        frame: np.ndarray,
        liveness_session: Optional[LivenessSession],
        eye_landmarks_fn=None   # Callable: frame → (left_eye_pts, right_eye_pts) or None
    ) -> Dict[str, Any]:
        """
        Run Steps 2–6 of the pipeline on a single frame.
        Returns result dict with keys: faces, recognized, liveness_done, etc.
        """
        result = {
            "faces_detected": 0,
            "recognized": None,   # {"student_id", "name", "confidence", "liveness_score"}
            "liveness_passed": False,
            "liveness_score": 0.0,
        }

        # Step 2: Face Detection
        faces = self.detector.detect(frame)
        if not faces:
            return result
        result["faces_detected"] = len(faces)

        # Take the largest face
        face = max(faces, key=lambda f: (f["bbox"][2] - f["bbox"][0]) * (f["bbox"][3] - f["bbox"][1]))

        # Step 3: Face Alignment
        aligned = align_face(frame, face["landmarks"])
        aligned = enhance_image(aligned)

        # Step 4: Liveness Detection (multi-layer)
        ls = liveness_session
        if ls and not ls.is_complete() and not ls.timeout:
            # Layer 1: Blink — requires 6-pt eye landmarks; fallback skip if not provided
            if eye_landmarks_fn:
                lm6 = eye_landmarks_fn(frame)
                if lm6:
                    ls.blink.update(lm6[0], lm6[1])

            # Layer 2: Head movement via 5-pt landmarks from detector
            yaw, pitch, roll = self.pose_est.estimate(face["landmarks"])
            ls.head.update(yaw, pitch, roll)

            # Layer 3: Depth check (every 5th call to reduce CPU load)
            if not ls.depth_passed:
                is_live, delta = self.depth_chk.check(aligned)
                if is_live:
                    ls.depth_passed = True

        liveness_ok = ls.is_complete() if ls else True  # Bypass if no session (enrollment)
        liveness_score = ls.liveness_score() if ls else 1.0
        result["liveness_passed"] = liveness_ok
        result["liveness_score"] = liveness_score

        if not liveness_ok:
            return result

        # Step 5: Embedding Extraction
        embedding = self.embedder.extract(aligned)

        # Step 6: Identity Matching
        sid, name, score = self.match_embedding(embedding)
        if sid:
            result["recognized"] = {
                "student_id": sid,
                "name": name,
                "confidence": round(score, 4),
                "liveness_score": round(liveness_score, 4),
            }

        return result