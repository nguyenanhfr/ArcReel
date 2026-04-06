"""VideoTạo định nghĩa giao diện cốt lõi của lớp dịch vụ."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

import httpx

from lib.retry import with_retry_async

# ẢnhBản đồ hậu tố → Loại MIME (dùng chung cho nhiều backend)
IMAGE_MIME_TYPES: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


@with_retry_async()
async def download_video(url: str, output_path: Path, *, timeout: int = 120) -> None:
    """Tải Video từ URL về tệp cục bộ theo luồng (bao gồm lỗi nhất thời Thử lại)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient() as http_client:
        async with http_client.stream("GET", url, timeout=timeout) as resp:
            resp.raise_for_status()
            with open(output_path, "wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=65536):
                    f.write(chunk)


class VideoCapability(StrEnum):
    """VideoLiệt kê các khả năng được hỗ trợ bởi backend."""

    TEXT_TO_VIDEO = "text_to_video"
    IMAGE_TO_VIDEO = "image_to_video"
    GENERATE_AUDIO = "generate_audio"
    NEGATIVE_PROMPT = "negative_prompt"
    VIDEO_EXTEND = "video_extend"
    SEED_CONTROL = "seed_control"
    FLEX_TIER = "flex_tier"


@dataclass
class VideoGenerationRequest:
    """Yêu cầu tạo Video chung. Các Backend bỏ qua một số đoạn từ không được hỗ trợ."""

    prompt: str
    output_path: Path
    aspect_ratio: str = "9:16"
    duration_seconds: int = 5
    resolution: str = "1080p"
    start_image: Path | None = None
    generate_audio: bool = True

    # Veo Riêng
    negative_prompt: str | None = None

    # Dự ánbối cảnh（Dùng để xây dựng URL dịch vụ tệp, v.v.)
    project_name: str | None = None

    # Seedance Riêng
    service_tier: str = "default"
    seed: int | None = None


@dataclass
class VideoGenerationResult:
    """Kết quả tạo Video chung."""

    video_path: Path
    provider: str
    model: str
    duration_seconds: int

    video_uri: str | None = None
    seed: int | None = None
    usage_tokens: int | None = None
    task_id: str | None = None
    generate_audio: bool | None = None


class VideoBackend(Protocol):
    """VideoGiao thức backend tạo."""

    @property
    def name(self) -> str: ...

    @property
    def model(self) -> str: ...

    @property
    def capabilities(self) -> set[VideoCapability]: ...

    async def generate(self, request: VideoGenerationRequest) -> VideoGenerationResult: ...
