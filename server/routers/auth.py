"""
Xác thực đường dẫn API

Cung cấp giao diện Đăng nhập OAuth2 và xác thực token.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from server.auth import CurrentUser, check_credentials, create_token

logger = logging.getLogger(__name__)

router = APIRouter()


# ==================== Mẫu phản hồi ====================


class TokenResponse(BaseModel):
    access_token: str
    token_type: str


class VerifyResponse(BaseModel):
    valid: bool
    username: str


# ==================== Đường dẫn ====================


@router.post("/auth/token", response_model=TokenResponse)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
):
    """Người dùng Đăng nhập

    Sử dụng biểu mẫu tiêu chuẩn OAuth2 để xác thực thông tin xác thực, trả về access_token khi thành công.
    """
    if not check_credentials(form_data.username, form_data.password):
        logger.warning("Đăng nhập thất bại: Tên người dùngHoặc mật khẩu sai (người dùng: %s)", form_data.username)
        raise HTTPException(
            status_code=401,
            detail="Tên người dùngHoặc mật khẩu sai",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_token(form_data.username)
    logger.info("Người dùng đăng nhập thành công: %s", form_data.username)
    return TokenResponse(access_token=token, token_type="bearer")


@router.get("/auth/verify", response_model=VerifyResponse)
async def verify(
    current_user: CurrentUser,
):
    """Xác thực tính hợp lệ của token

    Sử dụng token OAuth2 Bearer dựa vào việc tự động trích xuất và xác thực token.
    """
    return VerifyResponse(valid=True, username=current_user.sub)
