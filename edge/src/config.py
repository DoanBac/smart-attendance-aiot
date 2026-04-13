from dataclasses import dataclass, field
from typing import Optional
import os
from dotenv import load_dotenv

# Load config from /app/config/device.env (Docker) or local edge/config/device.env
env_path = "/app/config/device.env"
if not os.path.exists(env_path):
    env_path = os.path.join(os.path.dirname(__file__), "..", "config", "device.env")
load_dotenv(env_path)

@dataclass
class EdgeConfig:
    # Device identity
    DEVICE_TOKEN: str           = os.getenv("DEVICE_TOKEN", "")
    CLASS_ID: str               = os.getenv("CLASS_ID", "")
    CLASS_NAME: str             = os.getenv("CLASS_NAME", "Lớp học")   # tên lớp hiển thị trên kiosk
    DEVICE_NAME: str            = os.getenv("DEVICE_NAME", "Pi Edge")  # tên thiết bị hiển thị trên kiosk

    # Cloud API
    CLOUD_API_URL: str          = os.getenv("CLOUD_API_URL", "https://api.example.com")
    SYNC_INTERVAL_SEC: int      = int(os.getenv("SYNC_INTERVAL_SEC", "30"))

    # Camera
    CAMERA_SOURCE: str          = os.getenv("CAMERA_SOURCE", "0")  # "0" USB, or RTSP/HTTP URL
    FRAME_WIDTH: int            = int(os.getenv("FRAME_WIDTH", "1280"))
    FRAME_HEIGHT: int           = int(os.getenv("FRAME_HEIGHT", "720"))
    CAPTURE_FPS: int            = int(os.getenv("CAPTURE_FPS", "10"))
    PROCESS_EVERY_N_FRAMES: int = int(os.getenv("PROCESS_EVERY_N_FRAMES", "3"))

    # AI Models
    DETECTION_MODEL: str        = os.getenv("DETECTION_MODEL", "/app/models/yolov8_face_320.onnx")
    EMBEDDING_MODEL: str        = os.getenv("EMBEDDING_MODEL", "/app/models/arcface_r100.onnx")
    DEPTH_MODEL: str            = os.getenv("DEPTH_MODEL", "/app/models/depth_lite.onnx")
    BLINK_MODEL: str            = os.getenv("BLINK_MODEL", "/app/models/mobilenet_eye_blink.onnx")

    # Face Recognition
    COSINE_THRESHOLD: float     = float(os.getenv("COSINE_THRESHOLD", "0.65"))
    LIVENESS_BLINK_THRESHOLD: float = float(os.getenv("LIVENESS_BLINK_THRESHOLD", "0.25"))
    LIVENESS_REQUIRE_BLINK: bool = os.getenv("LIVENESS_REQUIRE_BLINK", "true").lower() == "true"

    # AES Key (must match Cloud server)
    AES_KEY: str                = os.getenv("AES_KEY", "")

    # Local DB
    LOCAL_DB_PATH: str          = os.getenv("LOCAL_DB_PATH", "/app/data/local.db")

    # ONNX Runtime
    ORT_NUM_THREADS: int        = int(os.getenv("ORT_NUM_THREADS", "4"))

config = EdgeConfig()