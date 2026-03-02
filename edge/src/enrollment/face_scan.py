"""
3D-like Face Scan enrollment (inspired by Apple FaceID).
Guides user through 6 pose directions and collects high-quality frames.
"""
import cv2
import numpy as np
import time
import logging
from typing import List, Tuple, Optional
from dataclasses import dataclass, field

from edge.src.ai.face_detection import FaceDetector
from edge.src.ai.face_alignment import align_face, enhance_image
from edge.src.ai.face_embedding import FaceEmbedder

logger = logging.getLogger(__name__)

POSE_STEPS = [
    {"name": "Nhìn thẳng",       "yaw_range": (-10, 10),  "pitch_range": (-10, 10)},
    {"name": "Quay trái nhẹ",    "yaw_range": (-30, -15), "pitch_range": (-15, 15)},
    {"name": "Quay phải nhẹ",    "yaw_range": (15, 30),   "pitch_range": (-15, 15)},
    {"name": "Ngẩng đầu nhẹ",    "yaw_range": (-10, 10),  "pitch_range": (-25, -10)},
    {"name": "Cúi đầu nhẹ",      "yaw_range": (-10, 10),  "pitch_range": (10, 25)},
    {"name": "Nhìn thẳng (xác nhận)", "yaw_range": (-8, 8), "pitch_range": (-8, 8)},
]

@dataclass
class EnrollmentResult:
    success: bool
    student_id: Optional[int]
    mean_embedding: Optional[np.ndarray]   # Averaged over all quality frames
    frame_count: int = 0
    error: str = ""

def blur_score(img: np.ndarray) -> float:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())

def face_area_ratio(bbox, frame_shape) -> float:
    x1, y1, x2, y2 = bbox
    face_area = (x2 - x1) * (y2 - y1)
    frame_area = frame_shape[0] * frame_shape[1]
    return face_area / frame_area

class FaceEnrollment:
    FRAMES_PER_STEP = 8    # Collect up to 8 quality frames per pose step
    MIN_BLUR = 100.0
    MIN_FACE_RATIO = 0.08
    MIN_LANDMARK_CONF = 0.7

    def __init__(self):
        self.detector = FaceDetector()
        self.embedder = FaceEmbedder()

    def run(self, cap: cv2.VideoCapture, student_id: int, display_fn=None) -> EnrollmentResult:
        """
        Full enrollment loop. display_fn(frame, message) optional for UI.
        Returns EnrollmentResult with mean_embedding if successful.
        """
        all_embeddings: List[np.ndarray] = []

        for step_idx, step in enumerate(POSE_STEPS):
            step_frames = 0
            step_start = time.time()
            timeout = 10.0  # 10 seconds per pose step

            logger.info(f"[Enrollment] Step {step_idx + 1}/{len(POSE_STEPS)}: {step['name']}")

            while step_frames < self.FRAMES_PER_STEP:
                if time.time() - step_start > timeout:
                    logger.warning(f"Timeout on step: {step['name']}")
                    break

                ret, frame = cap.read()
                if not ret:
                    continue

                msg = f"[{step_idx+1}/{len(POSE_STEPS)}] {step['name']} ({step_frames}/{self.FRAMES_PER_STEP})"
                if display_fn:
                    display_fn(frame.copy(), msg)

                faces = self.detector.detect(frame)
                if not faces:
                    continue

                face = max(faces, key=lambda f: face_area_ratio(f["bbox"], frame.shape))

                # Quality checks
                if face["confidence"] < self.MIN_LANDMARK_CONF:
                    continue
                if face_area_ratio(face["bbox"], frame.shape) < self.MIN_FACE_RATIO:
                    continue

                aligned = align_face(frame, face["landmarks"])
                aligned = enhance_image(aligned)

                if blur_score(aligned) < self.MIN_BLUR:
                    continue

                # Extract and collect embedding
                emb = self.embedder.extract(aligned)
                all_embeddings.append(emb)
                step_frames += 1

            if step_frames == 0:
                return EnrollmentResult(
                    success=False,
                    student_id=student_id,
                    mean_embedding=None,
                    error=f"No quality frames collected for step: {step['name']}"
                )

        if len(all_embeddings) < 10:
            return EnrollmentResult(
                success=False,
                student_id=student_id,
                mean_embedding=None,
                frame_count=len(all_embeddings),
                error="Insufficient quality frames for enrollment"
            )

        # Average all embeddings and re-normalize (FaceID-style profile)
        mean_emb = np.mean(all_embeddings, axis=0)
        mean_emb = mean_emb / (np.linalg.norm(mean_emb) + 1e-10)

        return EnrollmentResult(
            success=True,
            student_id=student_id,
            mean_embedding=mean_emb,
            frame_count=len(all_embeddings),
        )