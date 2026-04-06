"""TextGenerator — Văn bảnTạo + lớp bao bọc theo dõi sử dụng.

Tương tự MediaGenerator, kết hợp TextBackend + UsageTracker,
Người gọi không cần quan tâm đến chi tiết theo dõi sử dụng.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from lib.text_backends.base import (
    TextGenerationRequest,
    TextGenerationResult,
    TextTaskType,
)
from lib.text_backends.factory import create_text_backend_for_task
from lib.usage_tracker import UsageTracker

if TYPE_CHECKING:
    from lib.text_backends.base import TextBackend

logger = logging.getLogger(__name__)


class TextGenerator:
    """Kết hợp TextBackend + UsageTracker, bao bọc thống nhất việc tạo văn bản + theo dõi sử dụng."""

    def __init__(self, backend: TextBackend, usage_tracker: UsageTracker):
        self.backend = backend
        self.usage_tracker = usage_tracker

    @property
    def model(self) -> str:
        """Hiện tại backend Tên mô hình."""
        return self.backend.model

    @classmethod
    async def create(
        cls,
        task_type: TextTaskType,
        project_name: str | None = None,
    ) -> TextGenerator:
        """Phương thức nhà máy: tạo backend + usage_tracker tương ứng theo loại nhiệm vụ."""
        backend = await create_text_backend_for_task(task_type, project_name)
        usage_tracker = UsageTracker()
        return cls(backend, usage_tracker)

    async def generate(
        self,
        request: TextGenerationRequest,
        project_name: str | None = None,
    ) -> TextGenerationResult:
        """Tạo văn bản và tự động ghi nhận mức sử dụng."""
        call_id = await self.usage_tracker.start_call(
            project_name=project_name or "",
            call_type="text",
            model=self.backend.model,
            prompt=request.prompt[:500],
            provider=self.backend.name,
        )
        try:
            result = await self.backend.generate(request)
            await self.usage_tracker.finish_call(
                call_id,
                status="success",
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
            )
            return result
        except Exception as e:
            await self.usage_tracker.finish_call(
                call_id,
                status="failed",
                error_message=str(e)[:500],
            )
            raise
