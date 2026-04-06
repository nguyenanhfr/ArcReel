"""
Môi trườngKhởi tạo module

Tải file .env.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def init_environment():
    """
    Khởi tạo môi trường dự án

    1. Xác định thư mục gốc Dự án
    2. Tải tập tin .env
    """
    # Lấy thư mục gốc Dự án (thư mục cha của lib)
    lib_dir = Path(__file__).parent
    project_root = lib_dir.parent

    # Tải tập tin .env
    try:
        from dotenv import load_dotenv

        env_path = project_root / ".env"
        if env_path.exists():
            load_dotenv(env_path)
        else:
            load_dotenv()
    except ImportError:
        pass  # python-dotenv Bỏ qua nếu chưa cài đặt

    return project_root


# Tự động khởi tạo khi nhập module
PROJECT_ROOT = init_environment()
