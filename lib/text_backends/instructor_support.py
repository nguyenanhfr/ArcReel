"""Instructor Hỗ trợ hạ cấp — Cho các mô hình không hỗ trợ đầu ra cấu trúc gốc bằng cách chèn prompt + phân tích + thử lại."""

from __future__ import annotations

import instructor
from instructor import Mode
from pydantic import BaseModel


def generate_structured_via_instructor(
    client,
    model: str,
    messages: list[dict],
    response_model: type[BaseModel],
    mode: Mode = Mode.MD_JSON,
    max_retries: int = 2,
) -> tuple[str, int | None, int | None]:
    """Tạo đầu ra cấu trúc thông qua Instructor (phiên bản đồng bộ, dành cho SDK đồng bộ như Ark).

    Trả về (json_text, input_tokens, output_tokens).
    """
    patched = instructor.from_openai(client, mode=mode)
    if patched is None:
        raise TypeError(
            f"instructor.from_openai() Trả về None — loại client {type(client).__name__} Không được hỗ trợ,"
            "Vui lòng truyền một thực thể openai.OpenAI hoặc openai.AsyncOpenAI"
        )
    result, completion = patched.chat.completions.create_with_completion(
        model=model,
        messages=messages,
        response_model=response_model,
        max_retries=max_retries,
    )
    json_text = result.model_dump_json()

    input_tokens = None
    output_tokens = None
    if completion.usage:
        input_tokens = completion.usage.prompt_tokens
        output_tokens = completion.usage.completion_tokens

    return json_text, input_tokens, output_tokens


async def generate_structured_via_instructor_async(
    client,
    model: str,
    messages: list[dict],
    response_model: type[BaseModel],
    mode: Mode = Mode.MD_JSON,
    max_retries: int = 2,
) -> tuple[str, int | None, int | None]:
    """Tạo đầu ra cấu trúc thông qua Instructor (phiên bản bất đồng bộ, dành cho OpenAI AsyncOpenAI).

    Trả về (json_text, input_tokens, output_tokens).
    """
    patched = instructor.from_openai(client, mode=mode)
    if patched is None:
        raise TypeError(
            f"instructor.from_openai() Trả về None — loại client {type(client).__name__} Không được hỗ trợ,"
            "Vui lòng truyền một thực thể openai.OpenAI hoặc openai.AsyncOpenAI"
        )
    result, completion = await patched.chat.completions.create_with_completion(
        model=model,
        messages=messages,
        response_model=response_model,
        max_retries=max_retries,
    )
    json_text = result.model_dump_json()

    input_tokens = None
    output_tokens = None
    if completion.usage:
        input_tokens = completion.usage.prompt_tokens
        output_tokens = completion.usage.completion_tokens

    return json_text, input_tokens, output_tokens


def inject_json_instruction(messages: list[dict]) -> list[dict]:
    """Chèn chỉ dẫn định dạng JSON vào messages, đảm bảo chế độ json_object có thể sử dụng.

    OpenAI API Yêu cầu prompt phải chứa "JSON" Từ khóa quan trọng để kích hoạt chế độ json_object.
    Nếu messages đã chứa "JSON"，thì trả lại bản sao nguyên trạng.
    """
    fb_messages = list(messages)
    if any("JSON" in (m.get("content") or "") for m in fb_messages):
        return fb_messages
    sys_idx = next((i for i, m in enumerate(fb_messages) if m.get("role") == "system"), None)
    if sys_idx is not None:
        orig = fb_messages[sys_idx]
        fb_messages[sys_idx] = {**orig, "content": (orig.get("content") or "") + "\nRespond in JSON format."}
    else:
        fb_messages.insert(0, {"role": "system", "content": "Respond in JSON format."})
    return fb_messages
