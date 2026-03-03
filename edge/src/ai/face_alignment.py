"""
5-point ArcFace face alignment.
Warps detected face to canonical 112x112 ArcFace crop using similarity transform.
"""
import cv2
import numpy as np
from typing import List

# ArcFace canonical 112x112 landmark positions
# Order: left_eye, right_eye, nose_tip, left_mouth, right_mouth
ARCFACE_DST = np.array([
    [38.2946, 51.6963],
    [73.5318, 51.5014],
    [56.0252, 71.7366],
    [41.5493, 92.3655],
    [70.7299, 92.2041],
], dtype=np.float32)

OUTPUT_SIZE = 112


def align_face(frame: np.ndarray, landmarks_5: List[List[int]]) -> np.ndarray:
    """Similarity transform from 5 landmarks to ArcFace 112x112. Returns aligned BGR crop."""
    src = np.array(landmarks_5, dtype=np.float32)
    M, _ = cv2.estimateAffinePartial2D(
        src, ARCFACE_DST, method=cv2.RANSAC, ransacReprojThreshold=2.0
    )
    if M is None:
        cx = int(np.mean(src[:, 0])); cy = int(np.mean(src[:, 1]))
        h, w = frame.shape[:2]; half = 56
        x1 = max(0, cx - half); y1 = max(0, cy - half)
        x2 = min(w, cx + half); y2 = min(h, cy + half)
        return cv2.resize(frame[y1:y2, x1:x2], (OUTPUT_SIZE, OUTPUT_SIZE))
    return cv2.warpAffine(frame, M, (OUTPUT_SIZE, OUTPUT_SIZE), borderMode=cv2.BORDER_REFLECT)


def enhance_image(img: np.ndarray) -> np.ndarray:
    """CLAHE contrast enhancement on 112x112 BGR crop for better matching under poor light."""
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l = clahe.apply(l)
    return cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)
