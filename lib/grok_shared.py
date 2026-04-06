"""
Grok (xAI) Chia sẻ mô-đun Công cụ

Dùng lại text_backends / image_backends / video_backends.

Bao gồm:
- create_grok_client — xAI AsyncClient Nhà máy khách hàng
"""

from __future__ import annotations


def create_grok_client(*, api_key: str | None = None):
    """Tạo xAI AsyncClient，Xác minh và cấu trúc thống nhất."""
    import xai_sdk

    if not api_key:
        raise ValueError("XAI_API_KEY Chưa cài đặt\nVui lòng cấu hình xAI API Key trong trang cấu hình Hệ thống")
    return xai_sdk.AsyncClient(api_key=api_key)
