"""Cấu hình log thống nhất."""

import logging
import os

_HANDLER_ATTR = "_arcreel_logging"


def setup_logging(level: str | None = None) -> None:
    """Cấu hình logger gốc.

    Args:
        level: Mức log dưới dạng chuỗi (DEBUG/INFO/WARNING/ERROR).
               Nếu không cung cấp, đọc từ biến môi trường LOG_LEVEL, mặc định là INFO.
    """
    if level is None:
        level = os.environ.get("LOG_LEVEL", "INFO")

    numeric_level = getattr(logging, level.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(numeric_level)

    # Idempotent: tránh thêm handler trùng lặp
    if any(getattr(h, _HANDLER_ATTR, False) for h in root.handlers):
        return

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    setattr(handler, _HANDLER_ATTR, True)
    root.addHandler(handler)

    # Thống nhất định dạng log của uvicorn, tránh tồn tại hai định dạng cùng lúc
    for name in ("uvicorn", "uvicorn.error"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers.clear()
        uv_logger.propagate = True

    # Vô hiệu hóa uvicorn.access: log request được xử lý thống nhất bởi middleware trong app.py
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers.clear()
    access_logger.disabled = True

    # Ngăn tiếng ồn DEBUG của aiosqlite (mỗi thao tác SQL sẽ xuất ra 2 dòng log)
    logging.getLogger("aiosqlite").setLevel(max(numeric_level, logging.INFO))
