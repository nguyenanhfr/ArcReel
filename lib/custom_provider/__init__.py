"""nhà cung cấp tùy chỉnhModule."""

CUSTOM_PROVIDER_PREFIX = "custom-"


def make_provider_id(db_id: int) -> str:
    """Xây dựng chuỗi provider_id của nhà cung cấp tùy chỉnh, ví dụ 'custom-3'。"""
    return f"{CUSTOM_PROVIDER_PREFIX}{db_id}"


def parse_provider_id(provider_id: str) -> int:
    """Từ 'custom-3' định dạngprovider_id để trích xuất ID cơ sở dữ liệu.

    Raises:
        ValueError: Nếu định dạng không đúng
    """
    return int(provider_id.removeprefix(CUSTOM_PROVIDER_PREFIX))


def is_custom_provider(provider_id: str) -> bool:
    """Xác định xem có phải là provider_id của nhà cung cấp tùy chỉnh."""
    return provider_id.startswith(CUSTOM_PROVIDER_PREFIX)
