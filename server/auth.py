"""
Mô-đun lõi chứng nhận

Cung cấp các chức năng như tạo Mật khẩu, Tạo/xác minh mã thông báo JWT và xác minh thông tin xác thực.
Cũng hỗ trợ xác thực Khóa API (`arc-` Tiền tốMã thông báo mang).
"""

import hashlib
import logging
import os
import secrets
import string
import time
from collections import OrderedDict
from datetime import UTC
from pathlib import Path
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Query
from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash
from pydantic import BaseModel, ConfigDict

from lib import PROJECT_ROOT

logger = logging.getLogger(__name__)


class CurrentUserInfo(BaseModel):
    """Current authenticated user info."""

    id: str
    sub: str
    role: str = "admin"

    model_config = ConfigDict(frozen=True)


# JWT Bộ đệm khóa ký
_cached_token_secret: str | None = None

# Token Thời hạn hiệu lực: 7 ngày
TOKEN_EXPIRY_SECONDS = 7 * 24 * 3600

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)

# Mật khẩuBăm
_password_hash = PasswordHash.recommended()
_cached_password_hash: str | None = None


def generate_password(length: int = 16) -> str:
    """Tạo mật khẩu chữ và số ngẫu nhiên"""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def get_token_secret() -> str:
    """Nhận khóa ký JWT

    Ưu tiên sử dụng biến AUTH_TOKEN_SECRET Môi trường, nếu không sẽ tự động được tạo và lưu vào bộ nhớ đệm.
    """
    global _cached_token_secret

    env_secret = os.environ.get("AUTH_TOKEN_SECRET")
    if env_secret:
        return env_secret

    if _cached_token_secret is not None:
        return _cached_token_secret

    _cached_token_secret = secrets.token_hex(32)
    logger.info("Khóa ký JWT được tạo tự động")
    return _cached_token_secret


def create_token(username: str) -> str:
    """Tạo JWT token

    Args:
        username: Tên người dùng

    Returns:
        JWT token chuỗi
    """
    now = time.time()
    payload = {
        "sub": username,
        "iat": now,
        "exp": now + TOKEN_EXPIRY_SECONDS,
    }
    return jwt.encode(payload, get_token_secret(), algorithm="HS256")


def verify_token(token: str) -> dict | None:
    """Xác minh mã thông báo JWT

    Args:
        token: JWT token chuỗi

    Returns:
        Trả về dict tải trọng thành công, Thất bại trả về Không có
    """
    try:
        payload = jwt.decode(token, get_token_secret(), algorithms=["HS256"])
        return payload
    except (jwt.InvalidTokenError, jwt.ExpiredSignatureError):
        return None


DOWNLOAD_TOKEN_EXPIRY_SECONDS = 300  # 5 Phút


def create_download_token(username: str, project_name: str) -> str:
    """Phát hành mã thông báo tải xuống ngắn hạn để xác thực tải xuống gốc của trình duyệt"""
    now = time.time()
    payload = {
        "sub": username,
        "project": project_name,
        "purpose": "download",
        "iat": now,
        "exp": now + DOWNLOAD_TOKEN_EXPIRY_SECONDS,
    }
    return jwt.encode(payload, get_token_secret(), algorithm="HS256")


def verify_download_token(token: str, project_name: str) -> dict:
    """Xác minh mã thông báo tải xuống

    Returns:
        Trả lại lệnh tải trọng thành công

    Raises:
        jwt.ExpiredSignatureError: token Hết hạn
        jwt.InvalidTokenError: token không hợp lệ
        ValueError: purpose hoặc dự án không phù hợp
    """
    payload = jwt.decode(token, get_token_secret(), algorithms=["HS256"])
    if payload.get("purpose") != "download":
        raise ValueError("token purpose không có trận đấu")
    if payload.get("project") != project_name:
        raise ValueError("token project không có trận đấu")
    return payload


def _get_password_hash() -> str:
    """Lấy giá trị băm của Hiện tạiMật khẩu (được lưu trong bộ nhớ đệm)"""
    global _cached_password_hash
    if _cached_password_hash is None:
        raw = os.environ.get("AUTH_PASSWORD", "")
        _cached_password_hash = _password_hash.hash(raw)
    return _cached_password_hash


def check_credentials(username: str, password: str) -> bool:
    """Kiểm tra Tên người dùngMật khẩu (sử dụng so sánh hàm băm)

    Đọc từ các biến AUTH_USERNAME (quản trị viên mặc định) và AUTH_PASSWORD Môi trường.
    Xác minh băm được thực hiện ngay cả khi Tên người dùng không khớp, ngăn chặn các cuộc tấn công về thời gian.
    """
    expected_username = os.environ.get("AUTH_USERNAME", "admin")
    pw_hash = _get_password_hash()
    username_ok = secrets.compare_digest(username, expected_username)
    password_ok = _password_hash.verify(password, pw_hash)
    return username_ok and password_ok


