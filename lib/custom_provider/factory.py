"""nhà cung cấp tùy chỉnh Backend Nhà máy.

Tạo phiên bản Backend đã đóng gói dựa trên cấu hình CustomProvider.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lib.config.url_utils import ensure_google_base_url, ensure_openai_base_url
from lib.custom_provider.backends import CustomImageBackend, CustomTextBackend, CustomVideoBackend
from lib.image_backends.gemini import GeminiImageBackend
from lib.image_backends.openai import OpenAIImageBackend
from lib.text_backends.gemini import GeminiTextBackend
from lib.text_backends.openai import OpenAITextBackend
from lib.video_backends.gemini import GeminiVideoBackend
from lib.video_backends.openai import OpenAIVideoBackend

if TYPE_CHECKING:
    from lib.db.models.custom_provider import CustomProvider

_VALID_MEDIA_TYPES = {"text", "image", "video"}
_VALID_API_FORMATS = {"openai", "google"}


def create_custom_backend(
    *,
    provider: CustomProvider,
    model_id: str,
    media_type: str,
) -> CustomTextBackend | CustomImageBackend | CustomVideoBackend:
    """Tạo phiên bản Backend đã đóng gói dựa trên cấu hình nhà cung cấp tùy chỉnh.

    Args:
        provider: nhà cung cấp tùy chỉnh ORM 对象
        model_id: Mã mẫu sẽ sử dụng
        media_type: Loại phương tiện ("text" | "image" | "video")

    Returns:
        Phiên bản Custom*Backend đã đóng gói

    Raises:
        ValueError: api_format Hoặc media_type không hợp lệ
    """
    api_format = provider.api_format
    if api_format not in _VALID_API_FORMATS:
        raise ValueError(f"Định dạng api không được hỗ trợ: {api_format!r}，Hỗ trợ: {_VALID_API_FORMATS}")
    if media_type not in _VALID_MEDIA_TYPES:
        raise ValueError(f"media_type không được hỗ trợ: {media_type!r}，Hỗ trợ: {_VALID_MEDIA_TYPES}")

    if api_format == "openai":
        return _create_openai_backend(provider=provider, model_id=model_id, media_type=media_type)
    else:  # google
        return _create_google_backend(provider=provider, model_id=model_id, media_type=media_type)


def _create_openai_backend(
    *,
    provider: CustomProvider,
    model_id: str,
    media_type: str,
) -> CustomTextBackend | CustomImageBackend | CustomVideoBackend:
    """Tạo OpenAI định dạngHậu phương của."""
    pid = provider.provider_id
    base_url = ensure_openai_base_url(provider.base_url)
    if media_type == "text":
        delegate = OpenAITextBackend(api_key=provider.api_key, base_url=base_url, model=model_id)
        return CustomTextBackend(provider_id=pid, delegate=delegate, model=model_id)
    elif media_type == "image":
        delegate = OpenAIImageBackend(api_key=provider.api_key, base_url=base_url, model=model_id)
        return CustomImageBackend(provider_id=pid, delegate=delegate, model=model_id)
    else:  # video
        delegate = OpenAIVideoBackend(api_key=provider.api_key, base_url=base_url, model=model_id)
        return CustomVideoBackend(provider_id=pid, delegate=delegate, model=model_id)


def _create_google_backend(
    *,
    provider: CustomProvider,
    model_id: str,
    media_type: str,
) -> CustomTextBackend | CustomImageBackend | CustomVideoBackend:
    """Tạo Google định dạngHậu phương của."""
    base_url = ensure_google_base_url(provider.base_url) or None
    pid = provider.provider_id
    if media_type == "text":
        delegate = GeminiTextBackend(api_key=provider.api_key, base_url=base_url, model=model_id)
        return CustomTextBackend(provider_id=pid, delegate=delegate, model=model_id)
    elif media_type == "image":
        delegate = GeminiImageBackend(api_key=provider.api_key, base_url=base_url, image_model=model_id)
        return CustomImageBackend(provider_id=pid, delegate=delegate, model=model_id)
    else:  # video
        delegate = GeminiVideoBackend(api_key=provider.api_key, base_url=base_url, video_model=model_id)
        return CustomVideoBackend(provider_id=pid, delegate=delegate, model=model_id)
