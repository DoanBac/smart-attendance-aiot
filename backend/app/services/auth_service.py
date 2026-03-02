import logging
import hashlib
from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings
from app.models.admin import Admin
from app.schemas.auth import LoginRequest, TokenResponse, AdminCreate

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _prehash_password(password: str) -> str:
    """Pre-hash password với SHA256 để tránh giới hạn 72 bytes của bcrypt"""
    return hashlib.sha256(password.encode()).hexdigest()


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    def _hash_password(self, password: str) -> str:
        return pwd_context.hash(_prehash_password(password))

    def _verify_password(self, plain: str, hashed: str) -> bool:
        return pwd_context.verify(_prehash_password(plain), hashed)

    def _create_access_token(self, data: dict) -> str:
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode.update({"exp": expire, "type": "access"})
        return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

    def _create_refresh_token(self, data: dict) -> str:
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        to_encode.update({"exp": expire, "type": "refresh"})
        return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

    async def create_admin(self, data: AdminCreate) -> Admin:
        # Kiểm tra email đã tồn tại chưa
        result = await self.db.execute(select(Admin).where(Admin.email == data.email))
        existing = result.scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email đã được sử dụng"
            )

        admin = Admin(
            email=data.email,
            full_name=data.full_name,
            password_hash=self._hash_password(data.password),
            role=data.role,
            is_active=True
        )
        self.db.add(admin)
        await self.db.commit()
        await self.db.refresh(admin)
        logger.info(f"Admin created: {admin.email}")
        return admin

    async def login(self, credentials: LoginRequest) -> TokenResponse:
        result = await self.db.execute(select(Admin).where(Admin.email == credentials.email))
        admin = result.scalar_one_or_none()

        if not admin or not self._verify_password(credentials.password, admin.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Email hoặc mật khẩu không đúng"
            )

        if not admin.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tài khoản đã bị vô hiệu hóa"
            )

        payload = {"sub": str(admin.id), "email": admin.email, "role": admin.role}
        return TokenResponse(
            access_token=self._create_access_token(payload),
            refresh_token=self._create_refresh_token(payload),
            token_type="bearer"
        )

    async def refresh_token(self, refresh_token: str) -> TokenResponse:
        try:
            payload = jwt.decode(
                refresh_token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM]
            )
            if payload.get("type") != "refresh":
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token type"
                )

            admin_id = payload.get("sub")
            result = await self.db.execute(select(Admin).where(Admin.id == int(admin_id)))
            admin = result.scalar_one_or_none()

            if not admin or not admin.is_active:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Admin không tồn tại"
                )

            new_payload = {"sub": str(admin.id), "email": admin.email, "role": admin.role}
            return TokenResponse(
                access_token=self._create_access_token(new_payload),
                refresh_token=self._create_refresh_token(new_payload),
                token_type="bearer"
            )
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token không hợp lệ"
            )