def ensure_auth_password(env_path: str | None = None) -> str:
    """Đảm bảo AUTH_PASSWORD đã được cài đặt

    Nếu biến AUTH_PASSWORD Môi trường trống, Mật khẩu sẽ tự động được tạo và ghi vào biến Môi trường.
    Ghi lại vào tệp .env và đăng nhập vào bảng điều khiển bằng logger.warning Đầu.

    Args:
        env_path: .env Đường dẫn file, mặc định là .env trong thư mục gốc của Dự án

    Returns:
        Hiện tạiGiá trị AUTH_PASSWORD
    """
    password = os.environ.get("AUTH_PASSWORD")
    if password:
        return password

    # Tự động tạo mật khẩu
    password = generate_password()
    os.environ["AUTH_PASSWORD"] = password

    # Viết lại tập tin .env
    if env_path is None:
        env_path = str(PROJECT_ROOT / ".env")

    env_file = Path(env_path)
    try:
        if env_file.exists():
            lines = env_file.read_text().splitlines()
            new_lines = []
            found = False
            for line in lines:
                if not found and line.strip().startswith("AUTH_PASSWORD="):
                    new_lines.append(f"AUTH_PASSWORD={password}")
                    found = True
                else:
                    new_lines.append(line)
            if not found:
                new_lines.append(f"AUTH_PASSWORD={password}")
            new_content = "\n".join(new_lines) + "\n"
            # Sử dụng tính năng ghi tại chỗ (cắt + ghi) để giữ lại các inode, tương thích với Docker bind mount
            with open(env_file, "r+") as f:
                f.seek(0)
                f.write(new_content)
                f.truncate()
        else:
            env_file.write_text(f"AUTH_PASSWORD={password}\n")
    except OSError:
        logger.warning("Không thể ghi vào tệp .env: %s", env_path)

    logger.warning("Mật khẩu xác thực đã được tạo tự động, vui lòng kiểm tra trường AUTH_PASSWORD trong tệp .env")
    return password


# ---------------------------------------------------------------------------
# API Key Hỗ trợ xác thực
# ---------------------------------------------------------------------------

API_KEY_PREFIX = "arc-"
API_KEY_CACHE_TTL = 300  # 5 Phút

# LRU Bộ đệm: key_hash → (payload_dict | Không, hết hạn_at_timestamp)
# payload Không có nghĩa là khóa không tồn tại hoặc đã hết hạn (bộ nhớ đệm âm)
# Sử dụng OrderedDict để triển khai LRU: move_to_end khi bị đánh, popitem(last=False) khi bị loại
_api_key_cache: OrderedDict[str, tuple[dict | None, float]] = OrderedDict()
_API_KEY_CACHE_MAX = 512


def _hash_api_key(key: str) -> str:
    """Tính hàm băm SHA-256 của Khóa API."""
    return hashlib.sha256(key.encode()).hexdigest()


def invalidate_api_key_cache(key_hash: str) -> None:
    """Xóa ngay mục nhập bộ đệm cho key_hash đã chỉ định (được gọi khi phím Xóa)."""
    _api_key_cache.pop(key_hash, None)


def _get_cached_api_key_payload(key_hash: str) -> tuple[bool, dict | None]:
    """Tìm từ bộ đệm. Trả về (lần truy cập, tải trọng hoặc Không có). Di chuyển mục nhập để kết thúc khi nhấn (LRU)."""
    entry = _api_key_cache.get(key_hash)
    if entry is None:
        return False, None
    payload, expiry = entry
    if time.monotonic() > expiry:
        _api_key_cache.pop(key_hash, None)
        return False, None
    _api_key_cache.move_to_end(key_hash)
    return True, payload


def _set_api_key_cache(key_hash: str, payload: dict | None, expires_at_ts: float | None = None) -> None:
    """Ghi bộ đệm (với việc trục xuất LRU).

    Bộ đệm chuyển tiếp (tải trọng không phải là Không) TTL được giới hạn trên bởi thời gian hết hạn của khóa Thực tế.
    Tránh bảo mật Câu hỏi vẫn được xác minh trong bộ đệm sau khi khóa hết hạn.
    """
    if len(_api_key_cache) >= _API_KEY_CACHE_MAX:
        # Loại bỏ mục nhập cũ nhất không được sử dụng (LRU: tiêu đề OrderedDict)
        _api_key_cache.popitem(last=False)
    ttl = API_KEY_CACHE_TTL
    if payload is not None and expires_at_ts is not None:
        time_to_expiry = expires_at_ts - time.monotonic()
        if time_to_expiry <= 0:
            # key Đã hết hạn, được ghi vào bộ đệm âm
            _api_key_cache[key_hash] = (None, time.monotonic() + API_KEY_CACHE_TTL)
            return
        ttl = min(ttl, time_to_expiry)
    _api_key_cache[key_hash] = (payload, time.monotonic() + ttl)


