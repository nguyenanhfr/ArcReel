"""
Gemini Chia sẻ mô-đun Công cụ

Công cụ không phải GeminiClient được trích xuất từ gemini_client.py, dùng cho image_backends / video_backends /
providers / media_generator các module khác tái sử dụng, tránh phụ thuộc vòng lặp.

Bao gồm:
- VERTEX_SCOPES — Vertex AI OAuth scopes
- RETRYABLE_ERRORS — Gemini Loại lỗi có thể Thử lại chuyên dụng (mở rộng từ BASE_RETRYABLE_ERRORS)
- RateLimiter — Bộ giới hạn trượt nhiều mô hình
- _rate_limiter_limits_from_env / get_shared_rate_limiter / refresh_shared_rate_limiter
- with_retry_async — Trình trang trí Thử lại chung được tái xuất từ lib.retry
"""

import asyncio
import logging
import threading
import time
from collections import deque
from typing import Optional

from .cost_calculator import cost_calculator
from .retry import BASE_RETRYABLE_ERRORS, with_retry_async

__all__ = [
    "BASE_RETRYABLE_ERRORS",
    "RETRYABLE_ERRORS",
    "VERTEX_SCOPES",
    "RateLimiter",
    "get_shared_rate_limiter",
    "refresh_shared_rate_limiter",
    "with_retry_async",
]

logger = logging.getLogger(__name__)

# Vertex AI Các phạm vi OAuth cần thiết cho tài khoản dịch vụ (hằng số chia sẻ, dùng cho gemini_client / video_backends / providers)
VERTEX_SCOPES = [
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/generative-language",
]

# Gemini Loại lỗi có thể Thử lại chuyên dụng (mở rộng tập hợp cơ bản)
RETRYABLE_ERRORS: tuple[type[Exception], ...] = BASE_RETRYABLE_ERRORS

# Cố gắng nhập Loại lỗi API Google
try:
    from google import genai  # Import genai to access its errors
    from google.api_core import exceptions as google_exceptions

    RETRYABLE_ERRORS = RETRYABLE_ERRORS + (
        google_exceptions.ResourceExhausted,  # 429 Too Many Requests
        google_exceptions.ServiceUnavailable,  # 503
        google_exceptions.DeadlineExceeded,  # 超时
        google_exceptions.InternalServerError,  # 500
        genai.errors.ClientError,  # 4xx errors from new SDK
        genai.errors.ServerError,  # 5xx errors from new SDK
    )
except ImportError:
    pass


class RateLimiter:
    """
    Bộ giới hạn trượt nhiều mô hình
    """

    def __init__(self, limits_dict: dict[str, int] = None, *, request_gap: float = 3.1):
        """
        Args:
            limits_dict: {model_name: rpm} từVí dụ. Ví dụ {"gemini-3-pro-image-preview": 20}
            request_gap: Khoảng cách yêu cầu tối thiểu (giây), mặc định 3.1
        """
        self.limits = limits_dict or {}
        self.request_gap = request_gap
        # Lưu dấu thời gian yêu cầu:{model_name: deque([timestamp1, timestamp2, ...])}
        self.request_logs: dict[str, deque] = {}
        self.lock = threading.Lock()

    def acquire(self, model_name: str):
        """
        Chặn cho đến khi nhận được token
        """
        if model_name not in self.limits:
            return  # Cấu hình luồng vô hạn của mô hình

        limit = self.limits[model_name]
        if limit <= 0:
            return

        with self.lock:
            if model_name not in self.request_logs:
                self.request_logs[model_name] = deque()

            log = self.request_logs[model_name]

            while True:
                now = time.time()

                # Xóa các bản ghi cũ vượt quá 60 giây
                while log and now - log[0] > 60:
                    log.popleft()

                # Cưỡng bức tăng khoảng cách giữa các yêu cầu (theo yêu cầu của người dùng) > 3s）
                # Ngay cả khi nhận được token, cũng phải đảm bảo ít nhất 3 giây kể từ lần yêu cầu trước
                # Lấy thời gian yêu cầu mới nhất (có thể là do thread khác vừa ghi)
                min_gap = self.request_gap
                if log:
                    last_request = log[-1]
                    gap = time.time() - last_request
                    if gap < min_gap:
                        time.sleep(min_gap - gap)
                        # Cập nhật thời gian, kiểm tra lại
                        continue

                if len(log) < limit:
                    # Nhận token thành công
                    log.append(time.time())
                    return

                # Đạt giới hạn, tính toán thời gian chờ
                # Chờ cho đến khi bản ghi sớm nhất hết hạn
                wait_time = 60 - (now - log[0]) + 0.1  # Thêm thêm 0,1 giây đệm
                if wait_time > 0:
                    time.sleep(wait_time)

    async def acquire_async(self, model_name: str):
        """
        Chặn bất đồng bộ cho đến khi nhận được token
        """
        if model_name not in self.limits:
            return  # Cấu hình luồng vô hạn của mô hình

        limit = self.limits[model_name]
        if limit <= 0:
            return

        while True:
            with self.lock:
                now = time.time()

                if model_name not in self.request_logs:
                    self.request_logs[model_name] = deque()

                log = self.request_logs[model_name]

                # Xóa các bản ghi cũ vượt quá 60 giây
                while log and now - log[0] > 60:
                    log.popleft()

                min_gap = self.request_gap
                wait_needed = 0
                if log:
                    last_request = log[-1]
                    gap = now - last_request
                    if gap < min_gap:
                        # Chờ bất đồng bộ sau khi giải phóng khóa
                        wait_needed = min_gap - gap

                if len(log) >= limit:
                    # Đạt giới hạn, tính toán thời gian chờ
                    wait_needed = max(wait_needed, 60 - (now - log[0]) + 0.1)

                if wait_needed == 0 and len(log) < limit:
                    # Nhận token thành công
                    log.append(now)
                    return

            # Chờ bất đồng bộ ngoài khóa
            if wait_needed > 0:
                await asyncio.sleep(wait_needed)
            else:
                await asyncio.sleep(0.1)  # Tạm thời nhường quyền kiểm soát


