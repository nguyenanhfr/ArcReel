"""
Manh mốiQuản lý tuyến đường
"""

import logging

logger = logging.getLogger(__name__)
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from lib import PROJECT_ROOT
from lib.project_change_hints import project_change_source
from lib.project_manager import ProjectManager
from server.auth import CurrentUser

router = APIRouter()

# Khởi tạo quản lý dự án
pm = ProjectManager(PROJECT_ROOT / "projects")


def get_project_manager() -> ProjectManager:
    return pm


class CreateClueRequest(BaseModel):
    name: str
    clue_type: str  # 'prop' hoặc 'location'
    description: str
    importance: str | None = "major"  # 'major' hoặc 'minor'


class UpdateClueRequest(BaseModel):
    clue_type: str | None = None
    description: str | None = None
    importance: str | None = None
    clue_sheet: str | None = None


@router.post("/projects/{project_name}/clues")
async def add_clue(project_name: str, req: CreateClueRequest, _user: CurrentUser):
    """Thêm manh mối"""
    try:
        with project_change_source("webui"):
            project = get_project_manager().add_clue(
                project_name, req.name, req.clue_type, req.description, req.importance
            )
        return {"success": True, "clue": project["clues"][req.name]}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Dự án '{project_name}' không tồn tại")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Xử lý yêu cầu Thất bại")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/projects/{project_name}/clues/{clue_name}")
async def update_clue(project_name: str, clue_name: str, req: UpdateClueRequest, _user: CurrentUser):
    """Cập nhật manh mối"""
    try:
        manager = get_project_manager()
        project = manager.load_project(project_name)

        if clue_name not in project["clues"]:
            raise HTTPException(status_code=404, detail=f"Manh mối '{clue_name}' không tồn tại")

        clue = project["clues"][clue_name]
        if req.clue_type is not None:
            if req.clue_type not in ["prop", "location"]:
                raise HTTPException(status_code=400, detail="Manh mốiLoạiPhải là 'prop' hoặc 'location'")
            clue["type"] = req.clue_type
        if req.description is not None:
            clue["description"] = req.description
        if req.importance is not None:
            if req.importance not in ["major", "minor"]:
                raise HTTPException(status_code=400, detail="Quan trọngMức độ phải là 'major' hoặc 'minor'")
            clue["importance"] = req.importance
        if req.clue_sheet is not None:
            clue["clue_sheet"] = req.clue_sheet

        with project_change_source("webui"):
            manager.save_project(project_name, project)
        return {"success": True, "clue": clue}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Dự án '{project_name}' không tồn tại")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Xử lý yêu cầu Thất bại")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/projects/{project_name}/clues/{clue_name}")
async def delete_clue(project_name: str, clue_name: str, _user: CurrentUser):
    """XóaManh mối"""
    try:
        manager = get_project_manager()
        project = manager.load_project(project_name)

        if clue_name not in project["clues"]:
            raise HTTPException(status_code=404, detail=f"Manh mối '{clue_name}' không tồn tại")

        del project["clues"][clue_name]
        with project_change_source("webui"):
            manager.save_project(project_name, project)
        return {"success": True, "message": f"Manh mối '{clue_name}' Đã Xóa"}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Dự án '{project_name}' không tồn tại")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Xử lý yêu cầu Thất bại")
        raise HTTPException(status_code=500, detail=str(e))
