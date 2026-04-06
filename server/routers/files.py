"""
Quản lý tập tin路由

Xử lý tải lên tệp và dịch vụ tài nguyên tĩnh
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Body, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse

from lib import PROJECT_ROOT
from lib.image_utils import normalize_uploaded_image
from lib.project_change_hints import emit_project_change_batch, project_change_source
from lib.project_manager import ProjectManager
from server.auth import CurrentUser

router = APIRouter()

# Khởi tạo quản lý dự án
pm = ProjectManager(PROJECT_ROOT / "projects")


def get_project_manager() -> ProjectManager:
    return pm


# Loại tệp được phép
ALLOWED_EXTENSIONS = {
    "source": [".txt", ".md", ".doc", ".docx"],
    "character": [".png", ".jpg", ".jpeg", ".webp"],
    "character_ref": [".png", ".jpg", ".jpeg", ".webp"],
    "clue": [".png", ".jpg", ".jpeg", ".webp"],
    "storyboard": [".png", ".jpg", ".jpeg", ".webp"],
}


@router.get("/files/{project_name}/{path:path}")
async def serve_project_file(project_name: str, path: str, request: Request):
    """Dịch vụ tệp tĩnh trong Dự án (Ảnh/Video)"""
    try:
        project_dir = get_project_manager().get_project_path(project_name)
        file_path = project_dir / path

        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"Tệp không tồn tại: {path}")

        # Kiểm tra bảo mật: Đảm bảo đường dẫn nằm trong thư mục Dự án
        try:
            file_path.resolve().relative_to(project_dir.resolve())
        except ValueError:
            raise HTTPException(status_code=403, detail="Cấm truy cập tệp ngoài thư mục Dự án")

        # Bộ nhớ đệm theo địa chỉ nội dung: khi có tham số ?v= hoặc đường dẫn versions/ thì đặt immutable
        headers = {}
        if request.query_params.get("v") or path.startswith("versions/"):
            headers["Cache-Control"] = "public, max-age=31536000, immutable"

        return FileResponse(file_path, headers=headers)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Dự án '{project_name}' 不存在")


@router.post("/projects/{project_name}/upload/{upload_type}")
async def upload_file(
    project_name: str, upload_type: str, _user: CurrentUser, file: UploadFile = File(...), name: str = None
):
    """
    Tải lên tệp

    Args:
        project_name: Dự ánTên
        upload_type: Loại tải lên (nguồn/nhân vật/gợi ý/bảng tường truyện)
        file: Tệp đã tải lên
        name: Tùy chọn, dùng cho Nhân vật/Tên manh mối, hoặc Phân cảnh ID (tự động cập nhật siêu dữ liệu)
    """
    if upload_type not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"không hợp lệLoại tải lên: {upload_type}")

    # Kiểm tra phần mở rộng tệp
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS[upload_type]:
        raise HTTPException(
            status_code=400,
            detail=f"Loại tệp không được hỗ trợ {ext}，Loại được phép: {ALLOWED_EXTENSIONS[upload_type]}",
        )

    try:
        project_dir = get_project_manager().get_project_path(project_name)

        # Xác định thư mục đích
        if upload_type == "source":
            target_dir = project_dir / "source"
            filename = file.filename
        elif upload_type == "character":
            target_dir = project_dir / "characters"
            # Lưu thống nhất dưới dạng PNG và sử dụng tên tệp ổn định (tránh sự không nhất quán jpg/png gây ra bởi khôi phục phiền phiên bản/trích dẫn bất thường)
            if name:
                filename = f"{name}.png"
            else:
                filename = f"{Path(file.filename).stem}.png"
        elif upload_type == "character_ref":
            target_dir = project_dir / "characters" / "refs"
            if name:
                filename = f"{name}.png"
            else:
                filename = f"{Path(file.filename).stem}.png"
        elif upload_type == "clue":
            target_dir = project_dir / "clues"
            if name:
                filename = f"{name}.png"
            else:
                filename = f"{Path(file.filename).stem}.png"
        elif upload_type == "storyboard":
            # Lưu ý: thư mục là storyboards (số nhiều), không phải storyboard
            target_dir = project_dir / "storyboards"
            if name:
                filename = f"scene_{name}.png"
            else:
                filename = f"{Path(file.filename).stem}.png"
        else:
            target_dir = project_dir / upload_type
            filename = file.filename

        target_dir.mkdir(parents=True, exist_ok=True)

        # LưuTệp (nén thành JPEG nếu > 2MB, nếu không kiểm tra và lưu nguyên bản)
        content = await file.read()
        if upload_type in ("character", "character_ref", "clue", "storyboard"):
            try:
                content, ext = normalize_uploaded_image(content, Path(file.filename).suffix.lower())
            except ValueError:
                raise HTTPException(status_code=400, detail="không hợp lệTệp ảnh không thể phân tích")
            filename = Path(filename).with_suffix(ext).name

        target_path = target_dir / filename
        with open(target_path, "wb") as f:
            f.write(content)

        # Cập nhật siêu dữ liệu
        if upload_type == "source":
            relative_path = f"source/{filename}"
        elif upload_type == "character":
            relative_path = f"characters/{filename}"
        elif upload_type == "character_ref":
            relative_path = f"characters/refs/{filename}"
        elif upload_type == "clue":
            relative_path = f"clues/{filename}"
        elif upload_type == "storyboard":
            relative_path = f"storyboards/{filename}"
        else:
            relative_path = f"{upload_type}/{filename}"

        if upload_type == "character" and name:
            try:
                with project_change_source("webui"):
                    get_project_manager().update_project_character_sheet(project_name, name, f"characters/{filename}")
            except KeyError:
                pass  # Nhân vậtKhông tồn tại, bỏ qua

        if upload_type == "character_ref" and name:
            try:
                with project_change_source("webui"):
                    get_project_manager().update_character_reference_image(
                        project_name, name, f"characters/refs/{filename}"
                    )
            except KeyError:
                pass  # Nhân vậtKhông tồn tại, bỏ qua

        if upload_type == "clue" and name:
            try:
                with project_change_source("webui"):
                    get_project_manager().update_clue_sheet(
                        project_name,
                        name,
                        f"clues/{filename}",
                    )
            except KeyError:
                pass  # Manh mốiKhông tồn tại, bỏ qua

        return {
            "success": True,
            "filename": filename,
            "path": relative_path,
            "url": f"/api/v1/files/{project_name}/{relative_path}",
        }

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Dự án '{project_name}' 不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Xử lý yêu cầu Thất bại")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/projects/{project_name}/files")
async def list_project_files(project_name: str, _user: CurrentUser):
    """Liệt kê tất cả các tệp trong Dự án"""
    try:
        project_dir = get_project_manager().get_project_path(project_name)

        files = {
            "source": [],
            "characters": [],
            "clues": [],
            "storyboards": [],
            "videos": [],
            "output": [],
        }

        for subdir, file_list in files.items():
            subdir_path = project_dir / subdir
            if subdir_path.exists():
                for f in subdir_path.iterdir():
                    if f.is_file() and not f.name.startswith("."):
                        file_list.append(
                            {
                                "name": f.name,
                                "size": f.stat().st_size,
                                "url": f"/api/v1/files/{project_name}/{subdir}/{f.name}",
                            }
                        )

        return {"files": files}

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Dự án '{project_name}' 不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Xử lý yêu cầu Thất bại")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/projects/{project_name}/source/{filename}")
async def get_source_file(project_name: str, filename: str, _user: CurrentUser):
    """Lấy nội dung Văn bản của tệp nguồn"""
    try:
        project_dir = get_project_manager().get_project_path(project_name)
        source_path = project_dir / "source" / filename

        if not source_path.exists():
            raise HTTPException(status_code=404, detail=f"Tệp không tồn tại: {filename}")

        # Kiểm tra bảo mật: Đảm bảo đường dẫn nằm trong thư mục Dự án
        try:
            source_path.resolve().relative_to(project_dir.resolve())
        except ValueError:
            raise HTTPException(status_code=403, detail="Cấm truy cập tệp ngoài thư mục Dự án")

        content = source_path.read_text(encoding="utf-8")
        return PlainTextResponse(content)

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Dự án '{project_name}' 不存在")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Lỗi mã hóa tệp, không thể đọc")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Xử lý yêu cầu Thất bại")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/projects/{project_name}/source/{filename}")
async def update_source_file(
    project_name: str, filename: str, _user: CurrentUser, content: str = Body(..., media_type="text/plain")
):
    """Cập nhật hoặc tạo tệp nguồn"""
    try:
        project_dir = get_project_manager().get_project_path(project_name)
        source_dir = project_dir / "source"
        source_dir.mkdir(parents=True, exist_ok=True)
        source_path = source_dir / filename

        # Kiểm tra bảo mật: Đảm bảo đường dẫn nằm trong thư mục Dự án
        try:
            source_path.resolve().relative_to(project_dir.resolve())
        except ValueError:
            raise HTTPException(status_code=403, detail="Cấm truy cập tệp ngoài thư mục Dự án")

        source_path.write_text(content, encoding="utf-8")
        return {"success": True, "path": f"source/{filename}"}

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Dự án '{project_name}' 不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Xử lý yêu cầu Thất bại")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/projects/{project_name}/source/{filename}")
async def delete_source_file(project_name: str, filename: str, _user: CurrentUser):
    """Xóa source 文件"""
    try:
        project_dir = get_project_manager().get_project_path(project_name)
        source_path = project_dir / "source" / filename

        # Kiểm tra bảo mật: Đảm bảo đường dẫn nằm trong thư mục Dự án
        try:
            source_path.resolve().relative_to(project_dir.resolve())
        except ValueError:
            raise HTTPException(status_code=403, detail="Cấm truy cập tệp ngoài thư mục Dự án")

        if source_path.exists():
            source_path.unlink()
            return {"success": True}
        else:
            raise HTTPException(status_code=404, detail=f"Tệp không tồn tại: {filename}")

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Dự án '{project_name}' 不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Xử lý yêu cầu Thất bại")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Quản lý tập tin nháp ======================


@router.get("/projects/{project_name}/drafts")
async def list_drafts(project_name: str, _user: CurrentUser):
    """Liệt kê tất cả thư mục và tệp nháp của dự án"""
    try:
        project_dir = get_project_manager().get_project_path(project_name)
        drafts_dir = project_dir / "drafts"

        result = {}
        if drafts_dir.exists():
            for episode_dir in sorted(drafts_dir.iterdir()):
                if episode_dir.is_dir() and episode_dir.name.startswith("episode_"):
                    episode_num = episode_dir.name.replace("episode_", "")
                    files = []
                    for f in sorted(episode_dir.glob("*.md")):
                        files.append(
                            {
                                "name": f.name,
                                "step": _extract_step_number(f.name),
                                "title": _get_step_title(f.name),
                                "size": f.stat().st_size,
                                "modified": f.stat().st_mtime,
                            }
                        )
                    result[episode_num] = files

        return {"drafts": result}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Dự án '{project_name}' 不存在")


def _extract_step_number(filename: str) -> int:
    """Trích xuất số bước từ tên tệp"""
    import re

    match = re.search(r"step(\d+)", filename)
    return int(match.group(1)) if match else 0


def _get_step_files(content_mode: str) -> dict:
    """Lấy ánh xạ tên tệp bước dựa trên content_mode"""
    if content_mode == "narration":
        return {1: "step1_segments.md"}
    else:
        return {1: "step1_normalized_script.md"}


def _get_step_title(filename: str) -> str:
    """Lấy tiêu đề bước"""
    titles = {
        "step1_normalized_script.md": "Chuẩn hóa kịch bản",
        "step1_segments.md": "Đoạn拆分",
    }
    return titles.get(filename, filename)


def _get_content_mode(project_dir: Path) -> str:
    """Đọc content_mode từ project.json"""
    project_json_path = project_dir / "project.json"
    if project_json_path.exists():
        with open(project_json_path, encoding="utf-8") as f:
            project_data = json.load(f)
            return project_data.get("content_mode", "drama")
    return "drama"


@router.get("/projects/{project_name}/drafts/{episode}/step{step_num}")
async def get_draft_content(project_name: str, episode: int, step_num: int, _user: CurrentUser):
    """Lấy nội dung nháp của bước cụ thể"""
    try:
        project_dir = get_project_manager().get_project_path(project_name)
        content_mode = _get_content_mode(project_dir)
        step_files = _get_step_files(content_mode)

        if step_num not in step_files:
            raise HTTPException(status_code=400, detail=f"không hợp lệSố bước: {step_num}")

        draft_path = project_dir / "drafts" / f"episode_{episode}" / step_files[step_num]

        if not draft_path.exists():
            raise HTTPException(status_code=404, detail="Tệp nháp không tồn tại")

        content = draft_path.read_text(encoding="utf-8")
        return PlainTextResponse(content)

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Dự án '{project_name}' 不存在")


@router.put("/projects/{project_name}/drafts/{episode}/step{step_num}")
async def update_draft_content(
    project_name: str,
    episode: int,
    step_num: int,
    _user: CurrentUser,
    content: str = Body(..., media_type="text/plain"),
):
    """Cập nhật nội dung nháp"""
    try:
        project_dir = get_project_manager().get_project_path(project_name)
        content_mode = _get_content_mode(project_dir)
        step_files = _get_step_files(content_mode)

        if step_num not in step_files:
            raise HTTPException(status_code=400, detail=f"không hợp lệSố bước: {step_num}")

        drafts_dir = project_dir / "drafts" / f"episode_{episode}"
        drafts_dir.mkdir(parents=True, exist_ok=True)

        draft_path = drafts_dir / step_files[step_num]
        is_new = not draft_path.exists()
        draft_path.write_text(content, encoding="utf-8")

        # Phát sự kiện nháp thông báo frontend
        action = "created" if is_new else "updated"
        label_prefix = "Đoạn拆分" if content_mode == "narration" else "Chuẩn hóa kịch bản"
        change = {
            "entity_type": "draft",
            "action": action,
            "entity_id": f"episode_{episode}_step{step_num}",
            "label": f"Không. {episode} 集{label_prefix}",
            "episode": episode,
            "focus": {
                "pane": "episode",
                "episode": episode,
            },
            "important": is_new,
        }
        try:
            emit_project_change_batch(project_name, [change], source="worker")
        except Exception:
            logger.warning("Gửi sự kiện nháp thất bại project=%s episode=%s", project_name, episode, exc_info=True)

        return {"success": True, "path": str(draft_path.relative_to(project_dir))}

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Dự án '{project_name}' 不存在")


@router.delete("/projects/{project_name}/drafts/{episode}/step{step_num}")
async def delete_draft(project_name: str, episode: int, step_num: int, _user: CurrentUser):
    """Xóa草稿文件"""
    try:
        project_dir = get_project_manager().get_project_path(project_name)
        content_mode = _get_content_mode(project_dir)
        step_files = _get_step_files(content_mode)

        if step_num not in step_files:
            raise HTTPException(status_code=400, detail=f"không hợp lệSố bước: {step_num}")

        draft_path = project_dir / "drafts" / f"episode_{episode}" / step_files[step_num]

        if draft_path.exists():
            draft_path.unlink()
            return {"success": True}
        else:
            raise HTTPException(status_code=404, detail="Tệp nháp không tồn tại")

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Dự án '{project_name}' 不存在")


# ==================== Phong cáchẢnh tham chiếuQuản lý ======================


@router.post("/projects/{project_name}/style-image")
async def upload_style_image(project_name: str, _user: CurrentUser, file: UploadFile = File(...)):
    """
    Tải lên ảnh tham chiếu phong cáchVà phân tích phong cách

    1. LưuẢnhĐến projects/{project_name}/style_reference.png
    2. Gọi Gemini API để phân tích Phong cách
    3. Cập nhật style_image và style_description trong project.json từ đoạn
    """
    # Kiểm tra loại tệp
    ext = Path(file.filename).suffix.lower()
    if ext not in [".png", ".jpg", ".jpeg", ".webp"]:
        raise HTTPException(
            status_code=400,
            detail=f"Loại tệp không được hỗ trợ {ext}，Loại được phép: .png, .jpg, .jpeg, .webp",
        )

    try:
        project_dir = get_project_manager().get_project_path(project_name)

        # LưuẢnh（Nén thành JPEG nếu lớn hơn 2MB, nếu không kiểm tra và lưu nguyên dạng
        content = await file.read()
        try:
            content, ext = normalize_uploaded_image(content, Path(file.filename).suffix.lower())
        except ValueError:
            raise HTTPException(status_code=400, detail="không hợp lệTệp ảnh không thể phân tích")
        style_filename = f"style_reference{ext}"

        output_path = project_dir / style_filename
        with open(output_path, "wb") as f:
            f.write(content)

        # Gọi TextGenerator để phân tích Phong cách (tự động theo dõi sử dụng)
        from lib.text_backends.base import ImageInput, TextGenerationRequest, TextTaskType
        from lib.text_backends.prompts import STYLE_ANALYSIS_PROMPT
        from lib.text_generator import TextGenerator

        generator = await TextGenerator.create(TextTaskType.STYLE_ANALYSIS, project_name)
        result = await generator.generate(
            TextGenerationRequest(prompt=STYLE_ANALYSIS_PROMPT, images=[ImageInput(path=output_path)]),
            project_name=project_name,
        )
        style_description = result.text

        # Cập nhật project.json
        project_data = get_project_manager().load_project(project_name)
        project_data["style_image"] = style_filename
        project_data["style_description"] = style_description
        with project_change_source("webui"):
            get_project_manager().save_project(project_name, project_data)

        return {
            "success": True,
            "style_image": style_filename,
            "style_description": style_description,
            "url": f"/api/v1/files/{project_name}/{style_filename}",
        }

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Dự án '{project_name}' 不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Xử lý yêu cầu Thất bại")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/projects/{project_name}/style-image")
async def delete_style_image(project_name: str, _user: CurrentUser):
    """
    XóaPhong cáchẢnh tham chiếuVà các đoạn liên quan
    """
    try:
        project_dir = get_project_manager().get_project_path(project_name)

        # XóaẢnhTệp (tương thích tất cả các hậu tố có thể)
        for suffix in (".jpg", ".jpeg", ".png", ".webp"):
            image_path = project_dir / f"style_reference{suffix}"
            if image_path.exists():
                image_path.unlink()

        # Xóa project.json Trong các đoạn liên quan
        project_data = get_project_manager().load_project(project_name)
        project_data.pop("style_image", None)
        project_data.pop("style_description", None)
        with project_change_source("webui"):
            get_project_manager().save_project(project_name, project_data)

        return {"success": True}

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Dự án '{project_name}' 不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Xử lý yêu cầu Thất bại")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/projects/{project_name}/style-description")
async def update_style_description(
    project_name: str, _user: CurrentUser, style_description: str = Body(..., embed=True)
):
    """
    Update Style Description（手动Chỉnh sửa）
    """
    try:
        project_data = get_project_manager().load_project(project_name)
        project_data["style_description"] = style_description
        with project_change_source("webui"):
            get_project_manager().save_project(project_name, project_data)

        return {"success": True, "style_description": style_description}

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Dự án '{project_name}' 不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Xử lý yêu cầu Thất bại")
        raise HTTPException(status_code=500, detail=str(e))
