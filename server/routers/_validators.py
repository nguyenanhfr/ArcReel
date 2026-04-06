"""Hàm kiểm tra chia sẻ, dùng chung cho nhiều router."""

from __future__ import annotations

from fastapi import HTTPException

from lib.config.registry import PROVIDER_REGISTRY

# Tên provider theo định dạng cũ → provider_id theo định dạng registry mới.
# Giữ nhất quán với generation_worker._normalize_provider_id().
_LEGACY_PROVIDER_NAMES: dict[str, str] = {
    "gemini": "gemini-aistudio",
    "vertex": "gemini-vertex",
    "seedance": "ark",
}


def validate_backend_value(value: str, field_name: str) -> None:
    """Xác minh ``provider/model`` định dạngGiá trị từ backend của trường.

    Cũng chấp nhận tên provider đơn theo định dạng cũ (ví dụ ``"gemini"``），Để tương thích với các dự án tồn tại.

    Raises:
        HTTPException(400): định dạngKhông hợp lệ hoặc nhà cung cấp không có trong bảng đăng ký.
    """
    if "/" not in value:
        if value in _LEGACY_PROVIDER_NAMES or value in PROVIDER_REGISTRY:
            return  # Định dạng cũ hoặc ID đăng ký trần, xử lý bởi _normalize_provider_id() của hạ nguồn
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} định dạngNên là nhà cung cấp/mô hình",
        )
    provider_id = value.split("/", 1)[0]
    if provider_id not in PROVIDER_REGISTRY and not provider_id.startswith("custom-"):
        raise HTTPException(
            status_code=400,
            detail=f"Nhà cung cấp không xác định: {provider_id}",
        )
