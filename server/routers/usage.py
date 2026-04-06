"""
API Tuyến thống kê cuộc gọi

Cung cấp một giao diện truy vấn và thống kê hồ sơ cuộc gọi.
"""

from datetime import datetime

from fastapi import APIRouter, Query

from lib.usage_tracker import UsageTracker
from server.auth import CurrentUser

router = APIRouter()

_tracker = UsageTracker()


@router.get("/usage/stats")
async def get_stats(
    _user: CurrentUser,
    project_name: str | None = Query(None, description="Tên Dự án (tùy chọn)"),
    provider: str | None = Query(None, description="Lọc theo nhà cung cấp"),
    start_date: str | None = Query(None, description="Ngày bắt đầu (YYYY-MM-DD)"),
    end_date: str | None = Query(None, description="kết thúcNgày (YYYY-MM-DD)"),
    group_by: str | None = Query(None, description="Cách nhóm: provider"),
):
    start = datetime.fromisoformat(start_date) if start_date else None
    end = datetime.fromisoformat(end_date) if end_date else None

    if group_by == "provider":
        stats = await _tracker.get_stats_grouped_by_provider(
            project_name=project_name,
            provider=provider,
            start_date=start,
            end_date=end,
        )
    else:
        stats = await _tracker.get_stats(
            project_name=project_name,
            provider=provider,
            start_date=start,
            end_date=end,
        )
    return stats


@router.get("/usage/calls")
async def get_calls(
    _user: CurrentUser,
    project_name: str | None = Query(None, description="Dự ánTên"),
    call_type: str | None = Query(None, description="Loại cuộc gọi (image/video)"),
    status: str | None = Query(None, description="Trạng thái (success/failed)"),
    start_date: str | None = Query(None, description="Ngày bắt đầu (YYYY-MM-DD)"),
    end_date: str | None = Query(None, description="kết thúcNgày (YYYY-MM-DD)"),
    page: int = Query(1, ge=1, description="Số trang"),
    page_size: int = Query(20, ge=1, le=100, description="Số bản ghi mỗi trang"),
):
    start = datetime.fromisoformat(start_date) if start_date else None
    end = datetime.fromisoformat(end_date) if end_date else None

    result = await _tracker.get_calls(
        project_name=project_name,
        call_type=call_type,
        status=status,
        start_date=start,
        end_date=end,
        page=page,
        page_size=page_size,
    )
    return result


@router.get("/usage/projects")
async def get_projects_list(_user: CurrentUser):
    projects = await _tracker.get_projects_list()
    return {"projects": projects}