_SHARED_IMAGE_MODEL_NAME = cost_calculator.DEFAULT_IMAGE_MODEL
_SHARED_VIDEO_MODEL_NAME = cost_calculator.DEFAULT_VIDEO_MODEL

_shared_rate_limiter: Optional["RateLimiter"] = None
_shared_rate_limiter_lock = threading.Lock()


def _rate_limiter_limits_from_env(
    *,
    image_rpm: int | None = None,
    video_rpm: int | None = None,
    image_model: str | None = None,
    video_model: str | None = None,
) -> dict[str, int]:
    if image_rpm is None:
        image_rpm = 15
    if video_rpm is None:
        video_rpm = 10
    if image_model is None:
        image_model = _SHARED_IMAGE_MODEL_NAME
    if video_model is None:
        video_model = _SHARED_VIDEO_MODEL_NAME

    limits: dict[str, int] = {}
    if image_rpm > 0:
        limits[image_model] = image_rpm
    if video_rpm > 0:
        limits[video_model] = video_rpm
    return limits


def get_shared_rate_limiter(
    *,
    image_rpm: int | None = None,
    video_rpm: int | None = None,
    image_model: str | None = None,
    video_model: str | None = None,
    request_gap: float | None = None,
) -> "RateLimiter":
    """
    Lấy RateLimiter được chia sẻ trong tiến trình

    Gọi lần đầu tiên sẽ tạo instance theo tham số hoặc biến môi trường, các lần gọi sau trả về cùng một instance.

    - image_rpm / video_rpm：Giới hạn số lần yêu cầu mỗi phút (None thì đọc từ biến môi trường)
    - request_gap：Khoảng cách tối thiểu giữa các yêu cầu (None thì đọc từ biến môi trường GEMINI_REQUEST_GAP, mặc định 3.1)
    """
    global _shared_rate_limiter
    if _shared_rate_limiter is not None:
        return _shared_rate_limiter

    with _shared_rate_limiter_lock:
        if _shared_rate_limiter is not None:
            return _shared_rate_limiter

        limits = _rate_limiter_limits_from_env(
            image_rpm=image_rpm,
            video_rpm=video_rpm,
            image_model=image_model,
            video_model=video_model,
        )
        if request_gap is None:
            request_gap = 3.1
        _shared_rate_limiter = RateLimiter(limits, request_gap=request_gap)
        return _shared_rate_limiter


def refresh_shared_rate_limiter(
    *,
    image_rpm: int | None = None,
    video_rpm: int | None = None,
    image_model: str | None = None,
    video_model: str | None = None,
    request_gap: float | None = None,
) -> "RateLimiter":
    """
    Refresh the process-wide shared RateLimiter in-place.

    Updates model keys and request_gap. Parameters default to env vars when None.
    """
    limiter = get_shared_rate_limiter()
    new_limits = _rate_limiter_limits_from_env(
        image_rpm=image_rpm,
        video_rpm=video_rpm,
        image_model=image_model,
        video_model=video_model,
    )

    with limiter.lock:
        limiter.limits = new_limits
        if request_gap is not None:
            limiter.request_gap = request_gap

    return limiter
