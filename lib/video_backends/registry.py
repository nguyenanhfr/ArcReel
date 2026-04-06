"""VideoĐăng ký backend với factory."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from lib.video_backends.base import VideoBackend

_BACKEND_FACTORIES: dict[str, Callable[..., VideoBackend]] = {}


def register_backend(name: str, factory: Callable[..., VideoBackend]) -> None:
    """Đăng ký một hàm nhà máy Video backend."""
    _BACKEND_FACTORIES[name] = factory


def create_backend(name: str, **kwargs: Any) -> VideoBackend:
    """Dựa theo ví dụ TênTạoVideo backend."""
    if name not in _BACKEND_FACTORIES:
        raise ValueError(f"Unknown video backend: {name}")
    return _BACKEND_FACTORIES[name](**kwargs)


def get_registered_backends() -> list[str]:
    """Trả về tất cả Tên backend đã đăng ký."""
    return list(_BACKEND_FACTORIES.keys())
