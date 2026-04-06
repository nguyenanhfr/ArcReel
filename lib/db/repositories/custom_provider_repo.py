"""Custom provider repository."""

from __future__ import annotations

from sqlalchemy import delete, select

from lib.db.models.custom_provider import CustomProvider, CustomProviderModel
from lib.db.repositories.base import BaseRepository


class CustomProviderRepository(BaseRepository):
    """nhà cung cấp tùy chỉnh + CRUD mô hình."""

    # ── Provider CRUD ──────────────────────────────────────────────

    async def create_provider(
        self,
        display_name: str,
        api_format: str,
        base_url: str,
        api_key: str,
        models: list[dict] | None = None,
    ) -> CustomProvider:
        """Tạonhà cung cấp，Tùy chọn đồng thời Tạo danh sách mô hình."""
        provider = CustomProvider(
            display_name=display_name,
            api_format=api_format,
            base_url=base_url,
            api_key=api_key,
        )
        self.session.add(provider)
        await self.session.flush()  # Lấy provider.id

        if models:
            for m in models:
                model = CustomProviderModel(provider_id=provider.id, **m)
                self.session.add(model)
            await self.session.flush()

        return provider

    async def get_provider(self, provider_id: int) -> CustomProvider | None:
        stmt = select(CustomProvider).where(CustomProvider.id == provider_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_providers(self) -> list[CustomProvider]:
        stmt = select(CustomProvider).order_by(CustomProvider.id)
        result = await self.session.execute(stmt)
        return list(result.scalars())

    async def update_provider(self, provider_id: int, **kwargs) -> CustomProvider | None:
        """Cập nhật nhà cung cấp từ phần. Trả về đối tượng đã cập nhật, nếu không tồn tại trả về None."""
        provider = await self.get_provider(provider_id)
        if provider is None:
            return None
        for key, value in kwargs.items():
            setattr(provider, key, value)
        return provider

    async def delete_provider(self, provider_id: int) -> None:
        """Xóanhà cung cấpVà tất cả mô hình của nó.

        Xóa mô hình rõ ràng thay vì phụ thuộc FK CASCADE, vì SQLite mặc định không bật pragma foreign_keys.
        """
        await self.session.execute(delete(CustomProviderModel).where(CustomProviderModel.provider_id == provider_id))
        await self.session.execute(delete(CustomProvider).where(CustomProvider.id == provider_id))
        await self.session.flush()

    # ── Model management ──────────────────────────────────────────

    async def list_models(self, provider_id: int) -> list[CustomProviderModel]:
        stmt = (
            select(CustomProviderModel)
            .where(CustomProviderModel.provider_id == provider_id)
            .order_by(CustomProviderModel.id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars())

    async def replace_models(self, provider_id: int, models: list[dict]) -> list[CustomProviderModel]:
        """XóaMô hình cũ, chèn danh sách mới. Trả về mô hình mới được tạo."""
        await self.session.execute(delete(CustomProviderModel).where(CustomProviderModel.provider_id == provider_id))
        new_models = []
        for m in models:
            model = CustomProviderModel(provider_id=provider_id, **m)
            self.session.add(model)
            new_models.append(model)
        await self.session.flush()
        return new_models

    async def update_model(self, model_id: int, **kwargs) -> CustomProviderModel | None:
        """Cập nhật mô hình từ phần. Trả về đối tượng đã cập nhật, nếu không tồn tại trả về None."""
        stmt = select(CustomProviderModel).where(CustomProviderModel.id == model_id)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        for key, value in kwargs.items():
            setattr(model, key, value)
        return model

    async def delete_model(self, model_id: int) -> None:
        """XóaMột mô hình đơn."""
        await self.session.execute(delete(CustomProviderModel).where(CustomProviderModel.id == model_id))
        await self.session.flush()

    async def list_all_enabled_models(self) -> list[CustomProviderModel]:
        """Lấy tất cả mô hình đã kích hoạt trên tất cả nhà cung cấp."""
        stmt = (
            select(CustomProviderModel)
            .where(CustomProviderModel.is_enabled == True)  # noqa: E712
            .order_by(CustomProviderModel.provider_id, CustomProviderModel.id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars())

    async def list_providers_with_models(self) -> list[tuple[CustomProvider, list[CustomProviderModel]]]:
        """Lấy tất cả nhà cung cấp và mô hình của họ, chỉ cần 2 truy vấn."""
        providers = await self.list_providers()
        if not providers:
            return []
        provider_ids = [p.id for p in providers]
        stmt = (
            select(CustomProviderModel)
            .where(CustomProviderModel.provider_id.in_(provider_ids))
            .order_by(CustomProviderModel.provider_id, CustomProviderModel.id)
        )
        result = await self.session.execute(stmt)
        all_models = list(result.scalars())

        models_by_provider: dict[int, list[CustomProviderModel]] = {p.id: [] for p in providers}
        for m in all_models:
            models_by_provider.setdefault(m.provider_id, []).append(m)
        return [(p, models_by_provider.get(p.id, [])) for p in providers]

    async def list_enabled_models_by_media_type(self, media_type: str) -> list[CustomProviderModel]:
        """Lấy các mô hình đã kích hoạt của loại phương tiện chỉ định trên tất cả nhà cung cấp."""
        stmt = (
            select(CustomProviderModel)
            .where(
                CustomProviderModel.media_type == media_type,
                CustomProviderModel.is_enabled == True,  # noqa: E712
            )
            .order_by(CustomProviderModel.id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars())

    async def get_model_by_ids(self, provider_id: int, model_id: str) -> CustomProviderModel | None:
        """Dựa theo nhà cung cấp ID và Mã mẫu để lấy một mô hình."""
        stmt = select(CustomProviderModel).where(
            CustomProviderModel.provider_id == provider_id,
            CustomProviderModel.model_id == model_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_default_model(self, provider_id: int, media_type: str) -> CustomProviderModel | None:
        """Lấy mô hình mặc định đã kích hoạt cho nhà cung cấp + loại phương tiện chỉ định."""
        stmt = select(CustomProviderModel).where(
            CustomProviderModel.provider_id == provider_id,
            CustomProviderModel.media_type == media_type,
            CustomProviderModel.is_default == True,  # noqa: E712
            CustomProviderModel.is_enabled == True,  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
