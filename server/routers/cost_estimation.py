"""API định tuyến ước tính chi phí."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from lib import PROJECT_ROOT
from lib.config.resolver import ConfigResolver
from lib.db import async_session_factory
from lib.project_manager import ProjectManager
from lib.usage_tracker import UsageTracker
from server.auth import CurrentUser
from server.services.cost_estimation import CostEstimationService

router = APIRouter()
logger = logging.getLogger(__name__)
pm = ProjectManager(PROJECT_ROOT / "projects")


@router.get("/projects/{project_name}/cost-estimate")
async def get_cost_estimate(project_name: str, _user: CurrentUser):
    """Lấy ước tính chi phí dự án (Ước tính + Thực tế)."""
    if not pm.project_exists(project_name):
        raise HTTPException(status_code=404, detail=f"Dự án '{project_name}' 不存在")

    try:
        project_data = pm.load_project(project_name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Dự án '{project_name}' 不存在")

    # Tải tất cả kịch bản
    scripts: dict[str, dict] = {}
    for ep in project_data.get("episodes", []):
        script_file = ep.get("script_file", "")
        if script_file:
            try:
                scripts[script_file] = pm.load_script(project_name, script_file)
            except FileNotFoundError:
                logger.debug("Kịch bảnTệp không tồn tại, bỏ qua: %s/%s", project_name, script_file)

    resolver = ConfigResolver(async_session_factory)
    tracker = UsageTracker(session_factory=async_session_factory)
    service = CostEstimationService(resolver, tracker)

    try:
        return await service.compute(project_data, scripts, project_name=project_name)
    except Exception:
        logger.exception("Ước tính chi phí thất bại")
        raise HTTPException(status_code=500, detail="Ước tính chi phí thất bại，请稍后Thử lại")
