"""
Tạo API route

Xử lý các yêu cầu tạo Ảnh phân cảnh, Video, Nhân vật, Bản đồ manh mối.
Tất cả các yêu cầu tạo được đưa vào GenerationQueue, được GenerationWorker thực hiện bất đồng bộ.
"""

import logging

logger = logging.getLogger(__name__)

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from lib import PROJECT_ROOT
from lib.generation_queue import get_generation_queue
from lib.project_manager import ProjectManager
from lib.prompt_utils import (
    is_structured_image_prompt,
    is_structured_video_prompt,
)
from lib.storyboard_sequence import (
    find_storyboard_item,
    get_storyboard_items,
)
from server.auth import CurrentUser

router = APIRouter()

# Khởi tạo trình quản lý
pm = ProjectManager(PROJECT_ROOT / "projects")


def get_project_manager() -> ProjectManager:
    return pm


# ==================== Yêu cầu mô hình ====================


class GenerateStoryboardRequest(BaseModel):
    prompt: str | dict
    script_file: str


class GenerateVideoRequest(BaseModel):
    prompt: str | dict
    script_file: str
    duration_seconds: int | None = 4
    seed: int | None = None


class GenerateCharacterRequest(BaseModel):
    prompt: str


class GenerateClueRequest(BaseModel):
    prompt: str


_LEGACY_PROVIDER_NAMES: dict[str, str] = {
    "gemini": "gemini-aistudio",
    "aistudio": "gemini-aistudio",
    "vertex": "gemini-vertex",
}


def _normalize_provider_id(raw: str) -> str:
    """Chuẩn hóa tên nhà cung cấp định dạng cũ thành provider_id chuẩn."""
    return _LEGACY_PROVIDER_NAMES.get(raw, raw)


def _snapshot_image_backend(project_name: str) -> dict:
    """Chụp ảnh cấu hình nhà cung cấp, trả về từ điển có thể hợp nhất vào payload.

    Ưu tiên: image_backend cấp dự án > Hệ thốngCấp default_image_backend.
    """
    project = get_project_manager().load_project(project_name)
    project_image_backend = project.get("image_backend")  # định dạng: "provider_id/model"
    if project_image_backend and "/" in project_image_backend:
        image_provider, image_model = project_image_backend.split("/", 1)
    elif project_image_backend:
        image_provider = _normalize_provider_id(project_image_backend)
        image_model = ""
    else:
        return {}  # Nếu không có ghi đè cấp dự án, sử dụng mặc định toàn cục
    return {
        "image_provider": image_provider,
        "image_model": image_model,
    }


# ==================== Ảnh phân cảnhTạo ====================


@router.post("/projects/{project_name}/generate/storyboard/{segment_id}")
async def generate_storyboard(
    project_name: str,
    segment_id: str,
    req: GenerateStoryboardRequest,
    _user: CurrentUser,
):
    """
    Gửi nhiệm vụ tạo ảnh cảnh vào hàng đợi, trả về task_id ngay lập tức.

    Việc tạo được thực hiện bất đồng bộ bởi GenerationWorker, trạng thái được đẩy qua SSE.
    """
    try:
        get_project_manager().load_project(project_name)

        # Tải kịch bản kiểm tra Đoạn tồn tại
        script = get_project_manager().load_script(project_name, req.script_file)
        items, id_field, _, _ = get_storyboard_items(script)
        resolved = find_storyboard_item(items, id_field, segment_id)
        if resolved is None:
            raise HTTPException(status_code=404, detail=f"Đoạn/Cảnh '{segment_id}' không tồn tại")

        # Xác minh định dạng prompt
        if isinstance(req.prompt, dict):
            if not is_structured_image_prompt(req.prompt):
                raise HTTPException(
                    status_code=400,
                    detail="prompt Phải là chuỗi hoặc đối tượng chứa scene/composition",
                )
            scene_text = str(req.prompt.get("scene", "")).strip()
            if not scene_text:
                raise HTTPException(status_code=400, detail="prompt.scene không được để trống")
        elif not isinstance(req.prompt, str):
            raise HTTPException(status_code=400, detail="prompt Phải là chuỗi hoặc đối tượng")

        # Vào hàng đợi
        queue = get_generation_queue()
        image_snapshot = _snapshot_image_backend(project_name)
        result = await queue.enqueue_task(
            project_name=project_name,
            task_type="storyboard",
            media_type="image",
            resource_id=segment_id,
            script_file=req.script_file,
            payload={
                "prompt": req.prompt,
                "script_file": req.script_file,
                **image_snapshot,
            },
            source="webui",
            user_id=_user.id,
        )

        return {
            "success": True,
            "task_id": result["task_id"],
            "message": f"Phân cảnh「{segment_id}」Tác vụ tạo đã được gửi",
        }

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Xử lý yêu cầu Thất bại")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== VideoTạo ====================


