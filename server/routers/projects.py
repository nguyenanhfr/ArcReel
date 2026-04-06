"""
Dự ánQuản lý tuyến đường

Xử lý các thao tác CRUD của Dự án, tái sử dụng lib/project_manager.py
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

if TYPE_CHECKING:
    from server.services.jianying_draft_service import JianyingDraftService

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi import Path as FastAPIPath
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask

logger = logging.getLogger(__name__)

from lib import PROJECT_ROOT
from lib.asset_fingerprints import compute_asset_fingerprints
from lib.project_change_hints import project_change_source
from lib.project_manager import ProjectManager
from lib.status_calculator import StatusCalculator
from server.auth import CurrentUser, create_download_token, verify_download_token
from server.routers._validators import validate_backend_value
from server.services.project_archive import (
    ProjectArchiveService,
    ProjectArchiveValidationError,
)

router = APIRouter()

# Khởi tạo Trình quản lý Dự án và bộ tính trạng thái
pm = ProjectManager(PROJECT_ROOT / "projects")
calc = StatusCalculator(pm)


def get_project_manager() -> ProjectManager:
    return pm


def get_status_calculator() -> StatusCalculator:
    return calc


def get_archive_service() -> ProjectArchiveService:
    return ProjectArchiveService(get_project_manager())


class CreateProjectRequest(BaseModel):
    name: str | None = None
    title: str | None = None
    style: str | None = ""
    content_mode: str | None = "narration"


class UpdateProjectRequest(BaseModel):
    title: str | None = None
    style: str | None = None
    content_mode: str | None = None
    aspect_ratio: dict | None = None
    video_backend: str | None = None
    image_backend: str | None = None
    video_generate_audio: bool | None = None
    text_backend_script: str | None = None
    text_backend_overview: str | None = None
    text_backend_style: str | None = None


def _cleanup_temp_file(path: str) -> None:
    try:
        os.unlink(path)
    except FileNotFoundError:
        return


def _cleanup_temp_dir(dir_path: str) -> None:
    shutil.rmtree(dir_path, ignore_errors=True)


@router.post("/projects/import")
async def import_project_archive(
    _user: CurrentUser,
    file: UploadFile = File(...),
    conflict_policy: str = Form("prompt"),
):
    """Nhập Dự án từ ZIP."""
    upload_path: str | None = None
    try:
        fd, upload_path = tempfile.mkstemp(prefix="arcreel-upload-", suffix=".zip")
        os.close(fd)

        with open(upload_path, "wb") as target:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                target.write(chunk)

        result = get_archive_service().import_project_archive(
            Path(upload_path),
            uploaded_filename=file.filename,
            conflict_policy=conflict_policy,
        )
        return {
            "success": True,
            "project_name": result.project_name,
            "project": result.project,
            "warnings": result.warnings,
            "conflict_resolution": result.conflict_resolution,
            "diagnostics": result.diagnostics,
        }
    except ProjectArchiveValidationError as exc:
        diagnostics = exc.extra.get(
            "diagnostics",
            {"blocking": [], "auto_fixable": [], "warnings": []},
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": exc.detail,
                "errors": exc.errors,
                "warnings": exc.warnings,
                "diagnostics": diagnostics,
                **exc.extra,
            },
        )
    except Exception as e:
        logger.exception("Xử lý yêu cầu Thất bại")
        return JSONResponse(
            status_code=500,
            content={"detail": str(e), "errors": [], "warnings": []},
        )
    finally:
        await file.close()
        if upload_path:
            _cleanup_temp_file(upload_path)


@router.post("/projects/{name}/export/token")
async def create_export_token(
    name: str,
    current_user: CurrentUser,
    scope: str = Query("full"),
):
    """Phát hành mã thông báo tải xuống ngắn hạn để xác thực tải xuống gốc của trình duyệt。"""
    try:
        if not get_project_manager().project_exists(name):
            raise HTTPException(status_code=404, detail=f"Dự án '{name}' Không tồn tại hoặc chưa được khởi tạo")
        if scope not in ("full", "current"):
            raise HTTPException(status_code=422, detail="scope Phải là full hoặc current")

        username = current_user.sub
        download_token = create_download_token(username, name)
        diagnostics = get_archive_service().get_export_diagnostics(name, scope=scope)
        return {
            "download_token": download_token,
            "expires_in": 300,
            "diagnostics": diagnostics,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Xử lý yêu cầu Thất bại")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/projects/{name}/export")
async def export_project_archive(
    name: str,
    download_token: str = Query(...),
    scope: str = Query("full"),
):
    """Xuất Dự án thành ZIP. Cần xác thực download_token (lấy qua POST /export/token)."""
    if scope not in ("full", "current"):
        raise HTTPException(status_code=422, detail="scope Phải là full hoặc current")

    # Xác minh download_token
    import jwt as pyjwt

    try:
        verify_download_token(download_token, name)
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Liên kết tải xuống đã hết hạn, vui lòng xuất lại")
    except ValueError:
        raise HTTPException(status_code=403, detail="Download token không khớp với Dự án mục tiêu")
    except pyjwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Download token không hợp lệ")

    try:
        archive_path, download_name = get_archive_service().export_project(name, scope=scope)
        return FileResponse(
            archive_path,
            media_type="application/zip",
            filename=download_name,
            background=BackgroundTask(_cleanup_temp_file, str(archive_path)),
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Dự án '{name}' Không tồn tại hoặc chưa được khởi tạo")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Xử lý yêu cầu Thất bại")
        raise HTTPException(status_code=500, detail=str(e))


# --- Xuất bản nháp Jianying ---


def get_jianying_draft_service() -> JianyingDraftService:
    from server.services.jianying_draft_service import JianyingDraftService

    return JianyingDraftService(get_project_manager())


def _validate_draft_path(draft_path: str) -> str:
    """Kiểm tra tính hợp pháp của draft_path"""
    if not draft_path or not draft_path.strip():
        raise HTTPException(status_code=422, detail="Vui lòng cung cấp Đường dẫn thư mục bản nháp Jianying hợp lệ")
    if len(draft_path) > 1024:
        raise HTTPException(status_code=422, detail="Đường dẫn thư mục bản nhápQuá dài")
    if any(ord(c) < 32 for c in draft_path):
        raise HTTPException(status_code=422, detail="Đường dẫn thư mục bản nhápChứa ký tự bất hợp pháp")
    return draft_path.strip()


@router.get("/projects/{name}/export/jianying-draft")
def export_jianying_draft(
    name: str,
    episode: int = Query(..., description="Số tập"),
    draft_path: str = Query(..., description="Thư mục bản nháp Jianying của người dùng trên máy"),
    download_token: str = Query(..., description="下载 token"),
    jianying_version: str = Query("6", description="Phiên bản Jianying：6 Hoặc 5"),
):
    """Xuất bản nháp Jianying dưới dạng ZIP của tập được chỉ định"""
    import jwt as pyjwt

    # 1. Xác minh download_token
    try:
        verify_download_token(download_token, name)
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Liên kết tải xuống đã hết hạn, vui lòng xuất lại")
    except ValueError:
        raise HTTPException(status_code=403, detail="Tải token và Dự án không có trận đấu")
    except pyjwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Download token không hợp lệ")

    # 2. Kiểm tra draft_path
    draft_path = _validate_draft_path(draft_path)

    # 3. Gọi dịch vụ
    svc = get_jianying_draft_service()
    try:
        zip_path = svc.export_episode_draft(
            project_name=name,
            episode=episode,
            draft_path=draft_path,
            use_draft_info_name=(jianying_version != "5"),
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception:
        logger.exception("Xuất bản nháp Jianying thất bại: project=%s episode=%d", name, episode)
        raise HTTPException(status_code=500, detail="Xuất bản nháp Jianying thất bại，请稍后Thử lại")

    download_name = f"{name}_Không.{episode}Tập_Đoạn ghép Jingying.zip"

    return FileResponse(
        path=str(zip_path),
        media_type="application/zip",
        filename=download_name,
        background=BackgroundTask(_cleanup_temp_dir, str(zip_path.parent)),
    )


@router.get("/projects")
async def list_projects(_user: CurrentUser):
    """Liệt kê tất cả Dự án"""
    manager = get_project_manager()
    calculator = get_status_calculator()
    projects = []
    for name in manager.list_projects():
        try:
            # Thử tải metadata Dự án
            if manager.project_exists(name):
                project = manager.load_project(name)
                # Lấy hình thu nhỏ (Không. một Ảnh phân cảnh)
                project_dir = manager.get_project_path(name)
                storyboards_dir = project_dir / "storyboards"
                thumbnail = None
                if storyboards_dir.exists():
                    scene_images = sorted(storyboards_dir.glob("scene_*.png"))
                    if scene_images:
                        thumbnail = f"/api/v1/files/{name}/storyboards/{scene_images[0].name}"

                # Sử dụng StatusCalculator tính Tiến độ (tính khi đọc)
                status = calculator.calculate_project_status(name, project)

                projects.append(
                    {
                        "name": name,
                        "title": project.get("title", name),
                        "style": project.get("style", ""),
                        "thumbnail": thumbnail,
                        "status": status,
                    }
                )
            else:
                # Dự án không có project.json
                projects.append(
                    {
                        "name": name,
                        "title": name,
                        "style": "",
                        "thumbnail": None,
                        "status": {},
                    }
                )
        except Exception as e:
            # Trả về thông tin cơ bản khi xảy ra lỗi
            logger.warning("加载Dự án '%s' Metadata Thất bại: %s", name, e)
            projects.append(
                {"name": name, "title": name, "style": "", "thumbnail": None, "status": {}, "error": str(e)}
            )

    return {"projects": projects}


@router.post("/projects")
async def create_project(req: CreateProjectRequest, _user: CurrentUser):
    """Tạo新Dự án"""
    try:
        manager = get_project_manager()
        title = (req.title or "").strip()
        manual_name = (req.name or "").strip()
        if not title and not manual_name:
            raise HTTPException(status_code=400, detail="Dự ánTiêu đề không thể trống")
        project_name = manual_name or manager.generate_project_name(title)

        # TạoDự ánCấu trúc thư mục
        manager.create_project(project_name)
        # TạoDự án元数据
        with project_change_source("webui"):
            project = manager.create_project_metadata(
                project_name,
                title or manual_name,
                req.style,
                req.content_mode,
            )
        return {"success": True, "name": project_name, "project": project}
    except FileExistsError:
        raise HTTPException(status_code=400, detail=f"Dự án '{project_name}' Đã tồn tại")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Xử lý yêu cầu Thất bại")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/projects/{name}")
async def get_project(name: str, _user: CurrentUser):
    """Lấy chi tiết Dự án (bao gồm tính toán từ đoạn thời gian thực)"""
    try:
        manager = get_project_manager()
        calculator = get_status_calculator()
        if not manager.project_exists(name):
            raise HTTPException(status_code=404, detail=f"Dự án '{name}' Không tồn tại hoặc chưa được khởi tạo")

        project = manager.load_project(name)

        # Tiêm tính toán từ đoạn (không ghi vào JSON, chỉ dùng cho phản hồi API)
        project = calculator.enrich_project(name, project)

        # Tải tất cả Kịch bản và tiêm tính toán từ đoạn
        scripts = {}
        for ep in project.get("episodes", []):
            script_file = ep.get("script_file", "")
            if script_file:
                try:
                    script = manager.load_script(name, script_file)
                    script = calculator.enrich_script(script)
                    # Sử dụng tên tệp thuần túy làm khóa (bỏ tiền tố scripts/)
                    key = script_file.replace("scripts/", "", 1) if script_file.startswith("scripts/") else script_file
                    scripts[key] = script
                except FileNotFoundError:
                    pass

        # Tính vân tay tệp phương tiện (dùng cho bộ nhớ đệm định vị nội dung frontend)
        project_path = manager.get_project_path(name)
        fingerprints = compute_asset_fingerprints(project_path)

        return {
            "project": project,
            "scripts": scripts,
            "asset_fingerprints": fingerprints,
        }
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Dự án '{name}' 不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Xử lý yêu cầu Thất bại")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/projects/{name}")
async def update_project(name: str, req: UpdateProjectRequest, _user: CurrentUser):
    """Cập nhật metadata Dự án"""
    try:
        manager = get_project_manager()
        project = manager.load_project(name)

        if req.content_mode is not None or req.aspect_ratio is not None:
            raise HTTPException(
                status_code=400,
                detail="Không thể sửa content_mode hoặc aspect_ratio sau khi tạo dự án",
            )

        if req.title is not None:
            project["title"] = req.title
        if req.style is not None:
            project["style"] = req.style
        for field in (
            "video_backend",
            "image_backend",
            "text_backend_script",
            "text_backend_overview",
            "text_backend_style",
        ):
            if field in req.model_fields_set:
                value = getattr(req, field)
                if value:
                    validate_backend_value(value, field)
                    project[field] = value
                else:
                    project.pop(field, None)
        if "video_generate_audio" in req.model_fields_set:
            if req.video_generate_audio is None:
                project.pop("video_generate_audio", None)
            else:
                project["video_generate_audio"] = req.video_generate_audio

        with project_change_source("webui"):
            manager.save_project(name, project)
        return {"success": True, "project": project}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Dự án '{name}' 不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Xử lý yêu cầu Thất bại")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/projects/{name}")
async def delete_project(name: str, _user: CurrentUser):
    """XóaDự án"""
    try:
        project_dir = get_project_manager().get_project_path(name)
        shutil.rmtree(project_dir)
        return {"success": True, "message": f"Dự án '{name}' Đã Xóa"}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Dự án '{name}' 不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Xử lý yêu cầu Thất bại")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/projects/{name}/scripts/{script_file}")
async def get_script(name: str, script_file: str, _user: CurrentUser):
    """Lấy nội dung Kịch bản"""
    try:
        script = get_project_manager().load_script(name, script_file)
        return {"script": script}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Kịch bản '{script_file}' 不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Xử lý yêu cầu Thất bại")
        raise HTTPException(status_code=500, detail=str(e))


class UpdateSceneRequest(BaseModel):
    script_file: str
    updates: dict


@router.patch("/projects/{name}/scenes/{scene_id}")
async def update_scene(name: str, scene_id: str, req: UpdateSceneRequest, _user: CurrentUser):
    """Cập nhật Cảnh"""
    try:
        manager = get_project_manager()
        script = manager.load_script(name, req.script_file)

        # Tìm và cập nhật Cảnh
        scene_found = False
        for scene in script.get("scenes", []):
            if scene.get("scene_id") == scene_id:
                scene_found = True
                # Cập nhật các đoạn từ được phép
                for key, value in req.updates.items():
                    if key in [
                        "duration_seconds",
                        "image_prompt",
                        "video_prompt",
                        "characters_in_scene",
                        "clues_in_scene",
                        "segment_break",
                        "note",
                    ]:
                        if value is None and key != "note":
                            continue
                        scene[key] = value
                break

        if not scene_found:
            raise HTTPException(status_code=404, detail=f"Cảnh '{scene_id}' 不存在")

        with project_change_source("webui"):
            manager.save_script(name, script, req.script_file)
        return {"success": True, "scene": scene}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Kịch bản不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Xử lý yêu cầu Thất bại")
        raise HTTPException(status_code=500, detail=str(e))


class UpdateSegmentRequest(BaseModel):
    script_file: str
    duration_seconds: int | None = None
    segment_break: bool | None = None
    image_prompt: dict | str | None = None
    video_prompt: dict | str | None = None
    transition_to_next: str | None = None
    note: str | None = None


class UpdateOverviewRequest(BaseModel):
    synopsis: str | None = None
    genre: str | None = None
    theme: str | None = None
    world_setting: str | None = None


@router.patch("/projects/{name}/segments/{segment_id}")
async def update_segment(name: str, segment_id: str, req: UpdateSegmentRequest, _user: CurrentUser):
    """Cập nhật Đoạn chế độ kể chuyện"""
    try:
        manager = get_project_manager()
        script = manager.load_script(name, req.script_file)

        # Kiểm tra có phải chế độ kể chuyện không
        if script.get("content_mode") != "narration" and "segments" not in script:
            raise HTTPException(status_code=400, detail="Kịch bản này không phải chế độ kể chuyện, vui lòng sử dụng giao diện cập nhật Cảnh")

        # Tìm và cập nhật Đoạn
        segment_found = False
        for segment in script.get("segments", []):
            if segment.get("segment_id") == segment_id:
                segment_found = True
                # Cập nhật đoạn từ
                if req.duration_seconds is not None:
                    segment["duration_seconds"] = req.duration_seconds
                if req.segment_break is not None:
                    segment["segment_break"] = req.segment_break
                if req.image_prompt is not None:
                    segment["image_prompt"] = req.image_prompt
                if req.video_prompt is not None:
                    segment["video_prompt"] = req.video_prompt
                if req.transition_to_next is not None:
                    segment["transition_to_next"] = req.transition_to_next
                if "note" in req.model_fields_set:
                    segment["note"] = req.note
                break

        if not segment_found:
            raise HTTPException(status_code=404, detail=f"Đoạn '{segment_id}' 不存在")

        with project_change_source("webui"):
            manager.save_script(name, script, req.script_file)
        return {"success": True, "segment": segment}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Kịch bản不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Xử lý yêu cầu Thất bại")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Tệp nguồnQuản lý ======================


@router.post("/projects/{name}/source")
async def set_project_source(
    name: Annotated[str, FastAPIPath(pattern=r"^[a-zA-Z0-9_-]+$")],
    _user: CurrentUser,
    generate_overview: Annotated[bool, Form()] = True,
    content: Annotated[str | None, Form()] = None,
    file: Annotated[UploadFile | None, File()] = None,
):
    """Tải lên Tệp nguồn tiểu thuyết hoặc gửi trực tiếp nội dung Văn bản, tùy chọn kích hoạt AI Tạo tổng quan.

    Hai cách đầu vào (tương tranh, đều sử dụng multipart/form-data):
    - file：Tải lên tệp .txt/.md, tên tệp lấy từ tệp đã tải lên
    - content：Gửi trực tiếp nội dung Văn bản, tự động đặt tên là novel.txt

    Tối đa 200000 ký tự (khoảng 100000 từ Hán).
    """
    MAX_CHARS = 200_000
    ALLOWED_SUFFIXES = {".txt", ".md"}

    if not content and not file:
        raise HTTPException(status_code=400, detail="Cần cung cấp một trong hai: content (nội dung Văn bản) hoặc file (tải tập tin lên)")
    if content and file:
        raise HTTPException(status_code=400, detail="content Không được cung cấp cả content và file đồng thời, vui lòng chọn một")

    try:
        manager = get_project_manager()
        if not manager.project_exists(name):
            raise HTTPException(status_code=404, detail=f"Dự án '{name}' 不存在")

        project_dir = manager.get_project_path(name)
        source_dir = project_dir / "source"
        source_dir.mkdir(parents=True, exist_ok=True)

        if file:
            # Chế độ tải tập tin: tên tập tin lấy từ tệp đã tải lên
            original_name = file.filename or "novel.txt"
            suffix = Path(original_name).suffix.lower()
            if suffix not in ALLOWED_SUFFIXES:
                raise HTTPException(status_code=400, detail=f"Chỉ hỗ trợ tệp .txt / .md, nhận được: {original_name!r}")

            safe_filename = Path(original_name).name  # Ngăn chặn lỗ hổng đường dẫn
            # Nếu Content-Length khả dụng, từ chối trước các tệp quá lớn để tránh đọc vào bộ nhớ rồi mới kiểm tra
            if file.size is not None and file.size > MAX_CHARS * 4:
                raise HTTPException(status_code=400, detail=f"Kích thước tệp vượt quá giới hạn (tối đa khoảng {MAX_CHARS} từký tự)")
            raw = await file.read()
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                raise HTTPException(status_code=400, detail="Lỗi mã hóa tệp, vui lòng sử dụng tệp Văn bản mã hóa UTF-8")

            if len(text) > MAX_CHARS:
                raise HTTPException(
                    status_code=400, detail=f"Nội dung tệp vượt quá giới hạn tối đa {MAX_CHARS} từký tự (Hiện tại {len(text)}）"
                )

            (source_dir / safe_filename).write_text(text, encoding="utf-8")
            chars = len(text)
        else:
            # Văn bảnChế độ nội dung:Đặt tên cố định là novel.txt
            if len(content) > MAX_CHARS:
                raise HTTPException(
                    status_code=400, detail=f"content Vượt quá độ dài tối đa {MAX_CHARS} từký tự (Hiện tại {len(content)}）"
                )

            safe_filename = "novel.txt"
            (source_dir / safe_filename).write_text(content, encoding="utf-8")
            chars = len(content)

        result: dict = {"success": True, "filename": safe_filename, "chars": chars}

        if generate_overview:
            try:
                with project_change_source("webui"):
                    overview = await manager.generate_overview(name)
                result["overview"] = overview
            except Exception as ov_err:
                # Tạo tổng quanThất bạiKhông ảnh hưởng đến việc ghi tệp thành công
                result["overview"] = None
                result["overview_error"] = str(ov_err)

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Xử lý yêu cầu Thất bại")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if file:
            await file.close()


# ==================== Mô tả dự ánQuản lý ======================


@router.post("/projects/{name}/generate-overview")
async def generate_overview(name: str, _user: CurrentUser):
    """Sử dụng AI để tạo dự án Mô tả"""
    try:
        with project_change_source("webui"):
            overview = await get_project_manager().generate_overview(name)
        return {"success": True, "overview": overview}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Dự án '{name}' 不存在")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Xử lý yêu cầu Thất bại")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/projects/{name}/overview")
async def update_overview(name: str, req: UpdateOverviewRequest, _user: CurrentUser):
    """Cập nhật dự án mô tả (Chỉnh sửa thủ công)"""
    try:
        manager = get_project_manager()
        project = manager.load_project(name)

        # Đảm bảo overview từ đoạn tồn tại
        if "overview" not in project:
            project["overview"] = {}

        # Cập nhật trường không trống
        if req.synopsis is not None:
            project["overview"]["synopsis"] = req.synopsis
        if req.genre is not None:
            project["overview"]["genre"] = req.genre
        if req.theme is not None:
            project["overview"]["theme"] = req.theme
        if req.world_setting is not None:
            project["overview"]["world_setting"] = req.world_setting

        with project_change_source("webui"):
            manager.save_project(name, project)
        return {"success": True, "overview": project["overview"]}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Dự án '{name}' 不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Xử lý yêu cầu Thất bại")
        raise HTTPException(status_code=500, detail=str(e))
