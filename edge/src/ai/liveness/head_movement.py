"""
Layer 2 Liveness: Head Pose Estimation via solvePnP.
Requires a face with 5 landmarks (left_eye, right_eye, nose, left_mouth, right_mouth).
"""
import numpy as np
import cv2
from typing import List, Tuple, Optional

# Generic 3D face model reference points (mm scale)
MODEL_POINTS_5 = np.array([
    [-43.0,  32.7, -26.0],   # left eye
    [ 43.0,  32.7, -26.0],   # right eye
    [  0.0,   0.0,   0.0],   # nose tip
    [-28.9, -28.9, -24.1],   # left mouth
    [ 28.9, -28.9, -24.1],   # right mouth
], dtype=np.float64)

class HeadPoseEstimator:
    def __init__(self, frame_w: int = 1280, frame_h: int = 720):
        fx = frame_w
        fy = frame_w
        cx = frame_w / 2
        cy = frame_h / 2
        self.camera_matrix = np.array([
            [fx,  0, cx],
            [ 0, fy, cy],
            [ 0,  0,  1]
        ], dtype=np.float64)
        self.dist_coeffs = np.zeros((4, 1))

    def estimate(self, landmarks_5: List[List[int]]) -> Tuple[float, float, float]:
        """Returns (yaw, pitch, roll) in degrees."""
        img_pts = np.array(landmarks_5, dtype=np.float64)
        success, rvec, tvec = cv2.solvePnP(
            MODEL_POINTS_5, img_pts,
            self.camera_matrix, self.dist_coeffs,
            flags=cv2.SOLVEPNP_EPNP
        )
        if not success:
            return 0.0, 0.0, 0.0

        rmat, _ = cv2.Rodrigues(rvec)
        # Decompose to Euler angles
        sy = np.sqrt(rmat[0, 0] ** 2 + rmat[1, 0] ** 2)
        if sy > 1e-6:
            pitch = np.degrees(np.arctan2(-rmat[2, 0], sy))
            yaw   = np.degrees(np.arctan2(rmat[2, 1], rmat[2, 2]))
            roll  = np.degrees(np.arctan2(rmat[1, 0], rmat[0, 0]))
        else:
            pitch = np.degrees(np.arctan2(-rmat[2, 0], sy))
            yaw   = np.degrees(np.arctan2(-rmat[1, 2], rmat[1, 1]))
            roll  = 0.0
        return yaw, pitch, roll

class HeadMovementChecker:
    """Verify the user performs a requested head movement (left, right, nod)."""

    MOVEMENTS = {
        "left":  lambda y, p, r: y < -15,
        "right": lambda y, p, r: y >  15,
        "nod":   lambda y, p, r: p > 10,
    }

    def __init__(self, required: str = "left"):
        self.required = required
        self._done = False

    def update(self, yaw: float, pitch: float, roll: float) -> bool:
        if not self._done:
            check = self.MOVEMENTS.get(self.required, lambda *_: False)
            self._done = check(yaw, pitch, roll)
        return self._done

    def reset(self, required: str = None):
        self._done = False
        if required:
            self.required = required