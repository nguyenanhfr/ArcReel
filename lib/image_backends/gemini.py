"""GeminiImageBackend — Logic tạo Ảnh được trích xuất từ GeminiClient."""

from __future__ import annotations

import json as json_module
import logging
import os
from pathlib import Path

from PIL import Image

from lib.config.url_utils import normalize_base_url
from lib.gemini_shared import VERTEX_SCOPES, RateLimiter, get_shared_rate_limiter, with_retry_async
from lib.image_backends.base import (
    ImageCapability,
    ImageGenerationRequest,
    ImageGenerationResult,
    ReferenceImage,
)
from lib.providers import PROVIDER_GEMINI
from lib.system_config import resolve_vertex_credentials_path

logger = logging.getLogger(__name__)

# Bỏ qua mẫu tên tập tin suy đoán Tên
SKIP_NAME_PATTERNS = ("scene_", "storyboard_", "output_")

# Mô hình Ảnh mặc định
DEFAULT_IMAGE_MODEL = "gemini-3.1-flash-image-preview"


class GeminiImageBackend:
    """Gemini ẢnhTạo backend, hỗ trợ AI Studio và Vertex AI."""

    def __init__(
        self,
        *,
        backend_type: str = "aistudio",
        api_key: str | None = None,
        rate_limiter: RateLimiter | None = None,
        image_model: str | None = None,
        base_url: str | None = None,
        credentials_path: str | None = None,
    ):
        from google import genai as _genai
        from google.genai import types as _types

        self._types = _types
        self._rate_limiter = rate_limiter or get_shared_rate_limiter()
        self._backend_type = backend_type.strip().lower()
        self._image_model = image_model or os.environ.get("GEMINI_IMAGE_MODEL", DEFAULT_IMAGE_MODEL)

        if self._backend_type == "vertex":
            from google.oauth2 import service_account

            credentials_file: Path | None = None
            if credentials_path:
                credentials_file = Path(credentials_path)
            else:
                credentials_file = resolve_vertex_credentials_path(Path(__file__).parent.parent.parent)

            if credentials_file is None:
                raise ValueError("Không tìm thấy Tệp thông tin xác thực Vertex AI")

            with open(credentials_file) as f:
                creds_data = json_module.load(f)
            project_id = creds_data.get("project_id")

            credentials = service_account.Credentials.from_service_account_file(
                str(credentials_file), scopes=VERTEX_SCOPES
            )

            self._client = _genai.Client(
                vertexai=True,
                project=project_id,
                location="global",
                credentials=credentials,
            )
        else:
            _api_key = api_key or os.environ.get("GEMINI_API_KEY")
            if not _api_key:
                raise ValueError("Gemini API Key Chưa cung cấp. Vui lòng cấu hình API Key trên trang 「Cài đặt toàn cục → nhà cung cấp」.")

            effective_base_url = normalize_base_url(base_url or os.environ.get("GEMINI_BASE_URL"))
            http_options = {"base_url": effective_base_url} if effective_base_url else None
            self._client = _genai.Client(api_key=_api_key, http_options=http_options)

        self._capabilities: set[ImageCapability] = {
            ImageCapability.TEXT_TO_IMAGE,
            ImageCapability.IMAGE_TO_IMAGE,
        }

    @property
    def name(self) -> str:
        return f"gemini-{self._backend_type}"

    @property
    def model(self) -> str:
        return self._image_model

    @property
    def capabilities(self) -> set[ImageCapability]:
        return self._capabilities

    @with_retry_async(max_attempts=5, backoff_seconds=(2, 4, 8, 16, 32))
    async def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        """Tạo Ảnh bất đồng bộ."""
        # 1. Giới hạn lưu lượng
        if self._rate_limiter:
            await self._rate_limiter.acquire_async(self._image_model)

        # 2. Xây dựng contents (Ảnh tham chiếu + prompt)
        contents = self._build_contents_with_labeled_refs(request.prompt, request.reference_images)

        # 3. Xây dựng cấu hình
        config = self._types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=self._types.ImageConfig(
                aspect_ratio=request.aspect_ratio,
                image_size=request.image_size,
            ),
        )

        # 4. Gọi API bất đồng bộ
        response = await self._client.aio.models.generate_content(
            model=self._image_model, contents=contents, config=config
        )

        # 5. Phân tích phản hồi và Lưu
        self._process_image_response(response, request.output_path)

        return ImageGenerationResult(
            image_path=request.output_path,
            provider=PROVIDER_GEMINI,
            model=self._image_model,
        )

    @staticmethod
    def _load_image_detached(image_path: str | Path) -> Image.Image:
        """Tải Ảnh từ đường dẫn và ngắt liên kết với handle tệp cơ sở."""
        with Image.open(image_path) as img:
            return img.copy()

    @staticmethod
    def _extract_name_from_path(image_path: str | Path) -> str | None:
        """Suy ra Tên từ đường dẫn Ảnh. Bỏ qua các tệp có tiền tố scene_/storyboard_/output_"""
        path = Path(image_path)
        filename = path.stem
        for pattern in SKIP_NAME_PATTERNS:
            if filename.startswith(pattern):
                return None
        return filename

    def _build_contents_with_labeled_refs(
        self,
        prompt: str,
        reference_images: list[ReferenceImage] | None = None,
    ) -> list:
        """
        Xây dựng danh sách contents với nhãn Tên.

        định dạng：[Nhãn1, Ảnh1, Nhãn2, Ảnh2, ..., prompt]
        """
        contents: list = []

        if reference_images:
            labeled_refs: list[str] = []
            for ref in reference_images:
                # Xác định nhãn
                label = ref.label.strip() if ref.label else ""
                name = label or self._extract_name_from_path(ref.path)

                if name:
                    labeled_refs.append(name)
                    contents.append(name)

                # Tải Ảnh
                loaded_img = self._load_image_detached(ref.path)
                contents.append(loaded_img)

            if labeled_refs:
                logger.debug("Ảnh tham chiếuNhãn đoạn: %s", ", ".join(labeled_refs))

        # prompt Đặt cuối cùng
        contents.append(prompt)
        return contents

    @staticmethod
    def _process_image_response(response, output_path: Path) -> Image.Image:
        """Phân tích phản hồi tạo Ảnh và Lưu vào tệp."""
        for part in response.parts:
            if part.inline_data is not None:
                image = part.as_image()
                output_path.parent.mkdir(parents=True, exist_ok=True)
                image.save(output_path)
                return image
        raise RuntimeError("API Không trả về Ảnh")
