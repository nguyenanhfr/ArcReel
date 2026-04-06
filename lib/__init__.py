# AI Anime Generator Library
# Chia sẻ thư viện Python, dùng cho bao đóng Gemini API và quản lý Dự án

# Trước tiên khởi tạo Môi trường (kích hoạt .venv, tải .env)
from .data_validator import DataValidator, ValidationResult, validate_episode, validate_project
from .env_init import PROJECT_ROOT
from .project_manager import ProjectManager

__all__ = [
    "ProjectManager",
    "PROJECT_ROOT",
    "DataValidator",
    "validate_project",
    "validate_episode",
    "ValidationResult",
]
