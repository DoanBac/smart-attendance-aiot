from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    MODEL_STORAGE_PATH: str = "/app/models"
    MODEL_NAME: str = "buffalo_sc"          # buffalo_sc (nhẹ) hoặc buffalo_l (chính xác hơn)
    DET_SIZE: int = 640                      # Detection input size (640×640)
    COSINE_THRESHOLD: float = 0.65          # Default similarity threshold
    MIN_BLUR_VAR: float = 60.0              # Laplacian variance — dưới ngưỡng này = ảnh mờ
    MIN_FACE_RATIO: float = 0.05           # Khuôn mặt chiếm ≥ 5% diện tích ảnh

    # Internal service auth — backend phải gửi header X-Service-Key đúng
    SERVICE_SECRET_KEY: str = "ai-service-internal-secret-change-in-prod"

    class Config:
        env_file = "ai-service.env"
        extra = "ignore"


settings = Settings()
