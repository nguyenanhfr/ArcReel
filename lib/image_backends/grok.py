"""GrokImageBackend — xAI Grok (Aurora) ẢnhTạo backend."""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

from lib.grok_shared import create_grok_client
from lib.image_backends.base import (
    ImageCapability,
    ImageGenerationRequest,
    ImageGenerationResult,
    image_to_base64_data_uri,
)
from lib.providers import PROVIDER_GROK
from lib.retry import with_retry_async

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "grok-imagine-image"

_SUPPORTED_ASPECT_RATIOS = {
    "1:1",
    "16:9",
    "9:16",
    "4:3",
    "3:4",
    "3:2",
    "2:3",
    "2:1",
    "1:2",
    "19.5:9",
    "9:19.5",
    "20:9",
    "9:20",
    "auto",
}


def _validate_aspect_ratio(aspect_ratio: str) -> str:
    """Kiểm tra aspect_ratio có nằm trong danh sách hỗ trợ của Grok hay không, nếu không hỗ trợ thì cảnh báo và truyền tiếp."""
    if aspect_ratio not in _SUPPORTED_ASPECT_RATIOS:
        logger.warning("Grok Có thể không hỗ trợ aspect_ratio=%s, sẽ truyền tiếp đến API", aspect_ratio)
    return aspect_ratio


class GrokImageBackend:
    """xAI Grok (Aurora) ẢnhTạo backend, hỗ trợ T2I và I2I."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
    ):
        self._client = create_grok_client(api_key=api_key)
        self._model = model or DEFAULT_MODEL
        self._capabilities: set[ImageCapability] = {
            ImageCapability.TEXT_TO_IMAGE,
            ImageCapability.IMAGE_TO_IMAGE,
        }

    @property
    def name(self) -> str:
        return PROVIDER_GROK

    @property
    def model(self) -> str:
        return self._model

    @property
    def capabilities(self) -> set[ImageCapability]:
        return self._capabilities

    @with_retry_async()
    async def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        """Tạo Ảnh (T2I hoặc I2I)."""
        generate_kwargs: dict = {
            "prompt": request.prompt,
            "model": self._model,
            "aspect_ratio": _validate_aspect_ratio(request.aspect_ratio),
            "resolution": _map_image_size_to_resolution(request.image_size),
        }

        # I2I：Chuyển tất cả Ảnh tham chiếu thành danh sách dữ liệu URI base64
        if request.reference_images:
            data_uris = []
            for ref in request.reference_images:
                ref_path = Path(ref.path)
                if ref_path.exists():
                    data_uris.append(image_to_base64_data_uri(ref_path))
            if data_uris:
                generate_kwargs["image_urls"] = data_uris
                logger.info("Grok I2I Chế độ: %d Ảnh tham chiếu", len(data_uris))

        logger.info("Grok ẢnhBắt đầu tạo: model=%s", self._model)
        response = await self._client.image.sample(**generate_kwargs)

        # Kiểm tra đánh giá
        if not response.respect_moderation:
            raise RuntimeError("Grok ẢnhTạo bị từ chối bởi kiểm duyệt nội dung")

        # Tải Ảnh về máy
        await _download_image(response.url, request.output_path)

        logger.info("Grok ẢnhTải xong: %s", request.output_path)

        return ImageGenerationResult(
            image_path=request.output_path,
            provider=PROVIDER_GROK,
            model=self._model,
            image_uri=response.url,
        )


def _map_image_size_to_resolution(image_size: str) -> str:
    """Chuyển kích thước hình ảnh chung (như '1K', '2K'）Ánh xạ thành tham số resolution của Grok."""
    mapping = {
        "1K": "1k",
        "2K": "2k",
        "1k": "1k",
        "2k": "2k",
    }
    return mapping.get(image_size, "1k")


async def _download_image(url: str, output_path: Path, *, timeout: int = 60) -> None:
    """Tải Ảnh từ URL về tệp cục bộ."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient() as http_client:
        resp = await http_client.get(url, timeout=timeout)
        resp.raise_for_status()
        output_path.write_bytes(resp.content)