async def _verify_api_key(token: str) -> dict | None:
    """Xác minh API Key token, trả về payload dict hoặc None (Thất bại/hết hạn/không tồn tại).

    Bộ đệm được kiểm tra nội bộ trước tiên, sau đó cơ sở dữ liệu sẽ được kiểm tra nếu bộ đệm bị thiếu.
    Cập nhật Last_used_at sau khi kiểm tra cơ sở dữ liệu thành công (nền không đồng bộ, không có phản hồi chặn).
    """
    key_hash = _hash_api_key(token)

    # truy vấn bộ đệm
    hit, cached_payload = _get_cached_api_key_payload(key_hash)
    if hit:
        return cached_payload

    # Truy vấn cơ sở dữ liệu
    from lib.db import async_session_factory
    from lib.db.repositories.api_key_repository import ApiKeyRepository

    async with async_session_factory() as session:
        async with session.begin():
            repo = ApiKeyRepository(session)
            row = await repo.get_by_hash(key_hash)

    if row is None:
        _set_api_key_cache(key_hash, None)
        return None

    # kiểm tra đã hết hạn
    expires_at = row.get("expires_at")
    expires_at_monotonic: float | None = None
    if expires_at:
        from datetime import datetime

        try:
            exp_dt = expires_at
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=UTC)
            if datetime.now(UTC) >= exp_dt:
                _set_api_key_cache(key_hash, None)
                return None
            # Chuyển đổi thời gian hết hạn thành dấu thời gian đơn điệu để tính toán giới hạn trên của bộ đệm TTL
            remaining_secs = (exp_dt - datetime.now(UTC)).total_seconds()
            expires_at_monotonic = time.monotonic() + remaining_secs
        except (ValueError, TypeError):
            logger.warning("API Key expires_at Không thể phân tích cú pháp định dạng giá trị, bỏ qua kiểm tra hết hạn: %r", expires_at)

    payload = {"sub": f"apikey:{row['name']}", "via": "apikey"}
    _set_api_key_cache(key_hash, payload, expires_at_ts=expires_at_monotonic)

    # Cập nhật không đồng bộ Last_used_at (không chặn, Lưu tham chiếu ngăn GC)
    import asyncio

    async def _touch():
        try:
            async with async_session_factory() as s:
                async with s.begin():
                    await ApiKeyRepository(s).touch_last_used(key_hash)
        except Exception:
            logger.exception("Cập nhật API Key Last_used_at Thất bại (không gây tử vong)")

    _touch_task = asyncio.create_task(_touch())
    _touch_task.add_done_callback(lambda _: None)  # suppress "never retrieved" warning

    return payload


def _verify_and_get_payload(token: str) -> dict:
    """Xác thực mã thông báo JWT một cách đồng bộ và đưa ra ngoại lệ 401 khi Thất bại. (chỉ dành cho đường dẫn JWT)"""
    payload = verify_token(token)
    if payload is None:
        raise HTTPException(
            status_code=401,
            detail="token Không hợp lệ hoặc đã hết hạn",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


async def _verify_and_get_payload_async(token: str) -> dict:
    """Mã thông báo xác minh không đồng bộ hỗ trợ chế độ API Key (arc-Tiền tố) và JWT."""
    if token.startswith(API_KEY_PREFIX):
        payload = await _verify_api_key(token)
        if payload is None:
            raise HTTPException(
                status_code=401,
                detail="API Key Không hợp lệ, hết hạn hoặc không tồn tại",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return payload
    # JWT Đường dẫn
    return _verify_and_get_payload(token)


def _payload_to_user(payload: dict) -> CurrentUserInfo:
    """Convert a verified JWT/API-key payload to CurrentUserInfo."""
    from lib.db.base import DEFAULT_USER_ID

    sub = payload.get("sub", "")
    return CurrentUserInfo(id=DEFAULT_USER_ID, sub=sub, role="admin")


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
) -> CurrentUserInfo:
    """Phụ thuộc xác thực tiêu chuẩn - hỗ trợ mã thông báo JWT và API Key Bearer."""
    payload = await _verify_and_get_payload_async(token)
    return _payload_to_user(payload)


async def get_current_user_flexible(
    token: Annotated[str | None, Depends(oauth2_scheme_optional)] = None,
    query_token: str | None = Query(None, alias="token"),
) -> CurrentUserInfo:
    """SSE Xác thực phụ thuộc — hỗ trợ cả header Authorization và tham số truy vấn ?token=."""
    raw = token or query_token
    if not raw:
        raise HTTPException(
            status_code=401,
            detail="Thiếu token xác thực",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = await _verify_and_get_payload_async(raw)
    return _payload_to_user(payload)


# Type aliases for FastAPI dependency injection
CurrentUser = Annotated[CurrentUserInfo, Depends(get_current_user)]
CurrentUserFlexible = Annotated[CurrentUserInfo, Depends(get_current_user_flexible)]
