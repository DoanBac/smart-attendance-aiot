"""
Layer 1 Liveness: Deep Learning Eye Blink Detection.
Uses a MobileNetV2 ONNX model to classify eye status (open/closed).
"""
import cv2
import numpy as np
import onnxruntime as ort
from collections import deque
from typing import List, Tuple, Optional
from edge.src.config import config

class EyeBlinkModel:
    """MobileNet eye blink classifier (onnx)."""
    def __init__(self, model_path: str = None):
        model_path = model_path or config.BLINK_MODEL
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = config.ORT_NUM_THREADS
        self.session = ort.InferenceSession(
            model_path,
            sess_options=opts,
            providers=["CPUExecutionProvider"]
        )
        self.input_name = self.session.get_inputs()[0].name
        self.input_shape = self.session.get_inputs()[0].shape  # e.g., [None, 128, 128, 3]

    def predict(self, eye_img: np.ndarray) -> float:
        """
        Predict open probability.
        eye_img: BGR image of the eye.
        Returns: float in [0, 1] (1.0 = open, 0.0 = closed).
        """
        # Preprocessing matching the notebook
        h, w = self.input_shape[1:3]
        img = cv2.resize(eye_img, (w, h))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32)
        img = img / 255.0
        inp = img[np.newaxis, ...] # (1, 128, 128, 3)

        outputs = self.session.run(None, {self.input_name: inp})
        return float(outputs[0][0][0])

class BlinkDetector:
    def __init__(
        self,
        threshold: float = 0.5,
        consec_frames: int = 1,
        window_sec: float = 3.0,
        fps: int = 10,
        required_blinks: int = 1
    ):
        self.model = EyeBlinkModel()
        self.threshold = threshold
        self.consec_frames = consec_frames
        self.window_frames = int(window_sec * fps)
        self.required_blinks = required_blinks

        self._closed_counter = 0  # consecutive closed frames
        self._history = deque(maxlen=self.window_frames) # status history (True=Open, False=Closed)
        self._blinks = deque()  # timestamps of confirmed blinks
        self._frame_idx = 0
        self._last_state = True # Start assuming open

    def crop_eyes(self, frame: np.ndarray, landmarks: List[List[int]]) -> List[np.ndarray]:
        """
        Crop left and right eye regions from 5-pt landmarks.
        landmarks: [[x,y]*5] -> 0:L-Eye, 1:R-Eye, 2:Nose, 3:L-Mouth, 4:R-Mouth
        """
        crops = []
        # Estimate eye box size based on distance between eyes
        dx = landmarks[1][0] - landmarks[0][0]
        dy = landmarks[1][1] - landmarks[0][1]
        dist = np.sqrt(dx*dx + dy*dy)
        size = int(dist * 0.6) # Approximate size of eye region
        
        for i in range(2): # 0: Left, 1: Right
            cx, cy = landmarks[i]
            x1 = max(0, int(cx - size // 2))
            y1 = max(0, int(cy - size // 2))
            x2 = min(frame.shape[1], x1 + size)
            y2 = min(frame.shape[0], y1 + size)
            crops.append(frame[y1:y2, x1:x2])
        return crops

    def update(self, frame: np.ndarray, landmarks: List[List[int]]) -> bool:
        """
        Update with new frame and landmarks.
        Returns True when a blink is detected.
        """
        self._frame_idx += 1
        crops = self.crop_eyes(frame, landmarks)
        if not crops:
            return False

        # Average prediction for both eyes
        scores = [self.model.predict(c) for c in crops]
        avg_score = sum(scores) / len(scores)
        is_open = avg_score > self.threshold

        # Blink logic: Open -> Closed -> Open
        if not is_open:
            self._closed_counter += 1
        else:
            # We transitioned from Closed back to Open
            if self._closed_counter >= self.consec_frames:
                self._blinks.append(self._frame_idx)
            self._closed_counter = 0

        # Remove old blinks
        cutoff = self._frame_idx - self.window_frames
        while self._blinks and self._blinks[0] < cutoff:
            self._blinks.popleft()

        return len(self._blinks) >= self.required_blinks

    def reset(self):
        self._closed_counter = 0
        self._blinks.clear()
        self._frame_idx = 0