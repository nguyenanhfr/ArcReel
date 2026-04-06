"""
Ark (Hòm núi lửa) Chia sẻ mô-đun Công cụ

Dành cho text_backends / image_backends / video_backends / providers tái sử dụng.

Bao gồm:
- ARK_BASE_URL — Hòm núi lửa API URL cơ bản
- resolve_ark_api_key — API Key Phân tích (bao gồm fallback Biến môi trường)
- create_ark_client — Ark Nhà máy khách hàng
"""

from __future__ import annotations

import os

ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"


def resolve_ark_api_key(api_key: str | None = None) -> str:
    """Phân tích Ark API Key, hỗ trợ fallback Biến môi trường."""
    resolved = api_key or os.environ.get("ARK_API_KEY")
    if not resolved:
        raise ValueError("Ark API Key Chưa cung cấp. Vui lòng cấu hình API Key trên trang 「Cài đặt toàn cục → nhà cung cấp」.")
    return resolved


def create_ark_client(*, api_key: str | None = None):
    """Tạo Ark Khách hàng, kiểm tra api_key thống nhất và xây dựng."""
    from volcenginesdkarkruntime import Ark

    return Ark(base_url=ARK_BASE_URL, api_key=resolve_ark_api_key(api_key))
