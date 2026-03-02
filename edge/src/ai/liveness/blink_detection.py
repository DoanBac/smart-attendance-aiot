"""
Layer 1 Liveness: Eye Aspect Ratio (EAR) blink detection.
Uses 6-point eye landmarks from dlib/mediapipe.
"""
import numpy as np
from collections import deque
from typing import List, Tuple

def eye_aspect_ratio(eye_pts: List[Tuple[float, float]]) -> float:
    """
    EAR = (||p2-p6|| + ||p3-p5||) / (2 * ||p1-p4||)
    eye_pts: 6 points [p1..p6] clockwise around the eye.
    """
    def dist(a, b):
        return np.linalg.norm(np.array(a) - np.array(b))

    A = dist(eye_pts[1], eye_pts[5])
    B = dist(eye_pts[2], eye_pts[4])
    C = dist(eye_pts[0], eye_pts[3])
    return (A + B) / (2.0 * C + 1e-6)

class BlinkDetector:
    def __init__(
        self,
        ear_threshold: float = 0.25,
        consec_frames: int = 2,
        window_sec: float = 3.0,
        fps: int = 10,
        required_blinks: int = 1
    ):
        self.ear_threshold = ear_threshold
        self.consec_frames = consec_frames
        self.window_frames = int(window_sec * fps)
        self.required_blinks = required_blinks

        self._counter = 0       # consecutive below-threshold frames
        self._blinks = deque()  # timestamps (frame indices) of confirmed blinks
        self._frame_idx = 0

    def update(self, left_eye: List, right_eye: List) -> bool:
        """
        Feed new eye landmark points. Returns True when required_blinks confirmed.
        """
        self._frame_idx += 1
        ear = (eye_aspect_ratio(left_eye) + eye_aspect_ratio(right_eye)) / 2.0

        if ear < self.ear_threshold:
            self._counter += 1
        else:
            if self._counter >= self.consec_frames:
                self._blinks.append(self._frame_idx)
            self._counter = 0

        # Remove old blinks outside the window
        cutoff = self._frame_idx - self.window_frames
        while self._blinks and self._blinks[0] < cutoff:
            self._blinks.popleft()

        return len(self._blinks) >= self.required_blinks

    def reset(self):
        self._counter = 0
        self._blinks.clear()
        self._frame_idx = 0