"""
VideoDự ánQuản trị WebUI - Ứng dụng chính FastAPI

Phương pháp bắt đầu:
    cd ArcReel
    uv run uvicorn server.app:app --reload --port 1241
"""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.responses import Response

from lib import PROJECT_ROOT
from lib.db import async_session_factory, close_db, init_db
from lib.generation_worker import GenerationWorker
from lib.logging_config import setup_logging
from server.auth import ensure_auth_password
from server.routers import (
    agent_chat,
    api_keys,
    assistant,
    characters,
    clues,
    cost_estimation,
    custom_providers,
    files,
    generate,
    project_events,
    projects,
    providers,
    system_config,
    tasks,
    usage,
    versions,
)
from server.routers import auth as auth_router
from server.services.project_events import ProjectEventService

# Nhật ký khởi tạo
setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Quản lý vòng đời ứng dụng"""
    # Startup
    ensure_auth_password()

    # Run Alembic migrations (auto-creates tables on first start)
    await init_db()

    # Migrate legacy .system_config.json → DB (no-op if file doesn't exist or already migrated)
    try:
        from lib.config.migration import migrate_json_to_db

        json_path = PROJECT_ROOT / "projects" / ".system_config.json"
        async with async_session_factory() as session:
            await migrate_json_to_db(session, json_path)
    except Exception as exc:
        logger.warning("JSON→DB config migration failed (non-fatal): %s", exc)

    # Sync Anthropic DB settings to env vars (Claude Agent SDK reads from os.environ)
    try:
        from lib.config.service import ConfigService, sync_anthropic_env

        async with async_session_factory() as session:
            svc = ConfigService(session)
            all_settings = await svc.get_all_settings()
            sync_anthropic_env(all_settings)
    except Exception as exc:
        logger.warning("DB→env Anthropic config sync failed (non-fatal): %s", exc)

    # Sửa chữa kết nối mềm Agent_runtime của Dự án hiện có
    from lib.project_manager import ProjectManager

    _pm = ProjectManager(PROJECT_ROOT / "projects")
    _symlink_stats = _pm.repair_all_symlinks()
    if any(v > 0 for v in _symlink_stats.values()):
        logger.info("agent_runtime Sửa chữa kết nối mềm Hoàn thành: %s", _symlink_stats)

    # Initialize async services
    await assistant.assistant_service.startup()
    assistant.assistant_service.session_manager.start_patrol()

    logger.info("Bắt đầu GenerationWorker...")
    worker = create_generation_worker()
    app.state.generation_worker = worker
    await worker.start()
    logger.info("GenerationWorker Đã bắt đầu")

    logger.info("Bắt đầu ProjectEventService...")
    project_event_service = ProjectEventService(PROJECT_ROOT)
    app.state.project_event_service = project_event_service
    await project_event_service.start()
    logger.info("ProjectEventService Đã bắt đầu")

    yield

    # Shutdown
    project_event_service = getattr(app.state, "project_event_service", None)
    if project_event_service:
        logger.info("Đang dừng ProjectEventService...")
        await project_event_service.shutdown()
        logger.info("ProjectEventService Đã dừng")
    worker = getattr(app.state, "generation_worker", None)
    if worker:
        logger.info("Đang dừng GenerationWorker...")
        await worker.stop()
        logger.info("GenerationWorker Đã dừng")
    await close_db()


# Tạo FastAPI ứng dụng
app = FastAPI(
    title="VideoDự ánWebUI quản lý",
    description="AI VideoTạo giao diện quản lý web cho không gian làm việc",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS Cấu hình
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    start = time.perf_counter()
    path = request.url.path
    _skip_log = path.startswith("/assets") or path == "/health"
    try:
        response: Response = await call_next(request)
    except Exception:
        if not _skip_log:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.exception(
                "%s %s 500 %.0fms (unhandled)",
                request.method,
                path,
                elapsed_ms,
            )
        raise
    if not _skip_log:
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "%s %s %d %.0fms",
            request.method,
            path,
            response.status_code,
            elapsed_ms,
        )
    return response


# Đăng ký lộ trình API
app.include_router(auth_router.router, prefix="/api/v1", tags=["Xác nhận"])
app.include_router(projects.router, prefix="/api/v1", tags=["Quản lý dự án"])
app.include_router(characters.router, prefix="/api/v1", tags=["Quản lý nhân vật"])
app.include_router(clues.router, prefix="/api/v1", tags=["Quản lý manh mối"])
app.include_router(files.router, prefix="/api/v1", tags=["Quản lý tập tin"])
app.include_router(generate.router, prefix="/api/v1", tags=["Tạo"])
app.include_router(versions.router, prefix="/api/v1", tags=["Quản lý phiên bản"])
app.include_router(usage.router, prefix="/api/v1", tags=["Thống kê chi phí"])
app.include_router(assistant.router, prefix="/api/v1/projects/{project_name}/assistant", tags=["Phiên trợ lý"])
app.include_router(tasks.router, prefix="/api/v1", tags=["hàng đợi nhiệm vụ"])
app.include_router(project_events.router, prefix="/api/v1", tags=["Dự ánthay đổi dòng chảy"])
app.include_router(providers.router, prefix="/api/v1", tags=["Quản lý nhà cung cấp"])
app.include_router(system_config.router, prefix="/api/v1", tags=["Cấu hình hệ thống"])
app.include_router(api_keys.router, prefix="/api/v1", tags=["Quản lý API Key"])
app.include_router(agent_chat.router, prefix="/api/v1", tags=["Agent Đối thoại"])
app.include_router(custom_providers.router, prefix="/api/v1", tags=["nhà cung cấp tùy chỉnh"])
app.include_router(cost_estimation.router, prefix="/api/v1", tags=["Ước tính chi phí"])


def create_generation_worker() -> GenerationWorker:
    return GenerationWorker()


@app.get("/health")
async def health_check():
    """kiểm tra sức khỏe"""
    return {"status": "ok", "message": "VideoDự ánQuản lý WebUI hoạt động tốt"}


@app.get("/skill.md", include_in_schema=False)
async def serve_skill_md(request: Request) -> Response:
    """Tự động hiển thị mẫu Skill.md thành {{BASE_URL}} Thay thếĐịa chỉ dịch vụ của Thực tế (không cần xác thực)."""
    from starlette.responses import PlainTextResponse

    template_path = PROJECT_ROOT / "public" / "skill.md.template"
    if not template_path.exists():
        return PlainTextResponse("skill.md Mẫu không tồn tại", status_code=404)

    template = template_path.read_text(encoding="utf-8")

    # Suy ra URL cơ sở từ yêu cầu; chỉ tin tưởng x-forwarded-proto (tiêu đề tiêu chuẩn proxy ngược),
    # host Sử dụng địa chỉ đích kết nối Thực tế và không chấp nhận x-forwarded-host vì người dùng có thể giả mạo.
    forwarded_proto = request.headers.get("x-forwarded-proto")
    scheme = forwarded_proto or request.url.scheme or "http"
    host = request.url.netloc
    base_url = f"{scheme}://{host}"

    content = template.replace("{{BASE_URL}}", base_url)
    return PlainTextResponse(content, media_type="text/markdown; charset=utf-8")


# Sản phẩm xây dựng giao diện người dùng: Dịch vụ tệp tĩnh SPA (phải được gắn sau tất cả các tuyến rõ ràng)
frontend_dist_dir = PROJECT_ROOT / "frontend" / "dist"


class SPAStaticFiles(StaticFiles):
    """Cung cấp các tạo phẩm của bản dựng Vite, các đường dẫn chưa khớp sẽ quay trở lại index.html (định tuyến SPA)."""

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404:
                return await super().get_response("index.html", scope)
            raise


if frontend_dist_dir.exists():
    app.mount("/", SPAStaticFiles(directory=frontend_dist_dir, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=1241, reload=True)
