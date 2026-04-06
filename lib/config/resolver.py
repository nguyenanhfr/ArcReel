"""Bộ phân tích cấu hình runtime đồng nhất.

Tập trung các cấu hình và giá trị mặc định phân tán trên nhiều tệp vào một nơi.
Mỗi lần gọi sẽ đọc từ DB, không lưu trữ đệm (chi phí SQLite cục bộ có thể bỏ qua).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

from sqlalchemy.ext.asyncio import AsyncSession

from lib.config.registry import PROVIDER_REGISTRY
from lib.config.service import (
    _DEFAULT_IMAGE_BACKEND,
    _DEFAULT_TEXT_BACKEND,
    _DEFAULT_VIDEO_BACKEND,
    ConfigService,
)
from lib.db.repositories.credential_repository import CredentialRepository
from lib.env_init import PROJECT_ROOT
from lib.project_manager import ProjectManager
from lib.text_backends.base import TextTaskType

_project_manager: ProjectManager | None = None


def get_project_manager() -> ProjectManager:
    """Trả về singleton ProjectManager chung (sử dụng thư mục gốc Dự án tiêu chuẩn)."""
    global _project_manager
    if _project_manager is None:
        _project_manager = ProjectManager(PROJECT_ROOT / "projects")
    return _project_manager


logger = logging.getLogger(__name__)

# Tập hợp các giá trị truthy để phân tích chuỗi boolean
_TRUTHY = frozenset({"true", "1", "yes"})


def _parse_bool(raw: str) -> bool:
    """Phân tích chuỗi cấu hình thành giá trị boolean."""
    return raw.strip().lower() in _TRUTHY


_TEXT_TASK_SETTING_KEYS: dict[TextTaskType, str] = {
    TextTaskType.SCRIPT: "text_backend_script",
    TextTaskType.OVERVIEW: "text_backend_overview",
    TextTaskType.STYLE_ANALYSIS: "text_backend_style",
}


class ConfigResolver:
    """Trình phân tích cấu hình thời gian chạy.

    Là một lớp bọc mỏng bên trên ConfigService, cung cấp:
    - Điểm định nghĩa giá trị mặc định duy nhất
    - LoạiHóa đầu ra (bool / tuple / dict)
    - Phân giải ưu tiên tích hợp sẵn (cấu hình toàn cục → ghi đè cấp dự án)
    """

    # ── Điểm định nghĩa giá trị mặc định duy nhất ──
    _DEFAULT_VIDEO_GENERATE_AUDIO = False

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    # ── API công khai: mở session mới mỗi lần gọi ──

    async def video_generate_audio(self, project_name: str | None = None) -> bool:
        """Phân giải video_generate_audio.

        Ưu tiên: ghi đè cấp dự án > Cấu hình toàn cục > Giá trị mặc định (False).
        """
        async with self._session_factory() as session:
            svc = ConfigService(session)
            return await self._resolve_video_generate_audio(svc, project_name)

    async def default_video_backend(self) -> tuple[str, str]:
        """Trả về (provider_id, model_id)."""
        async with self._session_factory() as session:
            svc = ConfigService(session)
            return await self._resolve_default_video_backend(svc)

    async def default_image_backend(self) -> tuple[str, str]:
        """Trả về (provider_id, model_id)."""
        async with self._session_factory() as session:
            svc = ConfigService(session)
            return await self._resolve_default_image_backend(svc)

    async def provider_config(self, provider_id: str) -> dict[str, str]:
        """Lấy cấu hình của một nhà cung cấp duy nhất."""
        async with self._session_factory() as session:
            svc = ConfigService(session)
            return await self._resolve_provider_config(svc, session, provider_id)

    async def all_provider_configs(self) -> dict[str, dict[str, str]]:
        """Lấy cấu hình của tất cả nhà cung cấp theo lô."""
        async with self._session_factory() as session:
            svc = ConfigService(session)
            return await self._resolve_all_provider_configs(svc, session)

    # ── Phương thức phân giải nội bộ (có thể kiểm thử độc lập, nhận svc đã tạo) ──

    async def _resolve_video_generate_audio(
        self,
        svc: ConfigService,
        project_name: str | None,
    ) -> bool:
        raw = await svc.get_setting("video_generate_audio", "")
        value = _parse_bool(raw) if raw else self._DEFAULT_VIDEO_GENERATE_AUDIO

        if project_name:
            project = get_project_manager().load_project(project_name)
            override = project.get("video_generate_audio")
            if override is not None:
                if isinstance(override, str):
                    value = _parse_bool(override)
                else:
                    value = bool(override)

        return value

    async def _resolve_default_video_backend(self, svc: ConfigService) -> tuple[str, str]:
        raw = await svc.get_setting("default_video_backend", "")
        if raw and "/" in raw:
            return ConfigService._parse_backend(raw, _DEFAULT_VIDEO_BACKEND)
        return await self._auto_resolve_backend(svc, "video")

    async def _resolve_default_image_backend(self, svc: ConfigService) -> tuple[str, str]:
        raw = await svc.get_setting("default_image_backend", "")
        if raw and "/" in raw:
            return ConfigService._parse_backend(raw, _DEFAULT_IMAGE_BACKEND)
        return await self._auto_resolve_backend(svc, "image")

    async def _resolve_provider_config(
        self,
        svc: ConfigService,
        session: AsyncSession,
        provider_id: str,
    ) -> dict[str, str]:
        config = await svc.get_provider_config(provider_id)
        cred_repo = CredentialRepository(session)
        active = await cred_repo.get_active(provider_id)
        if active:
            active.overlay_config(config)
        return config

    async def _resolve_all_provider_configs(
        self,
        svc: ConfigService,
        session: AsyncSession,
    ) -> dict[str, dict[str, str]]:
        configs = await svc.get_all_provider_configs()
        cred_repo = CredentialRepository(session)
        active_creds = await cred_repo.get_active_credentials_bulk()
        for provider_id, cred in active_creds.items():
            cfg = configs.setdefault(provider_id, {})
            cred.overlay_config(cfg)
        return configs

    async def default_text_backend(self) -> tuple[str, str]:
        """Trả về (provider_id, model_id)."""
        async with self._session_factory() as session:
            svc = ConfigService(session)
            return await svc.get_default_text_backend()

    async def text_backend_for_task(
        self,
        task_type: TextTaskType,
        project_name: str | None = None,
    ) -> tuple[str, str]:
        """Phân tích Văn bản backend. Ưu tiên: Cấu hình nhiệm vụ cấp Dự án → Cấu hình nhiệm vụ toàn cục → Mặc định toàn cục → Suy luận tự động"""
        async with self._session_factory() as session:
            svc = ConfigService(session)
            return await self._resolve_text_backend(svc, task_type, project_name)

    async def _resolve_text_backend(
        self,
        svc: ConfigService,
        task_type: TextTaskType,
        project_name: str | None,
    ) -> tuple[str, str]:
        setting_key = _TEXT_TASK_SETTING_KEYS[task_type]

        # 1. Project-level task override
        if project_name:
            project = get_project_manager().load_project(project_name)
            project_val = project.get(setting_key)
            if project_val and "/" in str(project_val):
                return ConfigService._parse_backend(str(project_val), _DEFAULT_TEXT_BACKEND)

        # 2. Global task-type setting
        task_val = await svc.get_setting(setting_key, "")
        if task_val and "/" in task_val:
            return ConfigService._parse_backend(task_val, _DEFAULT_TEXT_BACKEND)

        # 3. Global default text backend
        default_val = await svc.get_setting("default_text_backend", "")
        if default_val and "/" in default_val:
            return ConfigService._parse_backend(default_val, _DEFAULT_TEXT_BACKEND)

        # 4. Auto-resolve
        return await self._auto_resolve_backend(svc, "text")

    async def _auto_resolve_backend(
        self,
        svc: ConfigService,
        media_type: str,
    ) -> tuple[str, str]:
        """Duyệt qua PROVIDER_REGISTRY (theo thứ tự đăng ký), tìm một nhà cung cấp ready và hỗ trợ media_type đó."""
        statuses = await svc.get_all_providers_status()
        ready = {s.name for s in statuses if s.status == "ready"}

        for provider_id, meta in PROVIDER_REGISTRY.items():
            if provider_id not in ready:
                continue
            for model_id, model_info in meta.models.items():
                if model_info.media_type == media_type and model_info.default:
                    return provider_id, model_id

        if getattr(self, "_session_factory", None) is not None:
            from lib.custom_provider import make_provider_id
            from lib.db.repositories.custom_provider_repo import CustomProviderRepository

            async with self._session_factory() as session:
                repo = CustomProviderRepository(session)
                custom_models = await repo.list_enabled_models_by_media_type(media_type)
                for model in custom_models:
                    if model.is_default:
                        return make_provider_id(model.provider_id), model.model_id

        raise ValueError(f"Không tìm thấy nhà cung cấp khả dụng {media_type} nhà cung cấp。Vui lòng cấu hình ít nhất một nhà cung cấp trên trang 「Cài đặt toàn cục → nhà cung cấp」.")
