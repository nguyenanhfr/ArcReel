"""Tính toán dấu vân tay tệp tài sản — Hỗ trợ bộ nhớ đệm định danh nội dung dựa trên mtime"""

from pathlib import Path

# Thư mục con phương tiện được quét
_MEDIA_SUBDIRS = ("storyboards", "videos", "thumbnails", "characters", "clues")

# Các tệp phương tiện đã biết trong thư mục gốc (như Phong cách Ảnh tham khảo)
_ROOT_MEDIA_SUFFIXES = frozenset((".png", ".jpg", ".jpeg", ".webp", ".mp4"))


def _scan_subdir(prefix: str, dir_path: Path, fingerprints: dict[str, int]) -> None:
    """Quét một thư mục con phương tiện và các thư mục con cấp một của nó (bỏ qua thư mục versions/)."""
    for entry in dir_path.iterdir():
        if entry.is_file():
            fingerprints[f"{prefix}/{entry.name}"] = entry.stat().st_mtime_ns
        elif entry.is_dir() and entry.name != "versions":
            sub_prefix = f"{prefix}/{entry.name}"
            for sub_entry in entry.iterdir():
                if sub_entry.is_file():
                    fingerprints[f"{sub_prefix}/{sub_entry.name}"] = sub_entry.stat().st_mtime_ns


def compute_asset_fingerprints(project_path: Path) -> dict[str, int]:
    """
    Quét tất cả các tệp phương tiện trong thư mục Dự án, trả lại {Đường dẫn tương đối: mtime_ns_int} Bản đồ.

    mtime_ns Là số nguyên theo nano giây, dùng làm tham số cache-bust URL, độ chính xác cao hơn mức giây.
    Khoảng 50 tệp, mất thời gian <1ms（Chỉ đọc Hệ thống chuyển dữ liệu (metadata)).
    """
    fingerprints: dict[str, int] = {}

    for subdir in _MEDIA_SUBDIRS:
        dir_path = project_path / subdir
        if dir_path.is_dir():
            _scan_subdir(subdir, dir_path, fingerprints)

    # Các tệp phương tiện trong thư mục gốc (như style_reference.png)
    for f in project_path.iterdir():
        if f.is_file() and f.suffix.lower() in _ROOT_MEDIA_SUFFIXES:
            fingerprints[f.name] = f.stat().st_mtime_ns

    return fingerprints
