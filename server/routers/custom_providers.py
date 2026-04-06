"""
nhà cung cấp tùy chỉnhQuản lý API.

Cung cấp các nhà cung cấp tùy chỉnh CRUD, quản lý mô hình, khám phá mô hình và kiểm tra kết nối endpoint.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from lib.config.repository import mask_secret
from lib.custom_provider import make_provider_id
from lib.db import get_async_session
from lib.db.base import dt_to_iso
from lib.db.repositories.custom_provider_repo import CustomProviderRepository
from server.auth import CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/custom-providers", tags=["nhà cung cấp tùy chỉnh"])

_CONNECTION_TEST_TIMEOUT = 15  # 秒

_BACKEND_SETTING_KEYS = (
    "default_video_backend",
    "default_image_backend",
    "default_text_backend",
    "text_backend_script",
    "text_backend_overview",
    "text_backend_style",
)

# ---------------------------------------------------------------------------
# Pydantic 模型
# ---------------------------------------------------------------------------


class ModelInput(BaseModel):
    model_id: str
    display_name: str
    media_type: str  # "text" | "image" | "video"
    is_default: bool = False
    is_enabled: bool = True
    price_unit: str | None = None
    price_input: float | None = None
    price_output: float | None = None
    currency: str | None = None

    @model_validator(mode="after")
    def _check_price_consistency(self):
        if self.price_output is not None and self.price_input is None:
            raise ValueError("Cài đặt price_output Khi sử dụng phải đồng thời cài đặt price_input")
        return self


class CreateProviderRequest(BaseModel):
    display_name: str
    api_format: str  # "openai" or "google"
    base_url: str
    api_key: str
    models: list[ModelInput] = []


class UpdateProviderRequest(BaseModel):
    display_name: str | None = None
    base_url: str | None = None
    api_key: str | None = None


class FullUpdateProviderRequest(BaseModel):
    """PUT Cập nhật toàn bộ: metadata của provider + danh sách người mẫu trong cùng một giao dịch."""

    display_name: str
    base_url: str
    api_key: str | None = None  # None = Không sửa đổi
    models: list[ModelInput]


class ProviderConnectionRequest(BaseModel):
    api_format: str
    base_url: str
    api_key: str


class ReplaceModelsRequest(BaseModel):
    models: list[ModelInput]


class ModelResponse(BaseModel):
    id: int
    model_id: str
    display_name: str
    media_type: str
    is_default: bool
    is_enabled: bool
    price_unit: str | None = None
    price_input: float | None = None
    price_output: float | None = None
    currency: str | None = None


class ProviderResponse(BaseModel):
    id: int
    display_name: str
    api_format: str
    base_url: str
    api_key_masked: str
    models: list[ModelResponse]
    created_at: str | None = None


class ConnectionTestResponse(BaseModel):
    success: bool
    message: str
    model_count: int = 0


class DiscoverResponse(BaseModel):
    models: list[dict]


# ---------------------------------------------------------------------------
# Hàm hỗ trợ
# ---------------------------------------------------------------------------


def _model_to_response(m) -> ModelResponse:
    return ModelResponse(
        id=m.id,
        model_id=m.model_id,
        display_name=m.display_name,
        media_type=m.media_type,
        is_default=m.is_default,
        is_enabled=m.is_enabled,
        price_unit=m.price_unit,
        price_input=m.price_input,
        price_output=m.price_output,
        currency=m.currency,
    )


def _provider_to_response(provider, models) -> ProviderResponse:
    return ProviderResponse(
        id=provider.id,
        display_name=provider.display_name,
        api_format=provider.api_format,
        base_url=provider.base_url,
        api_key_masked=mask_secret(provider.api_key),
        models=[_model_to_response(m) for m in models],
        created_at=dt_to_iso(provider.created_at),
    )


def _cleanup_project_refs(prefix: str, setting_keys: tuple[str, ...]) -> None:
    """Xóa provider Sau đó, dọn dẹp tất cả các tham chiếu treo trong project.json của Dự án."""
    from lib.config.resolver import get_project_manager

    pm = get_project_manager()
    for proj_name in pm.list_projects():
        try:

            def _mutate(p: dict, _prefix=prefix, _keys=setting_keys) -> None:
                for key in _keys:
                    val = p.get(key, "")
                    if isinstance(val, str) and val.startswith(_prefix):
                        p.pop(key, None)

            pm.update_project(proj_name, _mutate)
        except Exception:
            pass  # đọcThất bạiHoặc Dự án không thể ghi, bỏ qua (không gây lỗi nghiêm trọng)


def _check_duplicate_model_ids(models: list[ModelInput]) -> None:
    """Kiểm tra trong danh sách người mẫu không có model_id trùng lặp và các mô hình kích hoạt có model_id hợp lệ."""
    seen: set[str] = set()
    for m in models:
        if m.is_enabled and not m.model_id.strip():
            raise HTTPException(status_code=422, detail="Model_id là bắt buộc đối với các mô hình đã bật")
        if m.model_id in seen:
            raise HTTPException(status_code=422, detail=f"model_id Trùng lặp: {m.model_id}")
        if m.model_id:
            seen.add(m.model_id)


def _check_unique_defaults(models: list[ModelInput]) -> None:
    """Kiểm tra mỗi media_type có nhiều nhất chỉ một mô hình is_default=True."""
    defaults_by_type: dict[str, list[str]] = {}
    for m in models:
        if m.is_default:
            defaults_by_type.setdefault(m.media_type, []).append(m.model_id)
    duplicates = {mt: ids for mt, ids in defaults_by_type.items() if len(ids) > 1}
    if duplicates:
        parts = [f"{mt}({', '.join(ids)})" for mt, ids in duplicates.items()]
        raise HTTPException(
            status_code=422,
            detail=f"Mỗi media_type chỉ có thể có tối đa một mô hình mặc định, xung đột: {'; '.join(parts)}",
        )


async def _invalidate_caches(request: Request) -> None:
    """Xóa bộ nhớ đệm instance backend + làm mới cấu hình giới hạn chuyển đổi worker."""
    from server.services.generation_tasks import invalidate_backend_cache

    invalidate_backend_cache()
    worker = getattr(request.app.state, "generation_worker", None)
    if worker:
        await worker.reload_limits()


# ---------------------------------------------------------------------------
# Provider CRUD
# ---------------------------------------------------------------------------


@router.get("")
async def list_providers(
    _user: CurrentUser,
    session: AsyncSession = Depends(get_async_session),
):
    """Liệt kê tất cả các nhà cung cấp tùy chỉnh (bao gồm danh sách người mẫu)."""
    repo = CustomProviderRepository(session)
    pairs = await repo.list_providers_with_models()
    return {"providers": [_provider_to_response(p, models) for p, models in pairs]}


@router.post("", status_code=201)
async def create_provider(
    body: CreateProviderRequest,
    request: Request,
    _user: CurrentUser,
    session: AsyncSession = Depends(get_async_session),
):
    """Tạonhà cung cấp tùy chỉnh，Có thể đồng thời tạo danh sách người mẫu."""
    if body.models:
        _check_duplicate_model_ids(body.models)
        _check_unique_defaults(body.models)
    repo = CustomProviderRepository(session)
    model_dicts = [m.model_dump() for m in body.models] if body.models else None
    provider = await repo.create_provider(
        display_name=body.display_name,
        api_format=body.api_format,
        base_url=body.base_url,
        api_key=body.api_key,
        models=model_dicts,
    )
    await session.commit()
    await _invalidate_caches(request)
    await session.refresh(provider)
    models = await repo.list_models(provider.id)
    return _provider_to_response(provider, models)


@router.get("/{provider_id}")
async def get_provider(
    provider_id: int,
    _user: CurrentUser,
    session: AsyncSession = Depends(get_async_session),
):
    """Lấy chi tiết một nhà cung cấp tùy chỉnh."""
    repo = CustomProviderRepository(session)
    provider = await repo.get_provider(provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="nhà cung cấp不存在")
    models = await repo.list_models(provider_id)
    return _provider_to_response(provider, models)


@router.patch("/{provider_id}")
async def update_provider(
    provider_id: int,
    body: UpdateProviderRequest,
    request: Request,
    _user: CurrentUser,
    session: AsyncSession = Depends(get_async_session),
):
    """Cập nhật cấu hình nhà cung cấp tùy chỉnh."""
    repo = CustomProviderRepository(session)
    kwargs = {}
    if body.display_name is not None:
        kwargs["display_name"] = body.display_name
    if body.base_url is not None:
        kwargs["base_url"] = body.base_url
    if body.api_key is not None:
        kwargs["api_key"] = body.api_key

    if not kwargs:
        raise HTTPException(status_code=400, detail="Cần cung cấp ít nhất một trường để cập nhật")

    provider = await repo.update_provider(provider_id, **kwargs)
    if provider is None:
        raise HTTPException(status_code=404, detail="nhà cung cấp不存在")

    await session.commit()
    await _invalidate_caches(request)
    await session.refresh(provider)
    models = await repo.list_models(provider_id)
    return _provider_to_response(provider, models)


@router.put("/{provider_id}")
async def full_update_provider(
    provider_id: int,
    body: FullUpdateProviderRequest,
    request: Request,
    _user: CurrentUser,
    session: AsyncSession = Depends(get_async_session),
):
    """Cập nhật nguyên tử metadata nhà cung cấp + Danh sách mẫu (giao dịch đơn)."""
    _check_duplicate_model_ids(body.models)
    _check_unique_defaults(body.models)
    repo = CustomProviderRepository(session)
    kwargs: dict = {"display_name": body.display_name, "base_url": body.base_url}
    if body.api_key is not None:
        kwargs["api_key"] = body.api_key
    provider = await repo.update_provider(provider_id, **kwargs)
    if provider is None:
        raise HTTPException(status_code=404, detail="nhà cung cấp不存在")
    model_dicts = [m.model_dump() for m in body.models]
    await repo.replace_models(provider_id, model_dicts)
    await session.commit()
    await _invalidate_caches(request)
    await session.refresh(provider)
    models = await repo.list_models(provider_id)
    return _provider_to_response(provider, models)


@router.delete("/{provider_id}", status_code=204)
async def delete_provider(
    provider_id: int,
    request: Request,
    _user: CurrentUser,
    session: AsyncSession = Depends(get_async_session),
):
    """Xóanhà cung cấp tùy chỉnh（Xóa mẫu theo chuỗi, làm sạch cấu hình mặc định treo."""
    repo = CustomProviderRepository(session)
    provider = await repo.get_provider(provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="nhà cung cấp不存在")
    prefix = f"{make_provider_id(provider_id)}/"
    await repo.delete_provider(provider_id)
    # Làm sạch cấu hình backend mặc định toàn cục tham chiếu đến nhà cung cấp này
    from lib.config.service import ConfigService

    svc = ConfigService(session)
    for key in _BACKEND_SETTING_KEYS:
        val = await svc.get_setting(key, "")
        if val and val.startswith(prefix):
            await svc.set_setting(key, "")
    await session.commit()
    await _invalidate_caches(request)
    # Làm sạch cấu hình cấp dự án tham chiếu đến nhà cung cấp này (I/O tệp đồng bộ, đưa vào thread pool để tránh chặn vòng lặp sự kiện)
    await asyncio.to_thread(_cleanup_project_refs, prefix, _BACKEND_SETTING_KEYS)


# ---------------------------------------------------------------------------
# Model management
# ---------------------------------------------------------------------------


@router.put("/{provider_id}/models")
async def replace_models(
    provider_id: int,
    body: ReplaceModelsRequest,
    request: Request,
    _user: CurrentUser,
    session: AsyncSession = Depends(get_async_session),
):
    """Thay thếnhà cung cấpToàn bộ Danh sách mẫu."""
    _check_duplicate_model_ids(body.models)
    _check_unique_defaults(body.models)
    repo = CustomProviderRepository(session)
    provider = await repo.get_provider(provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="nhà cung cấp不存在")
    # Ghi lại Mã mẫu cũ, dùng để làm sạch tham chiếu treo
    old_models = await repo.list_models(provider_id)
    old_model_ids = {m.model_id for m in old_models}
    new_model_ids = {m.model_id for m in body.models}
    deleted_model_ids = old_model_ids - new_model_ids

    model_dicts = [m.model_dump() for m in body.models]
    new_models = await repo.replace_models(provider_id, model_dicts)

    # Làm sạch cấu hình toàn cục tham chiếu tới mô hình đã xóa
    if deleted_model_ids:
        from lib.config.service import ConfigService

        svc = ConfigService(session)
        prefix = f"{make_provider_id(provider_id)}/"
        for key in _BACKEND_SETTING_KEYS:
            val = await svc.get_setting(key, "")
            if val and val.startswith(prefix):
                _, model_part = val.split("/", 1)
                if model_part in deleted_model_ids:
                    await svc.set_setting(key, "")

    await session.commit()
    await _invalidate_caches(request)
    return [_model_to_response(m) for m in new_models]


# ---------------------------------------------------------------------------
# Hoạt động vô trạng thái
# ---------------------------------------------------------------------------


@router.post("/discover")
async def discover_models_endpoint(
    body: ProviderConnectionRequest,
    _user: CurrentUser,
):
    """Khám phá mẫu: Dựa trên api_format + base_url + api_key truy vấn các mẫu có sẵn."""
    from lib.custom_provider.discovery import discover_models

    try:
        models = await discover_models(
            api_format=body.api_format,
            base_url=body.base_url or None,
            api_key=body.api_key,
        )
        return DiscoverResponse(models=models)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        err_msg = str(exc)
        if len(err_msg) > 200:
            err_msg = err_msg[:200] + "..."
        logger.warning("Khám phá mẫu thất bại: %s", err_msg)
        raise HTTPException(status_code=502, detail=f"Khám phá mẫu thất bại: {err_msg}")


@router.post("/test")
async def test_connection(
    body: ProviderConnectionRequest,
    _user: CurrentUser,
):
    """kết nốiKiểm tra: Xác thực kết nối của api_format + base_url + api_key."""
    return await _run_connection_test(body.api_format, body.base_url, body.api_key)


@router.post("/{provider_id}/test")
async def test_connection_by_id(
    provider_id: int,
    _user: CurrentUser,
    session: AsyncSession = Depends(get_async_session),
):
    """Sử dụng thông tin đăng nhập đã lưu để kiểm tra kết nối với nhà cung cấp được chỉ định."""
    repo = CustomProviderRepository(session)
    provider = await repo.get_provider(provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="nhà cung cấp不存在")
    return await _run_connection_test(provider.api_format, provider.base_url, provider.api_key)


async def _run_connection_test(api_format: str, base_url: str, api_key: str) -> ConnectionTestResponse:
    """Chia sẻ logic kiểm tra kết nối."""
    try:
        if api_format == "openai":
            result = await asyncio.wait_for(
                asyncio.to_thread(_test_openai, base_url, api_key),
                timeout=_CONNECTION_TEST_TIMEOUT,
            )
        elif api_format == "google":
            result = await asyncio.wait_for(
                asyncio.to_thread(_test_google, base_url, api_key),
                timeout=_CONNECTION_TEST_TIMEOUT,
            )
        else:
            return ConnectionTestResponse(
                success=False,
                message=f"Định dạng api không được hỗ trợ: {api_format}",
            )
        return result
    except TimeoutError:
        return ConnectionTestResponse(
            success=False,
            message="kết nốiHết thời gian chờ, vui lòng kiểm tra mạng hoặc cấu hình API",
        )
    except Exception as exc:
        err_msg = str(exc)
        if len(err_msg) > 200:
            err_msg = err_msg[:200] + "..."
        logger.warning("Kiểm tra kết nối không thành công [%s]: %s", api_format, err_msg)
        return ConnectionTestResponse(
            success=False,
            message=f"kết nốiThất bại: {err_msg}",
        )


def _test_openai(base_url: str, api_key: str) -> ConnectionTestResponse:
    """Xác minh API tương thích OpenAI thông qua models.list()."""
    from openai import OpenAI

    from lib.config.url_utils import ensure_openai_base_url

    client = OpenAI(api_key=api_key, base_url=ensure_openai_base_url(base_url))
    models = client.models.list()
    count = sum(1 for _ in models)
    return ConnectionTestResponse(
        success=True,
        message="kết nối成功",
        model_count=count,
    )


def _test_google(base_url: str, api_key: str) -> ConnectionTestResponse:
    """Xác minh API Google genai thông qua models.list()."""
    from google import genai

    from lib.config.url_utils import ensure_google_base_url

    effective_url = ensure_google_base_url(base_url)
    http_options = {"base_url": effective_url} if effective_url else None
    client = genai.Client(api_key=api_key, http_options=http_options)
    pager = client.models.list()
    count = sum(1 for _ in pager)
    return ConnectionTestResponse(
        success=True,
        message="kết nối成功",
        model_count=count,
    )
