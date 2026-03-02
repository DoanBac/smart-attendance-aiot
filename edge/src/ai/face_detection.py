"""
YOLOv8-face ONNX face detector.
Input: BGR frame (numpy array).
Output: list of dicts {bbox: [x1,y1,x2,y2], landmarks: [[x,y]*5], confidence: float}
"""
import numpy as np
import onnxruntime as ort
import cv2
from typing import List, Dict, Any
from edge.src.config import config

class FaceDetector:
    def __init__(self, model_path: str = None, input_size: int = 320):
        model_path = model_path or config.DETECTION_MODEL
        self.input_size = input_size

        opts = ort.SessionOptions()
        opts.intra_op_num_threads = config.ORT_NUM_THREADS
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        opts.enable_mem_pattern = True

        self.session = ort.InferenceSession(
            model_path,
            sess_options=opts,
            providers=["CPUExecutionProvider"]
        )
        self.input_name = self.session.get_inputs()[0].name

    def _preprocess(self, frame: np.ndarray):
        h, w = frame.shape[:2]
        img = cv2.resize(frame, (self.input_size, self.input_size))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = img.astype(np.float32) / 255.0
        img = np.transpose(img, (2, 0, 1))[np.newaxis]  # NCHW
        return img, w, h

    def detect(self, frame: np.ndarray, conf_threshold: float = 0.5) -> List[Dict[str, Any]]:
        inp, orig_w, orig_h = self._preprocess(frame)
        outputs = self.session.run(None, {self.input_name: inp})
        # outputs[0]: (1, num_boxes, 16) — x,y,w,h,conf,5*landmark(x,y)
        predictions = outputs[0][0]  # shape (num_boxes, 16)

        sx = orig_w / self.input_size
        sy = orig_h / self.input_size

        faces = []
        for pred in predictions:
            conf = float(pred[4])
            if conf < conf_threshold:
                continue
            cx, cy, bw, bh = pred[:4]
            x1 = int((cx - bw / 2) * sx)
            y1 = int((cy - bh / 2) * sy)
            x2 = int((cx + bw / 2) * sx)
            y2 = int((cy + bh / 2) * sy)

            # 5 landmarks: [left_eye, right_eye, nose, left_mouth, right_mouth]
            lms = []
            for i in range(5):
                lx = int(pred[5 + i * 2] * sx)
                ly = int(pred[5 + i * 2 + 1] * sy)
                lms.append([lx, ly])

            faces.append({
                "bbox": [x1, y1, x2, y2],
                "landmarks": lms,
                "confidence": conf
            })
        return faces