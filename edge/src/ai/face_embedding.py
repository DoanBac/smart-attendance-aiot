"""
ArcFace (InsightFace) ONNX embedding extractor.
Input: 112x112 BGR aligned face.
Output: L2-normalized 512-dim float32 vector.
"""
import numpy as np
import onnxruntime as ort
import cv2
from edge.src.config import config

class FaceEmbedder:
    def __init__(self, model_path: str = None):
        model_path = model_path or config.EMBEDDING_MODEL

        opts = ort.SessionOptions()
        opts.intra_op_num_threads = config.ORT_NUM_THREADS
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

        self.session = ort.InferenceSession(
            model_path,
            sess_options=opts,
            providers=["CPUExecutionProvider"]
        )
        self.input_name = self.session.get_inputs()[0].name

    def _preprocess(self, aligned_bgr: np.ndarray) -> np.ndarray:
        """Normalize to [-1, 1] and convert to NCHW."""
        img = cv2.cvtColor(aligned_bgr, cv2.COLOR_BGR2RGB).astype(np.float32)
        img = (img - 127.5) / 128.0          # ArcFace standard normalization
        img = np.transpose(img, (2, 0, 1))    # HWC → CHW
        return img[np.newaxis]                 # NCHW

    def extract(self, aligned_bgr: np.ndarray) -> np.ndarray:
        """Returns L2-normalized 512-dim embedding vector."""
        inp = self._preprocess(aligned_bgr)
        output = self.session.run(None, {self.input_name: inp})[0]
        embedding = output[0]  # (512,)
        # L2 normalize
        norm = np.linalg.norm(embedding)
        return embedding / (norm + 1e-10)