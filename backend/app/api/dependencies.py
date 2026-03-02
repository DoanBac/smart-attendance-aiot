import logging
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.database.session import get_db
from app.models.admin import Admin
from app.core.jwt_handler import decode_token

logger = logging.getLogger(__name__)

security = HTTPBearer()


async def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> Admin:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        token = credentials.credentials
        # Dùng decode_token() — hỗ trợ dual-key rotation
        payload = decode_token(token)

        admin_id: str = payload.get("sub")
        token_type: str = payload.get("type")

        if admin_id is None or token_type != "access":
            raise credentials_exception

    except ValueError as e:
        logger.error(f"Token decode error: {e}")
        raise credentials_exception

    result = await db.execute(select(Admin).where(Admin.id == int(admin_id)))
    admin = result.scalar_one_or_none()

    if admin is None or not admin.is_active:
        raise credentials_exception

    return admin


async def get_current_active_admin(
    current_admin: Admin = Depends(get_current_admin)
) -> Admin:
    return current_admin


def require_role(*roles: str):
    async def role_checker(
        current_admin: Admin = Depends(get_current_admin)
    ) -> Admin:
        if current_admin.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Yêu cầu quyền: {', '.join(roles)}"
            )
        return current_admin
    return role_checker