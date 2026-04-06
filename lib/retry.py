"""Trình trang trí Thử lại chung, với thoái lui mũ và dao động ngẫu nhiên.

Không phụ thuộc vào bất kỳ nhà cung cấp SDK cụ thể nào, có thể tái sử dụng bởi tất cả các backend.
Các nhà cung cấp có thể tiêm loại Thử lại của riêng họ thông qua tham số retryable_errors.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import random

logger = logging.getLogger(__name__)

# Lỗi có thể Thử lại cơ bản (không phụ thuộc vào bất kỳ SDK nào)
BASE_RETRYABLE_ERRORS: tuple[type[Exception], ...] = (
    ConnectionError,
    TimeoutError,
)

# chuỗiKhớp mẫu: ghi đè loại bất thường không có trong danh sách nhưng thuộc trường hợp tạm thời (không phân biệt chữ hoa chữ thường)
RETRYABLE_STATUS_PATTERNS = (
    "429",
    "resource_exhausted",
    "500",
    "502",
    "503",
    "504",
    "internalservererror",
    "internal server error",
    "serviceunavailable",
    "service unavailable",
    "bad gateway",
    "gateway timeout",
    "timed out",
    "timeout",
)

# Cấu hình Thử lại mặc định, cho các backend tham chiếu trực tiếp, tránh các con số ma rải rác ở hơn 9 chỗ
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BACKOFF_SECONDS: tuple[int, ...] = (2, 4, 8)


def _should_retry(exc: Exception, retryable_errors: tuple[type[Exception], ...]) -> bool:
    """Xác định xem bất thường có nên Thử lại hay không."""
    if isinstance(exc, retryable_errors):
        return True
    error_lower = str(exc).lower()
    return any(pattern in error_lower for pattern in RETRYABLE_STATUS_PATTERNS)


def with_retry_async(
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    backoff_seconds: tuple[int, ...] = DEFAULT_BACKOFF_SECONDS,
    retryable_errors: tuple[type[Exception], ...] = BASE_RETRYABLE_ERRORS,
):
    """Trình trang trí hàm bất đồng bộ Thử lại, với thoái lui mũ và dao động ngẫu nhiên."""

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    if not _should_retry(e, retryable_errors):
                        raise

                    if attempt < max_attempts - 1:
                        backoff_idx = min(attempt, len(backoff_seconds) - 1)
                        base_wait = backoff_seconds[backoff_idx]
                        jitter = random.uniform(0, 2)
                        wait_time = base_wait + jitter
                        logger.warning(
                            "API Gọi bất thường: %s - %s",
                            type(e).__name__,
                            str(e)[:200],
                        )
                        logger.warning(
                            "Thử lại %d/%d, %.1f Sau vài giây...",
                            attempt + 1,
                            max_attempts - 1,
                            wait_time,
                        )
                        await asyncio.sleep(wait_time)
                    else:
                        raise

            raise RuntimeError(f"with_retry_async: max_attempts={max_attempts}，Chưa thực hiện bất kỳ thử nghiệm nào")

        return wrapper

    return decorator
