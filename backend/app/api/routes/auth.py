from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.session import get_db
from app.schemas.auth import LoginRequest, TokenResponse, AdminCreate, AdminResponse, RefreshRequest
from app.services.auth_service import AuthService

router = APIRouter()

# ✅ Không cần authentication - public route
@router.post("/register", response_model=AdminResponse, status_code=status.HTTP_201_CREATED)
async def register(
    admin_data: AdminCreate,
    db: AsyncSession = Depends(get_db)
):
    """Đăng ký admin mới - chỉ dùng lần đầu setup"""
    service = AuthService(db)
    return await service.create_admin(admin_data)

# ✅ Không cần authentication - public route  
@router.post("/login", response_model=TokenResponse)
async def login(
    credentials: LoginRequest,
    db: AsyncSession = Depends(get_db)
):
    """Đăng nhập và nhận JWT token"""
    service = AuthService(db)
    return await service.login(credentials)

@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshRequest,
    db: AsyncSession = Depends(get_db)
):
    """Refresh access token"""
    service = AuthService(db)
    return await service.refresh_token(request.refresh_token)