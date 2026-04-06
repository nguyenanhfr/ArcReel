"""URL Chuẩn hóa hàm Công cụ."""

from __future__ import annotations

import re


def ensure_openai_base_url(url: str | None) -> str | None:
    """Tự động bổ sung hậu tố đường dẫn /v1 tương thích API OpenAI.

    Người dùng có thể chỉ điền ``https://api.example.com``，Nhưng OpenAI SDK mong đợi
    ``https://api.example.com/v1``。Hàm này tự động thêm khi thiếu đường dẫn phiên bản.
    """
    if not url:
        return url
    stripped = url.strip().rstrip("/")
    if not re.search(r"/v\d+$", stripped):
        stripped += "/v1"
    return stripped


def normalize_base_url(url: str | None) -> str | None:
    """Đảm bảo base_url kết thúc bằng /.

    Google genai SDK http_options.base_url yêu cầu kết thúc bằng /,
    Nếu không, việc ghép nối đường dẫn yêu cầu sẽ thất bại. Backend Gemini được cài đặt sẵn sử dụng hàm này.
    """
    if not url:
        return None
    url = url.strip()
    if not url:
        return None
    if not url.endswith("/"):
        url += "/"
    return url


def ensure_google_base_url(url: str | None) -> str | None:
    """Chuẩn hóa base_url của Google genai SDK.

    Google genai SDK Sẽ tự động ghép nối sau base_url ``api_version``(Mặc định ``v1beta``）。
    Nếu người dùng vô tình điền sai ``https://example.com/v1beta``，SDK Có thể ghép ra
    ``https://example.com/v1beta/v1beta/models``，nguyên nhânYêu cầu thất bại。

    Hàm này loại bỏ đường dẫn phiên bản ở cuối (ví dụ ``/v1beta``、``/v1``），và đảm bảo phần cuối có ``/``。
    """
    if not url:
        return None
    url = url.strip()
    if not url:
        return None
    url = url.rstrip("/")
    # Loại bỏ đường dẫn phiên bản ở cuối (/v1, /v1beta, /v1alpha, v.v.)
    url = re.sub(r"/v\d+\w*$", "", url)
    if not url.endswith("/"):
        url += "/"
    return url
