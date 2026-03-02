from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from app.config import settings


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "type": "access"})
    # Luôn ký bằng key MỚI nhất
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    # Luôn ký bằng key MỚI nhất
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """
    Verify token với dual-key support để zero-downtime key rotation.

    Flow:
    1. Thử verify bằng JWT_SECRET_KEY (key hiện tại — mới nhất)
    2. Nếu fail, thử JWT_SECRET_KEY_OLD (key cũ — transition window)
    3. Nếu cả hai đều fail → raise ValueError

    Sau khi key rotation ổn định (vài ngày), xóa JWT_SECRET_KEY_OLD khỏi .env.
    """
    keys_to_try = [settings.JWT_SECRET_KEY]
    if settings.JWT_SECRET_KEY_OLD:
        keys_to_try.append(settings.JWT_SECRET_KEY_OLD)

    last_error: Exception = Exception("No keys configured")
    for key in keys_to_try:
        try:
            payload = jwt.decode(token, key, algorithms=[settings.JWT_ALGORITHM])
            return payload
        except JWTError as e:
            last_error = e
            continue  # thử key tiếp theo

    raise ValueError(f"Invalid token: {last_error}")