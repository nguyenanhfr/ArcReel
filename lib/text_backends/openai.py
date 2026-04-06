"""OpenAITextBackend — OpenAI Văn bảnTạo backend."""

from __future__ import annotations

import logging

from openai import AsyncOpenAI, BadRequestError

from lib.openai_shared import OPENAI_RETRYABLE_ERRORS, create_openai_client
from lib.providers import PROVIDER_OPENAI
from lib.retry import with_retry_async
from lib.text_backends.base import (
    TextCapability,
    TextGenerationRequest,
    TextGenerationResult,
    resolve_schema,
)

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-5.4-mini"


class OpenAITextBackend:
    """OpenAI Văn bảnTạo backend, hỗ trợ Chat Completions API."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ):
        # Vô hiệu hóa Thử lại tích hợp sẵn trong SDK, quản lý chiến lược Thử lại thống nhất tại lớp generate() này
        self._client = create_openai_client(api_key=api_key, base_url=base_url, max_retries=0)
        self._model = model or DEFAULT_MODEL
        self._capabilities: set[TextCapability] = {
            TextCapability.TEXT_GENERATION,
            TextCapability.STRUCTURED_OUTPUT,
            TextCapability.VISION,
        }

    @property
    def name(self) -> str:
        return PROVIDER_OPENAI

    @property
    def model(self) -> str:
        return self._model

    @property
    def capabilities(self) -> set[TextCapability]:
        return self._capabilities

    @with_retry_async(max_attempts=4, backoff_seconds=(2, 4, 8), retryable_errors=OPENAI_RETRYABLE_ERRORS)
    async def generate(self, request: TextGenerationRequest) -> TextGenerationResult:
        """Sinh Văn bản phản hồi.

        Vòng lặp Thử lại đơn bọc trọn quy trình:
        1. Thử gọi response_format gốc
        2. Nếu gặp lỗi không tương thích schema → hạ cấp xuống Instructor trong lần thử này
        3. Nếu gặp lỗi tạm thời (429/500/503/mạng) → decorator tự động Thử lại toàn bộ quá trình

        Như vậy, dù gọi gốc hay đường hạ cấp gặp lỗi tạm thời, đều được xử lý Thử lại thống nhất từ bên ngoài.
        """
        messages = _build_messages(request)
        kwargs: dict = {"model": self._model, "messages": messages}

        if request.response_schema:
            schema = resolve_schema(request.response_schema)
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "response",
                    "strict": True,
                    "schema": schema,
                },
            }

        try:
            response = await self._client.chat.completions.create(**kwargs)
        except Exception as exc:
            if request.response_schema and _is_schema_error(exc):
                logger.warning(
                    "response_format gốc thất bại (%s), hạ cấp xuống đường Instructor",
                    exc,
                )
                return await _instructor_fallback(self._client, self._model, request, messages)
            raise

        usage = response.usage
        return TextGenerationResult(
            text=response.choices[0].message.content or "",
            provider=PROVIDER_OPENAI,
            model=self._model,
            input_tokens=usage.prompt_tokens if usage else None,
            output_tokens=usage.completion_tokens if usage else None,
        )


def _build_messages(request: TextGenerationRequest) -> list[dict]:
    """Chuyển TextGenerationRequest thành định dạng OpenAI messages."""
    messages: list[dict] = []

    if request.system_prompt:
        messages.append({"role": "system", "content": request.system_prompt})

    # Tạo user message
    if request.images:
        from lib.image_backends.base import image_to_base64_data_uri

        content: list[dict] = []
        for img in request.images:
            if img.path:
                data_uri = image_to_base64_data_uri(img.path)
                content.append({"type": "image_url", "image_url": {"url": data_uri}})
            elif img.url:
                content.append({"type": "image_url", "image_url": {"url": img.url}})
        content.append({"type": "text", "text": request.prompt})
        messages.append({"role": "user", "content": content})
    else:
        messages.append({"role": "user", "content": request.prompt})

    return messages


_SCHEMA_ERROR_KEYWORDS = (
    "response_schema",
    "json_schema",
    "Unknown name",
    "Cannot find field",
    "Invalid JSON payload",
)


def _is_schema_error(exc: BaseException) -> bool:
    """Xác định bất thường có phải là lỗi do không tương thích JSON Schema hay không.

    Ngoài lỗi 400 BadRequestError tiêu chuẩn, một số proxy tương thích OpenAI (như Gemini
    endpoint tương thích) sẽ đóng gói lỗi schema upstream thành các mã trạng thái khác (như 429),
    Do đó cũng kiểm tra xem thông tin lỗi có chứa từ khóa liên quan đến schema hay không.
    """
    if isinstance(exc, BadRequestError):
        return True
    # Proxy có thể gói lỗi schema từ upstream thành mã trạng thái không phải 400
    error_str = str(exc)
    return any(kw in error_str for kw in _SCHEMA_ERROR_KEYWORDS)


async def _instructor_fallback(
    client: AsyncOpenAI,
    model: str,
    request: TextGenerationRequest,
    messages: list[dict],
) -> TextGenerationResult:
    """Instructor Hạ cấp: đường dẫn thay thế khi response_format gốc không khả dụng.

    Hàm này không thực hiện Thử lại, lỗi tạm thời sẽ được ném ra cho vòng lặp Thử lại của bên gọi xử lý统一。

    - response_schema Cho lớp Pydantic: sử dụng create_with_completion của instructor
    - response_schema Cho dict: quay lại cuộc gọi thông thường không có đầu ra có cấu trúc
    """
    from lib.text_backends.instructor_support import (
        generate_structured_via_instructor_async,
        inject_json_instruction,
    )

    if isinstance(request.response_schema, type):
        json_text, input_tokens, output_tokens = await generate_structured_via_instructor_async(
            client=client,
            model=model,
            messages=messages,
            response_model=request.response_schema,
        )
        return TextGenerationResult(
            text=json_text,
            provider=PROVIDER_OPENAI,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
    else:
        logger.info("response_schema Cho dict, không thể sử dụng Instructor, quay lại chế độ json_object")
        fb_messages = inject_json_instruction(messages)
        response = await client.chat.completions.create(
            model=model,
            messages=fb_messages,
            response_format={"type": "json_object"},
        )
        usage = response.usage
        return TextGenerationResult(
            text=response.choices[0].message.content or "",
            provider=PROVIDER_OPENAI,
            model=model,
            input_tokens=usage.prompt_tokens if usage else None,
            output_tokens=usage.completion_tokens if usage else None,
        )
