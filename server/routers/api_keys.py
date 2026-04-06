"""
API Key Quản lý tuyến đường

Cung cấp giao diện Tạo, danh sách truy vấn và Xóa cho API Key.
"""

import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from lib.db import async_session_factory
from lib.db.repositories.api_key_repository import ApiKeyRepository
from server.auth import (
    API_KEY_PREFIX,
    CurrentUser,
    CurrentUserInfo,
    _hash_api_key,
    invalidate_api_key_cache,
)

router = APIRouter()


def _require_jwt_auth(user: CurrentUserInfo) -> None:
    """Đảm bảo yêu cầu thông qua xác thực JWT (không phải API Key). Thao tác quản lý API Key không được thực hiện bởi chính API Key."""
    if user.sub.startswith("apikey:"):
        raise HTTPException(status_code=403, detail="API Key Không có quyền thực hiện thao tác này, vui lòng sử dụng xác thực JWT")


API_KEY_DEFAULT_EXPIRY_DAYS = 30


def _generate_api_key() -> str:
    """Tạo định dạng là arc-<32Vị trí ngẫu nhiên từ ký tự> Khóa API。"""
    random_part = secrets.token_hex(16)  # 32 hex chars
    return f"{API_KEY_PREFIX}{random_part}"


def _default_expires_at() -> datetime:
    return datetime.now(UTC) + timedelta(days=API_KEY_DEFAULT_EXPIRY_DAYS)


class CreateApiKeyRequest(BaseModel):
    name: str
    expires_days: int | None = Field(None, ge=0)  # None Sử dụng mặc định 30 ngày, 0 có nghĩa là không hết hạn


class CreateApiKeyResponse(BaseModel):
    id: int
    name: str
    key: str  # Khóa đầy đủ, chỉ trả về khi Tạo
    key_prefix: str
    created_at: str
    expires_at: str | None


class ApiKeyInfo(BaseModel):
    id: int
    name: str
    key_prefix: str
    created_at: str
    expires_at: str | None
    last_used_at: str | None


@router.post("/api-keys", status_code=201)
async def create_api_key(
    body: CreateApiKeyRequest,
    _user: CurrentUser,
) -> CreateApiKeyResponse:
    """TạoAPI Key mới. Khóa đầy đủ chỉ xuất hiện một lần trong phản hồi, sau đó không thể xem lại."""
    _require_jwt_auth(_user)
    key = _generate_api_key()
    key_hash = _hash_api_key(key)
    key_prefix = key[:8]  # e.g. "arc-abcd"

    if body.expires_days == 0:
        expires_at: datetime | None = None
    elif body.expires_days is not None:
        expires_at = datetime.now(UTC) + timedelta(days=body.expires_days)
    else:
        expires_at = _default_expires_at()

    try:
        async with async_session_factory() as session:
            async with session.begin():
                repo = ApiKeyRepository(session)
                row = await repo.create(
                    name=body.name,
                    key_hash=key_hash,
                    key_prefix=key_prefix,
                    expires_at=expires_at,
                )
    except IntegrityError:
        raise HTTPException(status_code=409, detail=f"Tên '{body.name}' Đã tồn tại")

    return CreateApiKeyResponse(
        id=row["id"],
        name=row["name"],
        key=key,
        key_prefix=row["key_prefix"],
        created_at=row["created_at"],
        expires_at=row["expires_at"],
    )


@router.get("/api-keys")
async def list_api_keys(
    _user: CurrentUser,
) -> list[ApiKeyInfo]:
    """Truy vấn tất cả metadata của API Key (không bao gồm khóa đầy đủ)."""
    _require_jwt_auth(_user)
    async with async_session_factory() as session:
        async with session.begin():
            repo = ApiKeyRepository(session)
            rows = await repo.list_all()

    return [ApiKeyInfo(**row) for row in rows]


@router.delete("/api-keys/{key_id}", status_code=204)
async def delete_api_key(
    key_id: int,
    _user: CurrentUser,
) -> None:
    """Xóa（Thu hồi）Chỉ định API Key và ngay lập tức Xóa bộ nhớ cache."""
    _require_jwt_auth(_user)
    async with async_session_factory() as session:
        async with session.begin():
            repo = ApiKeyRepository(session)
            row = await repo.get_by_id(key_id)
            if row is None:
                raise HTTPException(status_code=404, detail=f"API Key {key_id} 不存在")
            key_hash = row["key_hash"]
            # Vô hiệu hóa cache trước khi xóa cơ sở dữ liệu: ngay cả khi giao dịch được cam kết rồi sập, cache vẫn Đã Xóa,
            # Sẽ không xuất hiện cửa sổ trễ khi DB đã xóa nhưng cache vẫn còn hiệu lực.
            invalidate_api_key_cache(key_hash)
            deleted = await repo.delete(key_id)

    if not deleted:
        raise HTTPException(status_code=404, detail=f"API Key {key_id} 不存在")
