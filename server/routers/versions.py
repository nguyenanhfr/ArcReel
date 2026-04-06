"""
Quản lý phiên bản API Định tuyến

Xử lý truy vấn phiên bản và yêu cầu khôi phục.
"""

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

from lib import PROJECT_ROOT
from lib.project_change_hints import project_change_source
from lib.project_manager import ProjectManager
from lib.version_manager import VersionManager
from server.auth import CurrentUser

router = APIRouter()

# Khởi tạo quản lý dự án
pm = ProjectManager(PROJECT_ROOT / "projects")

_RESOURCE_FILE_PATTERNS: dict[str, tuple[str, str]] = {
    "storyboards": ("storyboards", "scene_{id}.png"),
    "videos": ("videos", "scene_{id}.mp4"),
    "characters": ("characters", "{id}.png"),
    "clues": ("clues", "{id}.png"),
}


def get_project_manager() -> ProjectManager:
    return pm


def get_version_manager(project_name: str) -> VersionManager:
    """Lấy Trình quản lý phiên bản của Dự án"""
    project_path = get_project_manager().get_project_path(project_name)
    return VersionManager(project_path)


def _resolve_resource_path(
    resource_type: str,
    resource_id: str,
    project_path: Path,
) -> tuple[Path, str]:
    """Trả về (current_file_absolute, relative_file_path), ném HTTP khi loại tài nguyên không hợp lệPException。"""
    pattern = _RESOURCE_FILE_PATTERNS.get(resource_type)
    if pattern is None:
        raise HTTPException(status_code=400, detail=f"Loại tài nguyên không được hỗ trợ: {resource_type}")
    subdir, name_tpl = pattern
    name = name_tpl.format(id=resource_id)
    return project_path / subdir / name, f"{subdir}/{name}"


def _sync_storyboard_metadata(
    project_name: str,
    resource_id: str,
    file_path: str,
    project_path: Path,
) -> None:
    scripts_dir = project_path / "scripts"
    if not scripts_dir.exists():
        return
    for script_file in scripts_dir.glob("*.json"):
        try:
            with project_change_source("webui"):
                get_project_manager().update_scene_asset(
                    project_name=project_name,
                    script_filename=script_file.name,
                    scene_id=resource_id,
                    asset_type="storyboard_image",
                    asset_path=file_path,
                )
        except KeyError:
            continue
        except Exception as exc:
            logger.warning("Đồng bộ hóa métadata phân cảnh thất bại: %s", exc)
            continue


def _sync_metadata(
    resource_type: str,
    project_name: str,
    resource_id: str,
    file_path: str,
    project_path: Path,
) -> None:
    """Khôi phục xong đồng bộ hóa siêu dữ liệu, đảm bảo tham chiếu chỉ đến đường dẫn tệp thống nhất."""
    if resource_type == "characters":
        try:
            with project_change_source("webui"):
                get_project_manager().update_project_character_sheet(project_name, resource_id, file_path)
        except KeyError:
            pass  # Nhân vậtMục có thể đã bị xóa khỏi project.json, bỏ qua đồng bộ hóa siêu dữ liệu
    elif resource_type == "clues":
        try:
            with project_change_source("webui"):
                get_project_manager().update_clue_sheet(project_name, resource_id, file_path)
        except KeyError:
            pass  # Manh mốiMục có thể đã bị xóa khỏi project.json, bỏ qua đồng bộ hóa siêu dữ liệu
    elif resource_type == "storyboards":
        _sync_storyboard_metadata(project_name, resource_id, file_path, project_path)


# ==================== Truy vấn phiên bản ====================


@router.get("/projects/{project_name}/versions/{resource_type}/{resource_id}")
async def get_versions(
    project_name: str,
    resource_type: str,
    resource_id: str,
    _user: CurrentUser,
):
    """
    Lấy danh sách tất cả các phiên bản của tài nguyên

    Args:
        project_name: Dự ánTên
        resource_type: Loại tài nguyên (bảng phân cảnh, video, nhân vật, manh mối)
        resource_id: ID tài nguyên
    """
    try:
        vm = get_version_manager(project_name)
        versions_info = vm.get_versions(resource_type, resource_id)

        return {"resource_type": resource_type, "resource_id": resource_id, **versions_info}

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Xử lý yêu cầu Thất bại")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Khôi phục phiên bản ====================


@router.post("/projects/{project_name}/versions/{resource_type}/{resource_id}/restore/{version}")
async def restore_version(
    project_name: str,
    resource_type: str,
    resource_id: str,
    version: int,
    _user: CurrentUser,
):
    """
    Chuyển sang phiên bản được chỉ định

    Sẽ sao chép phiên bản được chỉ định đến đường dẫn hiện tại và chuyển con trỏ phiên bản hiện tại sang phiên bản đó.

    Args:
        project_name: Dự ánTên
        resource_type: Loại tài nguyên
        resource_id: ID tài nguyên
        version: Số phiên bản cần khôi phục
    """
    try:
        vm = get_version_manager(project_name)
        project_path = get_project_manager().get_project_path(project_name)
        current_file, file_path = _resolve_resource_path(resource_type, resource_id, project_path)

        result = vm.restore_version(
            resource_type=resource_type,
            resource_id=resource_id,
            version=version,
            current_file=current_file,
        )

        _sync_metadata(resource_type, project_name, resource_id, file_path, project_path)

        # Tính toán fingerprint của tệp sau khi khôi phục; khi khôi phục video đồng bộ xóa hình thu nhỏ (nội dung đã mất hiệu lực)
        asset_fingerprints: dict[str, int] = {}
        if current_file.exists():
            asset_fingerprints[file_path] = current_file.stat().st_mtime_ns

        if resource_type == "videos":
            thumbnail_path = project_path / "thumbnails" / f"scene_{resource_id}.jpg"
            thumbnail_key = f"thumbnails/scene_{resource_id}.jpg"
            thumbnail_path.unlink(missing_ok=True)
            # fingerprint=0 Thông báoTệp phía trước đã mất hiệu lực (poster biến mất cho đến khi tạo lại)
            asset_fingerprints[thumbnail_key] = 0

        return {
            "success": True,
            **result,
            "file_path": file_path,
            "asset_fingerprints": asset_fingerprints,
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Xử lý yêu cầu Thất bại")
        raise HTTPException(status_code=500, detail=str(e))