@router.post("/projects/{project_name}/generate/video/{segment_id}")
async def generate_video(project_name: str, segment_id: str, req: GenerateVideoRequest, _user: CurrentUser):
    """
    Gửi nhiệm vụ tạo video vào hàng đợi, trả về task_id ngay lập tức.

    Cần có trước Ảnh phân cảnh làm khung hình bắt đầu. Tạo bởi GenerationWorker thực hiện bất đồng bộ.
    """
    try:
        get_project_manager().load_project(project_name)
        project_path = get_project_manager().get_project_path(project_name)

        # Kiểm tra Ảnh phân cảnh có tồn tại không
        storyboard_file = project_path / "storyboards" / f"scene_{segment_id}.png"
        if not storyboard_file.exists():
            raise HTTPException(status_code=400, detail=f"Vui lòng Tạo ảnh phân cảnh scene_{segment_id}.png")

        # Xác minh định dạng prompt
        if isinstance(req.prompt, dict):
            if not is_structured_video_prompt(req.prompt):
                raise HTTPException(
                    status_code=400,
                    detail="prompt Phải là chuỗi hoặc đối tượng chứa action/camera_motion",
                )
            action_text = str(req.prompt.get("action", "")).strip()
            if not action_text:
                raise HTTPException(status_code=400, detail="prompt.action không được để trống")
            dialogue = req.prompt.get("dialogue", [])
            if dialogue is not None and not isinstance(dialogue, list):
                raise HTTPException(status_code=400, detail="prompt.dialogue Phải là mảng")
        elif not isinstance(req.prompt, str):
            raise HTTPException(status_code=400, detail="prompt Phải là chuỗi hoặc đối tượng")

        # Đưa vào hàng đợi (nhà cung cấp sẽ được lớp dịch vụ phân tích tự động dựa trên cấu hình, người gọi không cần truyền)
        queue = get_generation_queue()
        result = await queue.enqueue_task(
            project_name=project_name,
            task_type="video",
            media_type="video",
            resource_id=segment_id,
            script_file=req.script_file,
            payload={
                "prompt": req.prompt,
                "script_file": req.script_file,
                "duration_seconds": req.duration_seconds,
                "seed": req.seed,
            },
            source="webui",
            user_id=_user.id,
        )

        return {
            "success": True,
            "task_id": result["task_id"],
            "message": f"Video「{segment_id}」Tác vụ tạo đã được gửi",
        }

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Xử lý yêu cầu Thất bại")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Ảnh thiết kế nhân vậtTạo ====================


@router.post("/projects/{project_name}/generate/character/{char_name}")
async def generate_character(
    project_name: str,
    char_name: str,
    req: GenerateCharacterRequest,
    _user: CurrentUser,
):
    """
    Gửi nhiệm vụ tạo Ảnh thiết kế nhân vật vào hàng đợi, ngay lập tức trả về task_id.
    """
    try:
        project = get_project_manager().load_project(project_name)

        # Kiểm tra Nhân vật có tồn tại không
        if char_name not in project.get("characters", {}):
            raise HTTPException(status_code=404, detail=f"Nhân vật '{char_name}' không tồn tại")

        # Vào hàng đợi
        queue = get_generation_queue()
        image_snapshot = _snapshot_image_backend(project_name)
        result = await queue.enqueue_task(
            project_name=project_name,
            task_type="character",
            media_type="image",
            resource_id=char_name,
            payload={
                "prompt": req.prompt,
                **image_snapshot,
            },
            source="webui",
            user_id=_user.id,
        )

        return {
            "success": True,
            "task_id": result["task_id"],
            "message": f"Nhân vật「{char_name}」Nhiệm vụ Tạo bản thiết kế đã được gửi",
        }

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Xử lý yêu cầu Thất bại")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Ảnh thiết kế manh mốiTạo ====================


@router.post("/projects/{project_name}/generate/clue/{clue_name}")
async def generate_clue(project_name: str, clue_name: str, req: GenerateClueRequest, _user: CurrentUser):
    """
    Gửi nhiệm vụ tạo Ảnh thiết kế manh mối vào hàng đợi, ngay lập tức trả về task_id.
    """
    try:
        project = get_project_manager().load_project(project_name)

        # Kiểm tra Manh mối có tồn tại không
        if clue_name not in project.get("clues", {}):
            raise HTTPException(status_code=404, detail=f"Manh mối '{clue_name}' không tồn tại")

        # Vào hàng đợi
        queue = get_generation_queue()
        image_snapshot = _snapshot_image_backend(project_name)
        result = await queue.enqueue_task(
            project_name=project_name,
            task_type="clue",
            media_type="image",
            resource_id=clue_name,
            payload={
                "prompt": req.prompt,
                **image_snapshot,
            },
            source="webui",
            user_id=_user.id,
        )

        return {
            "success": True,
            "task_id": result["task_id"],
            "message": f"Manh mối「{clue_name}」Nhiệm vụ Tạo bản thiết kế đã được gửi",
        }

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Xử lý yêu cầu Thất bại")
        raise HTTPException(status_code=500, detail=str(e))
