"""Văn bảnĐăng ký backend với factory."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from lib.text_backends.base import TextBackend

_BACKEND_FACTORIES: dict[str, Callable[..., TextBackend]] = {}


def register_backend(name: str, factory: Callable[..., TextBackend]) -> None:
    """Đăng ký một Hàm xưởng văn bản phía sau."""
    _BACKEND_FACTORIES[name] = factory


def create_backend(name: str, **kwargs: Any) -> TextBackend:
    """Theo TênTạoVăn bản phía sau Ví dụ."""
    if name not in _BACKEND_FACTORIES:
        raise ValueError(f"Unknown text backend: {name}")
    return _BACKEND_FACTORIES[name](**kwargs)


def get_registered_backends() -> list[str]:
    """Trả về tất cả Tên backend đã đăng ký."""
    return list(_BACKEND_FACTORIES.keys())
