"""
OpenAI Chia sẻ mô-đun Công cụ

Dành cho text_backends / image_backends / video_backends / providers tái sử dụng.

Bao gồm:
- OPENAI_RETRYABLE_ERRORS — Có Thử lại lỗi Loại
- create_openai_client — AsyncOpenAI Nhà máy khách hàng
"""

from __future__ import annotations

import logging

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

OPENAI_RETRYABLE_ERRORS: tuple[type[Exception], ...] = ()

try:
    from openai import (
        APIConnectionError,
        APITimeoutError,
        InternalServerError,
        RateLimitError,
    )

    OPENAI_RETRYABLE_ERRORS = (
        APIConnectionError,
        APITimeoutError,
        InternalServerError,
        RateLimitError,
    )
except ImportError:
    pass  # openai Là phụ thuộc bắt buộc cài đặt, nhánh này chỉ để bảo vệ phòng ngừa; quay lại tuple rỗng


def create_openai_client(
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    max_retries: int | None = None,
) -> AsyncOpenAI:
    """Tạo AsyncOpenAI Khách hàng, xử lý thống nhất api_key và base_url."""
    kwargs: dict = {}
    if api_key:
        kwargs["api_key"] = api_key
    if base_url:
        kwargs["base_url"] = base_url
    if max_retries is not None:
        kwargs["max_retries"] = max_retries
    return AsyncOpenAI(**kwargs)
