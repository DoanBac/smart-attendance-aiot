import cv2
import numpy as np
import onnxruntime as ort
from typing import List

class EyeBlinkModel:
    def __init__(self, model_path: str = "/app/edge_models/mobilenet_eye_blink.onnx"):
        import os
        if not os.path.exists(model_path):
            # Fallback for local testing
            model_path = "../edge/models/mobilenet_eye_blink.onnx"
            if not os.path.exists(model_path):
                # Fallback again if running inside ai-service folder without docker
                model_path = "../../edge/models/mobilenet_eye_blink.onnx"

        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 2
        self.session = ort.InferenceSession(
            model_path,
            sess_options=opts,
            providers=["CPUExecutionProvider"]
        )
        self.input_name = self.session.get_inputs()[0].name
        self.input_shape = self.session.get_inputs()[0].shape

    def predict(self, eye_img: np.ndarray) -> float:
        h, w = self.input_shape[1:3]
        img = cv2.resize(eye_img, (w, h))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32)
        img = img / 255.0
        inp = img[np.newaxis, ...]

        outputs = self.session.run(None, {self.input_name: inp})
        return float(outputs[0][0][0])

def crop_eyes(frame: np.ndarray, landmarks: List[List[float]]) -> List[np.ndarray]:
    crops = []
    dx = landmarks[1][0] - landmarks[0][0]
    dy = landmarks[1][1] - landmarks[0][1]
    dist = np.sqrt(dx*dx + dy*dy)
    size = int(dist * 0.6)
    
    for i in range(2):
        cx, cy = landmarks[i]
        x1 = max(0, int(cx - size // 2))
        y1 = max(0, int(cy - size // 2))
        x2 = min(frame.shape[1], x1 + size)
        y2 = min(frame.shape[0], y1 + size)
        img_crop = frame[y1:y2, x1:x2]
        if img_crop.size > 0:
            crops.append(img_crop)
    return crops

def analyze_blink_sequence(frames: List[np.ndarray], landmarks_list: List[List[List[float]]], threshold: float = 0.5):
    """
    Check if a blink occurs in the sequence by measuring eye state amplitude change.
    Returns (True/False, debug_dict)
    """
    model = EyeBlinkModel()
    
    scores = []
    for frame, landmarks in zip(frames, landmarks_list):
        if landmarks is None:
            scores.append(None)
            continue
            
        crops = crop_eyes(frame, landmarks)
        if not crops:
            scores.append(None)
            continue
            
        preds = [model.predict(c) for c in crops]
        avg_score = sum(preds) / len(preds)
        scores.append(avg_score)
        
    valid_scores = [s for s in scores if s is not None]
    
    debug_info = {
        "total_frames": len(frames),
        "valid_frames": len(valid_scores),
        "amplitude": 0.0,
        "scores": [round(s, 3) for s in valid_scores],
    }
    
    if len(valid_scores) < 3:
        return False, debug_info

    amplitude = max(valid_scores) - min(valid_scores)
    debug_info["amplitude"] = round(amplitude, 3)
    
    # Static photos/screenshots usually have amplitude < 0.05.
    # Blinks usually create a dip or peak > 0.15.
    # We also require at least one frame to show "relatively closed" eyes (< 0.4)
    if amplitude > 0.20 and min(valid_scores) < 0.4:
        return True, debug_info
        
    return False, debug_info
