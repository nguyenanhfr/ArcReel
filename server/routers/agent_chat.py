"""
Đồng bộ điểm cuối Agent Đối thoại

Đóng gói luồng SSE Trợ lý hiện có thành chế độ yêu cầu-đáp ứng đồng bộ, để các Agent bên ngoài như OpenClaw gọi.
"""

import asyncio
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from server.agent_runtime.service import AssistantService
from server.agent_runtime.session_manager import SessionCapacityError
from server.auth import CurrentUser
from server.routers.assistant import get_assistant_service

logger = logging.getLogger(__name__)

router = APIRouter()

SYNC_CHAT_TIMEOUT = 120  # giây


class AgentChatRequest(BaseModel):
    project_name: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    message: str = Field(min_length=1)
    session_id: str | None = None


class AgentChatResponse(BaseModel):
    session_id: str
    reply: str
    status: str  # "completed" | "timeout" | "error"


def _extract_text_from_assistant_message(msg: dict) -> str:
    """Trích xuất nội dung Văn bản thuần từ loại Tin nhắn assistant."""
    content = msg.get("content", [])
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for block in content if isinstance(content, list) else []:
        if not isinstance(block, dict):
            continue
        text = block.get("text")
        if text and isinstance(text, str):
            parts.append(text)
    return "".join(parts)


TERMINAL_RUNTIME_STATUSES = {"idle", "completed", "error", "interrupted"}


async def _collect_reply(
    service: AssistantService,
    session_id: str,
    timeout: float,
) -> tuple[str, str]:
    """Đăng ký hàng đợi phiên, thu thập phản hồi của assistant cho đến khi Hoàn thành hoặc quá thời gian.

    Returns:
        (reply_text, status) — status để "completed" / "timeout" / "error"
    """
    queue = await service.session_manager.subscribe(session_id, replay_buffer=True)
    try:
        reply_parts: list[str] = []
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout

        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                status = "timeout"
                break

            try:
                message = await asyncio.wait_for(queue.get(), timeout=min(remaining, 5.0))
            except TimeoutError:
                # Kiểm tra phiên đã Hoàn thành hay chưa
                live_status = await service.session_manager.get_status(session_id)
                if live_status and live_status != "running":
                    status = "completed" if live_status in {"idle", "completed"} else live_status
                    break
                # Kiểm tra xem có quá hạn không
                if loop.time() >= deadline:
                    status = "timeout"
                    break
                continue

            msg_type = message.get("type", "")

            if msg_type == "assistant":
                text = _extract_text_from_assistant_message(message)
                if text:
                    reply_parts.append(text)

            elif msg_type == "result":
                # Kết thúc Tin nhắn: trích xuất phản hồi cuối cùng của assistant (nếu chưa nhận từ hàng đợi)
                subtype = str(message.get("subtype") or "").lower()
                is_error = bool(message.get("is_error"))
                if is_error or subtype.startswith("error"):
                    status = "error"
                else:
                    status = "completed"
                break

            elif msg_type == "runtime_status":
                runtime_status = str(message.get("status") or "").strip()
                if runtime_status in TERMINAL_RUNTIME_STATUSES and runtime_status != "running":
                    status = "completed" if runtime_status in {"idle", "completed"} else runtime_status
                    break

            elif msg_type == "_queue_overflow":
                # Hàng đợi tràn, gián đoạn
                status = "error"
                break

        return "".join(reply_parts), status

    finally:
        await service.session_manager.unsubscribe(session_id, queue)


@router.post("/agent/chat")
async def agent_chat(
    body: AgentChatRequest,
    _user: CurrentUser,
) -> AgentChatResponse:
    """Đồng bộ điểm cuối Agent Đối thoại.

    - Nếu không truyền session_id, thì tạo Phiên mới
    - Nếu truyền session_id, tiếp tục Đối thoại trong bối cảnh phiên đó
    - Kết nối nội bộ với AssistantService, thu thập phản hồi đầy đủ rồi trả về
    - Quá 120 giây thì trả về phần phản hồi đã thu thập, trạng thái là "timeout"
    """
    service = get_assistant_service()

    # Xác thực Dự án có tồn tại hay không
    try:
        service.pm.get_project_path(body.project_name)
    except (FileNotFoundError, KeyError):
        raise HTTPException(status_code=404, detail=f"Dự án '{body.project_name}' không tồn tại")

    # Nếu truyền session_id, trước tiên kiểm tra quyền sở hữu phiên
    if body.session_id:
        session = await service.get_session(body.session_id)
        if session is None:
            raise HTTPException(status_code=404, detail=f"phiên '{body.session_id}' không tồn tại")
        if session.project_name != body.project_name:
            raise HTTPException(
                status_code=400,
                detail=f"phiên '{body.session_id}' Thuộc về Dự án '{session.project_name}'，So với Dự án yêu cầu '{body.project_name}' không phù hợp",
            )

    # Thống nhất thông qua send_or_create Tạo hoặc tái sử dụng phiên và Gửi tin nhắn.
    # Dựa vào replay_buffer=True lưu trữ các Tin nhắn đã gửi, sẽ không gây ra điều kiện tranh chấp.
    try:
        result = await service.send_or_create(
            body.project_name,
            body.message,
            session_id=body.session_id,
        )
        session_id = result["session_id"]
    except SessionCapacityError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except TimeoutError:
        raise HTTPException(status_code=504, detail="SDK Hết thời gian tạo phiên")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    # Thu thập phản hồi (có timeout)
    reply, status = await _collect_reply(service, session_id, SYNC_CHAT_TIMEOUT)

    # Nếu không nhận được Văn bản nhưng có snapshot, lấy phản hồi Trợ lý mới nhất từ snapshot
    if not reply:
        try:
            snapshot = await service.get_snapshot(session_id)
            turns = snapshot.get("turns", [])
            for turn in reversed(turns):
                if turn.get("role") == "assistant":
                    blocks = turn.get("content", [])
                    text_parts = [b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text"]
                    reply = "".join(text_parts)
                    if reply:
                        break
        except Exception as exc:
            logger.warning("Lấy snapshot Thất bại session_id=%s: %s", session_id, exc)

    return AgentChatResponse(
        session_id=session_id,
        reply=reply,
        status=status,
    )
