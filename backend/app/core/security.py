import hashlib
import logging
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status, Header
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.database.session import get_db
from app.models.admin import Admin
from app.models.device import Device
from app.core.jwt_handler import decode_token

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

def _prehash(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def hash_password(password: str) -> str:
    return pwd_context.hash(_prehash(password))

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(_prehash(plain), hashed)

async def get_current_admin(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> Admin:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # Dùng decode_token() — hỗ trợ dual-key rotation
        payload = decode_token(token)
        logger.info(f"Token payload: {payload}")

        if payload.get("type") != "access":
            logger.error(f"Wrong token type: {payload.get('type')}")
            raise credentials_exc

        admin_id = payload.get("sub")
        if not admin_id:
            logger.error("No sub in payload")
            raise credentials_exc

    except ValueError as e:
        logger.error(f"Token decode error: {e}")
        raise credentials_exc

    result = await db.execute(select(Admin).where(Admin.id == int(admin_id)))
    admin = result.scalar_one_or_none()

    if not admin:
        logger.error(f"Admin id={admin_id} not found")
        raise credentials_exc

    if not admin.is_active:
        logger.error(f"Admin id={admin_id} is inactive")
        raise credentials_exc

    return admin

async def verify_device_token(
    x_device_token: str = Header(...),
    db: AsyncSession = Depends(get_db)
) -> Device:
    result = await db.execute(
        select(Device).where(
            Device.device_token == x_device_token,
            Device.status == "active"
        )
    )
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid device token"
        )
    return device