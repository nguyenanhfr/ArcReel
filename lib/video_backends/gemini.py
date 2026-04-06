"""GeminiVideoBackend — Logic tạo Video được trích xuất từ GeminiClient."""

from __future__ import annotations

import asyncio
import io
import logging
import os
import time
from pathlib import Path
from typing import Any

from PIL import Image

from lib.config.url_utils import normalize_base_url
from lib.gemini_shared import VERTEX_SCOPES, RateLimiter, get_shared_rate_limiter, with_retry_async
from lib.providers import PROVIDER_GEMINI
from lib.retry import BASE_RETRYABLE_ERRORS, _should_retry
from lib.system_config import resolve_vertex_credentials_path
from lib.video_backends.base import (
    VideoCapability,
    VideoGenerationRequest,
    VideoGenerationResult,
)

logger = logging.getLogger(__name__)


class GeminiVideoBackend:
    """Gemini (Veo) VideoTạo backend."""

    def __init__(
        self,
        *,
        backend_type: str = "aistudio",
        api_key: str | None = None,
        rate_limiter: RateLimiter | None = None,
        video_model: str | None = None,
        base_url: str | None = None,
    ):
        from google import genai as _genai
        from google.genai import types as _types

        self._types = _types
        self._rate_limiter = rate_limiter or get_shared_rate_limiter()
        self._backend_type = backend_type.strip().lower()
        self._credentials = None
        self._project_id = None

        from lib.cost_calculator import cost_calculator

        self._video_model = video_model or os.environ.get("GEMINI_VIDEO_MODEL", cost_calculator.DEFAULT_VIDEO_MODEL)

        if self._backend_type == "vertex":
            import json as json_module

            from google.oauth2 import service_account

            credentials_file = resolve_vertex_credentials_path(Path(__file__).parent.parent.parent)
            if credentials_file is None:
                raise ValueError("Không tìm thấy Tệp thông tin xác thực Vertex AI")

            with open(credentials_file) as f:
                creds_data = json_module.load(f)
            self._project_id = creds_data.get("project_id")

            self._credentials = service_account.Credentials.from_service_account_file(
                str(credentials_file), scopes=VERTEX_SCOPES
            )

            self._client = _genai.Client(
                vertexai=True,
                project=self._project_id,
                location="global",
                credentials=self._credentials,
            )
        else:
            _api_key = api_key or os.environ.get("GEMINI_API_KEY")
            if not _api_key:
                raise ValueError("GEMINI_API_KEY Môi trườngBiến Chưa cài đặt")

            effective_base_url = normalize_base_url(base_url or os.environ.get("GEMINI_BASE_URL"))
            http_options = {"base_url": effective_base_url} if effective_base_url else None
            self._client = _genai.Client(api_key=_api_key, http_options=http_options)

        # Lưu trữ capabilities, tránh tạo set mới mỗi lần truy cập
        self._capabilities: set[VideoCapability] = {
            VideoCapability.TEXT_TO_VIDEO,
            VideoCapability.IMAGE_TO_VIDEO,
            VideoCapability.NEGATIVE_PROMPT,
            VideoCapability.VIDEO_EXTEND,
        }
        if self._backend_type == "vertex":
            self._capabilities.add(VideoCapability.GENERATE_AUDIO)

    @property
    def name(self) -> str:
        return f"gemini-{self._backend_type}"

    @property
    def model(self) -> str:
        return self._video_model

    @property
    def capabilities(self) -> set[VideoCapability]:
        return self._capabilities

    @staticmethod
    def _normalize_duration(duration_seconds: int) -> str:
        """Chuẩn hóa thành giá trị thời lượng rời rạc được Veo hỗ trợ: '4', '6', '8'。"""
        if duration_seconds <= 4:
            return "4"
        if duration_seconds <= 6:
            return "6"
        return "8"

    async def generate(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        """Tạo video。Tách giai đoạn Tạo và vòng lặp Thử lại để tránh lỗi nhất thời do nguyên nhân tái tạo nhiệm vụ."""
        operation = await self._create_task(request)
        return await self._poll_until_done(operation, request)

    @with_retry_async()
    async def _create_task(self, request: VideoGenerationRequest) -> Any:
        """Tạo Gemini VideoTạo nhiệm vụ (có bảo vệ Thử lại)."""
        # 1. Giới hạn lưu lượng
        if self._rate_limiter:
            await self._rate_limiter.acquire_async(self._video_model)

        # 2. duration Chuẩn hóa thành giá trị rời rạc được Veo hỗ trợ và chuyển sang chuỗi
        duration_str = self._normalize_duration(request.duration_seconds)

        # 3. Xây dựng cấu hình
        config_params: dict = {
            "aspect_ratio": request.aspect_ratio,
            "resolution": request.resolution,
            "duration_seconds": duration_str,
            "negative_prompt": request.negative_prompt or "music, BGM, background music, subtitles, low quality",
        }
        if self._backend_type == "vertex":
            config_params["generate_audio"] = request.generate_audio
        config = self._types.GenerateVideosConfig(**config_params)

        # 4. Chuẩn bị nguồn (prompt + khung bắt đầu tùy chọn)
        image_param = self._prepare_image_param(request.start_image) if request.start_image else None
        source = self._types.GenerateVideosSource(prompt=request.prompt, image=image_param)

        # 5. Gọi API
        operation = await self._client.aio.models.generate_videos(model=self._video_model, source=source, config=config)
        op_name = getattr(operation, "name", "unknown")
        logger.info("VideoTạo xong, operation=%s", op_name)
        return operation

    async def _poll_until_done(self, operation: Any, request: VideoGenerationRequest) -> VideoGenerationResult:
        """Vòng lặp trạng thái nhiệm vụ đến khi Hoàn thành, lỗi nhất thời chỉ Thử lại trong lần vòng lặp đó."""
        op_name = getattr(operation, "name", "unknown")
        logger.info("Bắt đầu kiểm tra operation=%s ...", op_name)

        start_time = time.monotonic()
        poll_interval = 20  # Đúng theo đề xuất chính thức của Google
        max_wait_time = 600
        while not operation.done:
            elapsed = time.monotonic() - start_time
            if elapsed >= max_wait_time:
                raise TimeoutError(f"VideoTạo vượt quá thời gian ({max_wait_time}秒）")
            await asyncio.sleep(poll_interval)
            try:
                operation = await self._client.aio.operations.get(operation)
            except Exception as e:
                if _should_retry(e, BASE_RETRYABLE_ERRORS):
                    logger.warning("Gemini Vòng lặp bất thường (sẽ Thử lại): %s - %s", type(e).__name__, str(e)[:200])
                    continue
                raise
            if not operation.done:
                elapsed = time.monotonic() - start_time
                logger.info(
                    "VideoĐang tạo... Đã chờ %.0f giây (operation=%s)",
                    elapsed,
                    op_name,
                )

        total_elapsed = time.monotonic() - start_time
        logger.info("VideoTạo xong, tổng thời gian %.0f giây, operation=%s", total_elapsed, op_name)

        # Kết quả kiểm tra
        if not operation.response or not operation.response.generated_videos:
            error_detail = getattr(operation, "error", None)
            metadata = getattr(operation, "metadata", None)
            logger.error(
                "VideoTạo ra trả về kết quả rỗng: operation=%s, error=%s, metadata=%s, elapsed=%.0f giây",
                op_name,
                error_detail,
                metadata,
                total_elapsed,
            )
            if error_detail:
                raise RuntimeError(f"VideoTạo thất bại: {error_detail}")
            raise RuntimeError("VideoTạo thất bại: API trả về kết quả rỗng")

        # Trích xuất và tải Video xuống
        generated_video = operation.response.generated_videos[0]
        video_ref = generated_video.video
        video_uri = video_ref.uri if video_ref else None

        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        await self._download_video_with_retry(video_ref, request.output_path)

        return VideoGenerationResult(
            video_path=request.output_path,
            provider=PROVIDER_GEMINI,
            model=self._video_model,
            duration_seconds=request.duration_seconds,
            video_uri=video_uri,
            generate_audio=request.generate_audio if self._backend_type == "vertex" else True,
        )

    # ------------------------------------------------------------------
    # Phương pháp hỗ trợ nội bộ (trích xuất từ GeminiClient)
    # ------------------------------------------------------------------

    def _prepare_image_param(self, image: str | Path | Image.Image | None):
        """Chuẩn bị tham số Ảnh để gọi API — trích xuất từ GeminiClient."""
        if image is None:
            return None

        mime_type_png = "image/png"

        if isinstance(image, (str, Path)):
            with open(image, "rb") as f:
                image_bytes = f.read()
            suffix = Path(image).suffix.lower()
            mime_types = {
                ".png": mime_type_png,
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".gif": "image/gif",
                ".webp": "image/webp",
            }
            mime_type = mime_types.get(suffix, mime_type_png)
            return self._types.Image(image_bytes=image_bytes, mime_type=mime_type)
        elif isinstance(image, Image.Image):
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            image_bytes = buffer.getvalue()
            return self._types.Image(image_bytes=image_bytes, mime_type=mime_type_png)
        else:
            return image

    @with_retry_async()
    async def _download_video_with_retry(self, video_ref, output_path: Path) -> None:
        """Tải Video xuống (bao gồm lỗi tạm thời, thử lại)."""
        await asyncio.to_thread(self._download_video, video_ref, output_path)

    def _download_video(self, video_ref, output_path: Path) -> None:
        """Tải Video xuống tệp cục bộ — trích xuất từ GeminiClient."""
        if self._backend_type == "vertex":
            if video_ref and hasattr(video_ref, "video_bytes") and video_ref.video_bytes:
                with open(output_path, "wb") as f:
                    f.write(video_ref.video_bytes)
            elif video_ref and hasattr(video_ref, "uri") and video_ref.uri:
                import urllib.request

                urllib.request.urlretrieve(video_ref.uri, str(output_path))
            else:
                raise RuntimeError("VideoTạo thành công nhưng không thể lấy dữ liệu Video")
        else:
            # AI Studio Chế độ: sử dụng files.download
            self._client.files.download(file=video_ref)
            video_ref.save(str(output_path))
