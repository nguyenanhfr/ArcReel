"""nhà cung cấp tùy chỉnh Backend Lớp bao bọc.

Bao bọc các backend sẵn có (OpenAI/Gemini, v.v.), tạo thành nhà cung cấp tùy chỉnh, ghi đè thuộc tính name và model.
"""

from __future__ import annotations

from lib.image_backends.base import ImageBackend, ImageCapability, ImageGenerationRequest, ImageGenerationResult
from lib.text_backends.base import TextBackend, TextCapability, TextGenerationRequest, TextGenerationResult
from lib.video_backends.base import VideoBackend, VideoCapability, VideoGenerationRequest, VideoGenerationResult


class CustomTextBackend:
    """nhà cung cấp tùy chỉnhVăn bảnTạo lớp bao bọc backend."""

    def __init__(self, *, provider_id: str, delegate: TextBackend, model: str) -> None:
        self._provider_id = provider_id
        self._delegate = delegate
        self._model = model

    @property
    def name(self) -> str:
        return self._provider_id

    @property
    def model(self) -> str:
        return self._model

    @property
    def capabilities(self) -> set[TextCapability]:
        return self._delegate.capabilities

    async def generate(self, request: TextGenerationRequest) -> TextGenerationResult:
        return await self._delegate.generate(request)


class CustomImageBackend:
    """nhà cung cấp tùy chỉnhẢnhTạo lớp bao bọc backend."""

    def __init__(self, *, provider_id: str, delegate: ImageBackend, model: str) -> None:
        self._provider_id = provider_id
        self._delegate = delegate
        self._model = model

    @property
    def name(self) -> str:
        return self._provider_id

    @property
    def model(self) -> str:
        return self._model

    @property
    def capabilities(self) -> set[ImageCapability]:
        return self._delegate.capabilities

    async def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        return await self._delegate.generate(request)


class CustomVideoBackend:
    """nhà cung cấp tùy chỉnhVideoTạo lớp bao bọc backend."""

    def __init__(self, *, provider_id: str, delegate: VideoBackend, model: str) -> None:
        self._provider_id = provider_id
        self._delegate = delegate
        self._model = model

    @property
    def name(self) -> str:
        return self._provider_id

    @property
    def model(self) -> str:
        return self._model

    @property
    def capabilities(self) -> set[VideoCapability]:
        return self._delegate.capabilities

    async def generate(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        return await self._delegate.generate(request)
