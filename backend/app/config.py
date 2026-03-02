from pydantic_settings import BaseSettings
from typing import Optional
import secrets

class Settings(BaseSettings):
    # App
    APP_NAME: str = "AIoT Smart Attendance System"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    SECRET_KEY: str = secrets.token_urlsafe(32)
    
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://doanbac07:070301@postgres:5432/attendance_db"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20
    
    # JWT — PHẢI set cố định trong .env, KHÔNG để random (random → invalid sau mỗi restart)
    JWT_SECRET_KEY: str = "dev-secret-change-in-production-abcdef1234567890abcdef1234567890"
    JWT_SECRET_KEY_OLD: Optional[str] = None   # Key cũ — dùng khi rotation, xóa sau N ngày
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # AES Encryption for embeddings
    AES_KEY: str = "0" * 64  # 256-bit key
    
    # Redis
    REDIS_URL: str = "redis://redis:6379/0"      # ← redis (tên service docker)
    
    # MQTT
    MQTT_BROKER_HOST: str = "localhost"
    MQTT_BROKER_PORT: int = 1883
    MQTT_USERNAME: Optional[str] = None
    MQTT_PASSWORD: Optional[str] = None
    
    # Face Recognition
    MODEL_STORAGE_PATH: str = "/app/models"      # ← giữ 1 cái duy nhất
    COSINE_SIMILARITY_THRESHOLD: float = 0.65
    MAX_FACE_DISTANCE: float = 0.35
    
    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 100
    
    # CORS
    ALLOWED_ORIGINS: list = ["http://localhost:3000", "https://yourdomain.com"]

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()