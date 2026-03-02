"""
Layer 3 Liveness: Monocular depth estimation (lightweight ONNX model).
A real 3D face has non-zero depth variance across the face region.
"""
import numpy as np
import onnxruntime as ort
import cv2
from edge.src.config import config

class DepthLivenessChecker:
    DELTA_DEPTH_THRESHOLD = 0.08   # Relative normalized depth difference

    def __init__(self, model_path: str = None):
        model_path = model_path or config.DEPTH_MODEL
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 2  # Lightweight — keep threads low
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

        self.session = ort.InferenceSession(
            model_path, sess_options=opts, providers=["CPUExecutionProvider"]
        )
        self.input_name = self.session.get_inputs()[0].name
        inp = self.session.get_inputs()[0]
        _, _, self.h, self.w = inp.shape  # Expected input size

    def _preprocess(self, face_crop: np.ndarray) -> np.ndarray:
        img = cv2.resize(face_crop, (self.w, self.h))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        img = np.transpose(img, (2, 0, 1))[np.newaxis]  # NCHW
        return img

    def check(self, face_crop: np.ndarray) -> Tuple[bool, float]:
        """
        Returns (is_live, delta_depth).
        A flat surface (photo/screen) has delta_depth ≈ 0.
        A real face has delta_depth > threshold.
        """
        inp = self._preprocess(face_crop)
        depth_map = self.session.run(None, {self.input_name: inp})[0][0, 0]  # (H, W)

        h, w = depth_map.shape
        # Compare nose region (center) vs ear region (sides)
        nose_region = depth_map[h // 3: 2 * h // 3, w // 3: 2 * w // 3]
        left_region = depth_map[h // 3: 2 * h // 3, :w // 6]
        right_region = depth_map[h // 3: 2 * h // 3, 5 * w // 6:]

        nose_depth = float(np.mean(nose_region))
        side_depth = float((np.mean(left_region) + np.mean(right_region)) / 2)
        delta = abs(nose_depth - side_depth)

        is_live = delta > self.DELTA_DEPTH_THRESHOLD
        return is_live, delta

from typing import Tuple  # noqa: E402 (keep at bottom to avoid circular)