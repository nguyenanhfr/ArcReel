"""
MediaGenerator lớp trung gian

Đóng gói GeminiClient + VersionManager, cung cấp"Người gọi không cảm nhận được"Quản lý phiên bản.
Người gọi chỉ cần truyền project_path và resource_id, Quản lý phiên bản sẽ tự động hoàn thành.

4 loại tài nguyên được bao phủ:
- storyboards: Ảnh phân cảnh (scene_E1S01.png)
- videos: Video (scene_E1S01.mp4)
- characters: Ảnh thiết kế nhân vật (gừng thì là.png)
- clues: Ảnh thiết kế manh mối (mặt dây chuyền ngọc bích.png)
"""

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from PIL import Image

if TYPE_CHECKING:
    from lib.config.resolver import ConfigResolver
    from lib.image_backends.base import ImageBackend

from lib.db.base import DEFAULT_USER_ID
from lib.gemini_shared import RateLimiter
from lib.usage_tracker import UsageTracker
from lib.version_manager import VersionManager

logger = logging.getLogger(__name__)


class MediaGenerator:
    """
    Lớp trung gian của trình tạo phương tiện

    Đóng gói GeminiClient + VersionManager, cung cấp quản lý phiên bản tự động.
    """

    # Loại tài nguyênĐến ánh xạ mẫu đường dẫn Đầu ra
    OUTPUT_PATTERNS = {
        "storyboards": "storyboards/scene_{resource_id}.png",
        "videos": "videos/scene_{resource_id}.mp4",
        "characters": "characters/{resource_id}.png",
        "clues": "clues/{resource_id}.png",
    }

    def __init__(
        self,
        project_path: Path,
        rate_limiter: RateLimiter | None = None,
        image_backend: Optional["ImageBackend"] = None,
        video_backend=None,
        *,
        config_resolver: Optional["ConfigResolver"] = None,
        user_id: str = DEFAULT_USER_ID,
    ):
        """
        Khởi tạo MediaGenerator

        Args:
            project_path: Dự ánĐường dẫn thư mục gốc
            rate_limiter: Ví dụ bộ điều tiết lưu lượng tùy chọn
            image_backend: Một thực thể ImageBackend tùy chọn (dùng để tạo Ảnh)
            video_backend: Ví dụ VideoBackend tùy chọn (dùng cho tạo Video)
            config_resolver: ConfigResolver Ví dụ, dùng để đọc cấu hình khi chạy
            user_id: ID người dùng
        """
        self.project_path = Path(project_path)
        self.project_name = self.project_path.name
        self._rate_limiter = rate_limiter
        self._image_backend = image_backend
        self._video_backend = video_backend
        self._config = config_resolver
        self._user_id = user_id
        self.versions = VersionManager(project_path)

        # Khởi tạo UsageTracker (sử dụng global async session factory)
        self.usage_tracker = UsageTracker()

    @staticmethod
    def _sync(coro):
        """Run an async coroutine from synchronous code (e.g. inside to_thread)."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, coro).result()
        return asyncio.run(coro)

    def _get_output_path(self, resource_type: str, resource_id: str) -> Path:
        """
        Suy ra đường dẫn đầu ra dựa trên loại tài nguyên và ID

        Args:
            resource_type: Loại tài nguyên (bảng phân cảnh, video, nhân vật, manh mối)
            resource_id: ID tài nguyên (E1S01, 姜月茴, dây chuyền ngọc bích)

        Returns:
            Đầu raĐường dẫn tuyệt đối của tệp
        """
        if resource_type not in self.OUTPUT_PATTERNS:
            raise ValueError(f"Loại tài nguyên không được hỗ trợ: {resource_type}")

        pattern = self.OUTPUT_PATTERNS[resource_type]
        relative_path = pattern.format(resource_id=resource_id)
        output_path = (self.project_path / relative_path).resolve()
        try:
            output_path.relative_to(self.project_path.resolve())
        except ValueError:
            raise ValueError(f"ID tài nguyên không hợp lệ: '{resource_id}'")
        return output_path

    def _ensure_parent_dir(self, output_path: Path) -> None:
        """Đảm bảo thư mục đầu ra tồn tại"""
        output_path.parent.mkdir(parents=True, exist_ok=True)

    def generate_image(
        self,
        prompt: str,
        resource_type: str,
        resource_id: str,
        reference_images=None,
        aspect_ratio: str = "9:16",
        image_size: str = "1K",
        **version_metadata,
    ) -> tuple[Path, int]:
        """
        Tạo Ảnh (kèm quản lý phiên bản tự động, gói đồng bộ)

        Args:
            prompt: ẢnhTạo Prompt
            resource_type: Loại tài nguyên (storyboards, characters, clues)
            resource_id: ID tài nguyên (E1S01, 姜月茴, dây chuyền ngọc bích)
            reference_images: Ảnh tham chiếuDanh sách mảnh
            aspect_ratio: Tỷ lệ khung hình, mặc định 9:16 (dọc)
            image_size: ẢnhKích thước, mặc định 1K
            **version_metadata: Metadata bổ sung

        Returns:
            (output_path, version_number) Bộ giá trị
        """
        return self._sync(
            self.generate_image_async(
                prompt=prompt,
                resource_type=resource_type,
                resource_id=resource_id,
                reference_images=reference_images,
                aspect_ratio=aspect_ratio,
                image_size=image_size,
                **version_metadata,
            )
        )

    async def generate_image_async(
        self,
        prompt: str,
        resource_type: str,
        resource_id: str,
        reference_images=None,
        aspect_ratio: str = "9:16",
        image_size: str = "1K",
        **version_metadata,
    ) -> tuple[Path, int]:
        """
        Tạo Ảnh bất đồng bộ (kèm quản lý phiên bản tự động)

        Args:
            prompt: ẢnhTạo Prompt
            resource_type: Loại tài nguyên (storyboards, characters, clues)
            resource_id: ID tài nguyên (E1S01, 姜月茴, dây chuyền ngọc bích)
            reference_images: Ảnh tham chiếuDanh sách mảnh
            aspect_ratio: Tỷ lệ khung hình, mặc định 9:16 (dọc)
            image_size: ẢnhKích thước, mặc định 1K
            **version_metadata: Metadata bổ sung

        Returns:
            (output_path, version_number) Bộ giá trị
        """
        from lib.image_backends.base import ImageGenerationRequest, ReferenceImage

        output_path = self._get_output_path(resource_type, resource_id)
        self._ensure_parent_dir(output_path)

        # 1. Nếu đã tồn tại, đảm bảo tập tin cũ được ghi lại
        if output_path.exists():
            self.versions.ensure_current_tracked(
                resource_type=resource_type,
                resource_id=resource_id,
                current_file=output_path,
                prompt=prompt,
                aspect_ratio=aspect_ratio,
                **version_metadata,
            )

        if self._image_backend is None:
            raise RuntimeError("image_backend not configured")

        # 2. Ghi lại bắt đầu gọi API
        call_id = await self.usage_tracker.start_call(
            project_name=self.project_name,
            call_type="image",
            model=self._image_backend.model,
            prompt=prompt,
            resolution=image_size,
            aspect_ratio=aspect_ratio,
            provider=self._image_backend.name,
            user_id=self._user_id,
            segment_id=resource_id if resource_type in ("storyboards", "videos") else None,
        )

        try:
            # 3. Chuyển đổi ảnh tham chiếu sang định dạng và gọi ImageBackend
            ref_images: list[ReferenceImage] = []
            if reference_images:
                for ref in reference_images:
                    if isinstance(ref, dict):
                        img_val = ref.get("image", "")
                        ref_images.append(
                            ReferenceImage(
                                path=str(img_val),
                                label=str(ref.get("label", "")),
                            )
                        )
                    elif hasattr(ref, "__fspath__") or isinstance(ref, (str, Path)):
                        ref_images.append(ReferenceImage(path=str(ref)))
                    # PIL Image Bỏ qua loại không được hỗ trợ

            request = ImageGenerationRequest(
                prompt=prompt,
                output_path=output_path,
                reference_images=ref_images,
                aspect_ratio=aspect_ratio,
                image_size=image_size,
                project_name=self.project_name,
            )
            result = await self._image_backend.generate(request)

            # 4. Ghi một cuộc gọi thành công
            await self.usage_tracker.finish_call(
                call_id=call_id,
                status="success",
                output_path=str(output_path),
                quality=getattr(result, "quality", None),
            )
        except Exception as e:
            # Ghi lại cuộc gọi thất bại
            logger.exception("Tạo thất bại (%s)", "image")
            await self.usage_tracker.finish_call(
                call_id=call_id,
                status="failed",
                error_message=str(e),
            )
            raise

        # 5. Ghi lại phiên bản mới
        new_version = self.versions.add_version(
            resource_type=resource_type,
            resource_id=resource_id,
            prompt=prompt,
            source_file=output_path,
            aspect_ratio=aspect_ratio,
            **version_metadata,
        )

        return output_path, new_version

    def generate_video(
        self,
        prompt: str,
        resource_type: str,
        resource_id: str,
        start_image: str | Path | Image.Image | None = None,
        aspect_ratio: str = "9:16",
        duration_seconds: str = "8",
        resolution: str = "1080p",
        negative_prompt: str = "background music, BGM, soundtrack, musical accompaniment",
        **version_metadata,
    ) -> tuple[Path, int, any, str | None]:
        """
        Tạo video（Với quản lý phiên bản tự động, đồng bộ gói

        Args:
            prompt: VideoTạo Prompt
            resource_type: Loại tài nguyên (videos)
            resource_id: ID tài nguyên (E1S01)
            start_image: Khung bắt đầu ảnh (chế độ image-to-video)
            aspect_ratio: Tỷ lệ khung hình, mặc định 9:16 (dọc)
            duration_seconds: VideoĐộ dài, tùy chọn "4", "6", "8"
            resolution: Độ phân giải, mặc định "1080p"
            negative_prompt: Prompt tiêu cực
            **version_metadata: Metadata bổ sung

        Returns:
            (output_path, version_number, video_ref, video_uri) Bộ bốn
        """
        return self._sync(
            self.generate_video_async(
                prompt=prompt,
                resource_type=resource_type,
                resource_id=resource_id,
                start_image=start_image,
                aspect_ratio=aspect_ratio,
                duration_seconds=duration_seconds,
                resolution=resolution,
                negative_prompt=negative_prompt,
                **version_metadata,
            )
        )

    async def generate_video_async(
        self,
        prompt: str,
        resource_type: str,
        resource_id: str,
        start_image: str | Path | Image.Image | None = None,
        aspect_ratio: str = "9:16",
        duration_seconds: str = "8",
        resolution: str = "1080p",
        negative_prompt: str = "background music, BGM, soundtrack, musical accompaniment",
        **version_metadata,
    ) -> tuple[Path, int, any, str | None]:
        """
        Tạo video bất đồng bộ (với quản lý phiên bản tự động)

        Args:
            prompt: VideoTạo Prompt
            resource_type: Loại tài nguyên (videos)
            resource_id: ID tài nguyên (E1S01)
            start_image: Khung bắt đầu ảnh (chế độ image-to-video)
            aspect_ratio: Tỷ lệ khung hình, mặc định 9:16 (dọc)
            duration_seconds: VideoĐộ dài, tùy chọn "4", "6", "8"
            resolution: Độ phân giải, mặc định "1080p"
            negative_prompt: Prompt tiêu cực
            **version_metadata: Metadata bổ sung

        Returns:
            (output_path, version_number, video_ref, video_uri) Bộ bốn
        """
        output_path = self._get_output_path(resource_type, resource_id)
        self._ensure_parent_dir(output_path)

        # 1. Nếu đã tồn tại, đảm bảo tập tin cũ được ghi lại
        if output_path.exists():
            self.versions.ensure_current_tracked(
                resource_type=resource_type,
                resource_id=resource_id,
                current_file=output_path,
                prompt=prompt,
                duration_seconds=duration_seconds,
                **version_metadata,
            )

        # 2. Ghi lại bắt đầu gọi API
        try:
            duration_int = int(duration_seconds) if duration_seconds else 8
        except (ValueError, TypeError):
            duration_int = 8

        if self._video_backend is None:
            raise RuntimeError("video_backend not configured")

        model_name = self._video_backend.model
        provider_name = self._video_backend.name
        configured_generate_audio = (
            await self._config.video_generate_audio(self.project_name) if self._config else False
        )
        effective_generate_audio = version_metadata.get("generate_audio", configured_generate_audio)

        call_id = await self.usage_tracker.start_call(
            project_name=self.project_name,
            call_type="video",
            model=model_name,
            prompt=prompt,
            resolution=resolution,
            duration_seconds=duration_int,
            aspect_ratio=aspect_ratio,
            generate_audio=effective_generate_audio,
            provider=provider_name,
            user_id=self._user_id,
            segment_id=resource_id if resource_type in ("storyboards", "videos") else None,
        )

        try:
            from lib.video_backends.base import VideoGenerationRequest

            request = VideoGenerationRequest(
                prompt=prompt,
                output_path=output_path,
                aspect_ratio=aspect_ratio,
                duration_seconds=duration_int,
                resolution=resolution,
                start_image=Path(start_image) if isinstance(start_image, (str, Path)) else None,
                generate_audio=effective_generate_audio,
                negative_prompt=negative_prompt,
                project_name=self.project_name,
                service_tier=version_metadata.get("service_tier", "default"),
                seed=version_metadata.get("seed"),
            )

            result = await self._video_backend.generate(request)
            video_ref = None
            video_uri = result.video_uri

            # Track usage with provider info
            await self.usage_tracker.finish_call(
                call_id=call_id,
                status="success",
                output_path=str(output_path),
                usage_tokens=result.usage_tokens,
                service_tier=version_metadata.get("service_tier", "default"),
                generate_audio=result.generate_audio,
            )
        except Exception as e:
            # Ghi lại cuộc gọi thất bại
            logger.exception("Tạo thất bại (%s)", "video")
            await self.usage_tracker.finish_call(
                call_id=call_id,
                status="failed",
                error_message=str(e),
            )
            raise

        # 5. Ghi lại phiên bản mới
        new_version = self.versions.add_version(
            resource_type=resource_type,
            resource_id=resource_id,
            prompt=prompt,
            source_file=output_path,
            duration_seconds=duration_seconds,
            **version_metadata,
        )

        return output_path, new_version, video_ref, video_uri
