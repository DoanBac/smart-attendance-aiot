"""
InsightFace SCRFD ONNX face detector (det_10g.onnx).

Output format — 9 tensors in order:
  [score_s8, score_s16, score_s32,   - shape (N_i, 1)
   bbox_s8,  bbox_s16,  bbox_s32,    - shape (N_i, 4)  distance to l/t/r/b
   kps_s8,   kps_s16,   kps_s32]     - shape (N_i, 10) 5 keypoints x 2
"""
import cv2
import numpy as np
import onnxruntime as ort
from typing import List, Dict, Any
from edge.src.config import config


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -88, 88)))


def _distance2bbox(anchor_centers: np.ndarray, deltas: np.ndarray) -> np.ndarray:
    x1 = anchor_centers[:, 0] - deltas[:, 0]
    y1 = anchor_centers[:, 1] - deltas[:, 1]
    x2 = anchor_centers[:, 0] + deltas[:, 2]
    y2 = anchor_centers[:, 1] + deltas[:, 3]
    return np.stack([x1, y1, x2, y2], axis=-1)


def _distance2kps(anchor_centers: np.ndarray, deltas: np.ndarray) -> np.ndarray:
    kps = []
    for i in range(0, deltas.shape[1], 2):
        kps.append(anchor_centers[:, 0] + deltas[:, i])
        kps.append(anchor_centers[:, 1] + deltas[:, i + 1])
    return np.array(kps).T  # (N, 10)


def _nms(boxes: np.ndarray, scores: np.ndarray, iou_threshold: float = 0.4) -> List[int]:
    x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    areas = np.maximum(0, x2 - x1) * np.maximum(0, y2 - y1)
    order = scores.argsort()[::-1]
    kept: List[int] = []
    while order.size:
        i = order[0]
        kept.append(int(i))
        if order.size == 1:
            break
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        inter = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
        iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-6)
        order = order[1:][iou <= iou_threshold]
    return kept


class FaceDetector:
    """SCRFD face detector -- compatible with det_10g.onnx (InsightFace)."""

    STRIDES = [8, 16, 32]
    NUM_ANCHORS = 2
    INPUT_SIZE = 320

    def __init__(self, model_path: str = None):
        model_path = model_path or config.DETECTION_MODEL

        opts = ort.SessionOptions()
        opts.intra_op_num_threads = config.ORT_NUM_THREADS
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

        self.session = ort.InferenceSession(
            model_path,
            sess_options=opts,
            providers=["CPUExecutionProvider"],
        )
        self.input_name = self.session.get_inputs()[0].name

    def _make_anchors(self, stride: int, fh: int, fw: int) -> np.ndarray:
        cols = np.arange(fw, dtype=np.float32)
        rows = np.arange(fh, dtype=np.float32)
        grid_x, grid_y = np.meshgrid(cols, rows)
        cx = (grid_x.ravel() + 0.5) * stride
        cy = (grid_y.ravel() + 0.5) * stride
        centers = np.stack([cx, cy], axis=-1)
        return np.repeat(centers, self.NUM_ANCHORS, axis=0)

    def detect(
        self,
        frame: np.ndarray,
        conf_threshold: float = 0.5,
    ) -> List[Dict[str, Any]]:
        """
        Detect faces in a BGR frame.
        Returns list of {bbox: [x1,y1,x2,y2], landmarks: [[x,y]*5], confidence: float}
        """
        orig_h, orig_w = frame.shape[:2]
        sz = self.INPUT_SIZE

        img = cv2.resize(frame, (sz, sz))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32)
        img = (img - 127.5) / 128.0
        inp = img.transpose(2, 0, 1)[np.newaxis]

        outputs = self.session.run(None, {self.input_name: inp})

        scale_x = orig_w / sz
        scale_y = orig_h / sz

        all_boxes, all_scores, all_kps = [], [], []

        for level, stride in enumerate(self.STRIDES):
            fh = sz // stride
            fw = sz // stride

            scores = _sigmoid(outputs[level].ravel())
            bboxes = outputs[level + 3] * stride
            kpss   = outputs[level + 6] * stride

            anchors = self._make_anchors(stride, fh, fw)
            boxes = _distance2bbox(anchors, bboxes)
            kpts  = _distance2kps(anchors, kpss)

            mask = scores >= conf_threshold
            if not mask.any():
                continue

            all_boxes.append(boxes[mask])
            all_scores.append(scores[mask])
            all_kps.append(kpts[mask])

        if not all_boxes:
            return []

        boxes      = np.concatenate(all_boxes)
        scores_arr = np.concatenate(all_scores)
        kps_arr    = np.concatenate(all_kps)

        keep = _nms(boxes, scores_arr)
        faces: List[Dict[str, Any]] = []
        for k in keep:
            x1, y1, x2, y2 = boxes[k]
            lms = [
                [int(kps_arr[k, i * 2] * scale_x), int(kps_arr[k, i * 2 + 1] * scale_y)]
                for i in range(5)
            ]
            faces.append({
                "bbox": [
                    int(x1 * scale_x), int(y1 * scale_y),
                    int(x2 * scale_x), int(y2 * scale_y),
                ],
                "landmarks": lms,
                "confidence": float(scores_arr[k]),
            })

        return faces
