"""
script_models.py - Kịch bảnMô hình dữ liệu

Sử dụng Pydantic để định nghĩa cấu trúc dữ liệu kịch bản, dùng cho:
1. Gemini API response_schema (Đầu ra có cấu trúc)
2. Đầu raXác minh
"""

from typing import Literal

from pydantic import BaseModel, Field, GetCoreSchemaHandler, GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import core_schema


class DurationSeconds(int):
    """Đoạn/CảnhThời lượng (giây)，Giới hạn ở 4, 6, 8.

    Thời gian chạy là int, JSON Schema tạo chuỗi enum để tương thích với Gemini API.
    """

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler: GetCoreSchemaHandler):
        return core_schema.no_info_plain_validator_function(
            cls._validate,
            serialization=core_schema.plain_serializer_function_ser_schema(int),
        )

    @classmethod
    def _validate(cls, v):
        v = int(v)
        if v not in (4, 6, 8):
            raise ValueError(f"duration must be 4, 6, or 8, got {v}")
        return v

    @classmethod
    def __get_pydantic_json_schema__(cls, _schema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        return {"enum": ["4", "6", "8"]}


# ============ Định nghĩa Loại liệt kê ============

ShotType = Literal[
    "Extreme Close-up",
    "Close-up",
    "Medium Close-up",
    "Medium Shot",
    "Medium Long Shot",
    "Long Shot",
    "Extreme Long Shot",
    "Over-the-shoulder",
    "Point-of-view",
]

CameraMotion = Literal[
    "Static",
    "Pan Left",
    "Pan Right",
    "Tilt Up",
    "Tilt Down",
    "Zoom In",
    "Zoom Out",
    "Tracking Shot",
]


class Dialogue(BaseModel):
    """Mục đối thoại"""

    speaker: str = Field(description="Người nói Tên")
    line: str = Field(description="Nội dung đối thoại")


class Composition(BaseModel):
    """Thông tin bố cục"""

    shot_type: ShotType = Field(description="Góc máyLoại")
    lighting: str = Field(description="Ánh sángMô tả，Bao gồm nguồn sáng, hướng và Không khí")
    ambiance: str = Field(description="Không khí tổng thể, phù hợp với giai điệu cảm xúc")


class ImagePrompt(BaseModel):
    """Ảnh phân cảnhTạo Prompt"""

    scene: str = Field(description="CảnhMô tả：Nhân vậtVị trí, biểu cảm, hành động, chi tiết Môi trường")
    composition: Composition = Field(description="Thông tin bố cục")


class VideoPrompt(BaseModel):
    """VideoTạo Prompt"""

    action: str = Field(description="Mô tả hành động: Nhân vật thực hiện hành động cụ thể trong Đoạn này")
    camera_motion: CameraMotion = Field(description="Chuyển động máy quay")
    ambiance_audio: str = Field(description="Âm thanh môi trường：Chỉ mô tả âm thanh trong Cảnh, cấm BGM")
    dialogue: list[Dialogue] = Field(default_factory=list, description="Đối thoạidanh sách，Chỉ điền khi Văn gốc có dấu ngoặc kép Đối thoại")


class GeneratedAssets(BaseModel):
    """Trạng thái tài nguyên tạo ra (khởi tạo trống)"""

    storyboard_image: str | None = Field(default=None, description="Đường dẫn ảnh phân cảnh")
    video_clip: str | None = Field(default=None, description="Đường dẫn video đoạn")
    video_uri: str | None = Field(default=None, description="Video URI")
    status: Literal["pending", "storyboard_ready", "completed"] = Field(default="pending", description="Trạng thái tạo")


# ============ Chế độ kể chuyện (Narration) ============


class NarrationSegment(BaseModel):
    """Đoạn trong chế độ kể chuyện"""

    segment_id: str = Field(description="ID đoạn, định dạng E{tập}S{số thứ tự} hoặc E{tập}S{số thứ tự}_{Số thứ tự con}")
    episode: int = Field(description="Thuộc Tập Phim")
    duration_seconds: DurationSeconds = Field(description="ĐoạnThời lượng (giây)")
    segment_break: bool = Field(default=False, description="Có phải là Điểm Chuyển Cảnh")
    novel_text: str = Field(description="Nguyên tác Tiểu thuyết (phải giữ nguyên, dùng cho lồng tiếng sau)")
    characters_in_segment: list[str] = Field(description="Danh sách Nhân vật xuất hiện")
    clues_in_segment: list[str] = Field(default_factory=list, description="Danh sách Manh mối xuất hiện")
    image_prompt: ImagePrompt = Field(description="Ảnh phân cảnhTạo Prompt")
    video_prompt: VideoPrompt = Field(description="VideoTạo Prompt")
    transition_to_next: Literal["cut", "fade", "dissolve"] = Field(default="cut", description="Loại Chuyển cảnh")
    note: str | None = Field(default=None, description="Ghi chú Người dùng (không tham gia sinh sản)")
    generated_assets: GeneratedAssets = Field(default_factory=GeneratedAssets, description="Trạng thái Tài nguyên được tạo")


class NovelInfo(BaseModel):
    """Thông tin Nguồn tiểu thuyết"""

    title: str = Field(description="Tiểu thuyết Tiêu đề")
    chapter: str = Field(description="chươngTên")


class NarrationEpisodeScript(BaseModel):
    """Kịch bản Tập phim theo chế độ Kể chuyện"""

    episode: int = Field(description="Số hiệu tập phim")
    title: str = Field(description="Tập phimTiêu đề")
    content_mode: Literal["narration"] = Field(default="narration", description="chế độ nội dung")
    duration_seconds: int = Field(default=0, description="Tổng Thời lượng (giây)")
    summary: str = Field(description="Tập phimTóm tắt")
    novel: NovelInfo = Field(description="Thông tin Nguồn tiểu thuyết")
    segments: list[NarrationSegment] = Field(description="Đoạndanh sách")


# ============ Chế độ hoạt hình phim（Drama） ============


class DramaScene(BaseModel):
    """Chế độ hoạt hình phimCác Cảnh"""

    scene_id: str = Field(description="ID cảnh, định dạng E{tập}S{số thứ tự} hoặc E{tập}S{số thứ tự}_{Số thứ tự con}")
    duration_seconds: DurationSeconds = Field(default=8, description="CảnhThời lượng (giây)")
    segment_break: bool = Field(default=False, description="Có phải là Điểm Chuyển Cảnh")
    scene_type: str = Field(default="Cốt truyện", description="CảnhLoại")
    characters_in_scene: list[str] = Field(description="Danh sách Nhân vật xuất hiện")
    clues_in_scene: list[str] = Field(default_factory=list, description="Danh sách Manh mối xuất hiện")
    image_prompt: ImagePrompt = Field(description="Ảnh phân cảnhPrompt Tạo (16:9 ngang)")
    video_prompt: VideoPrompt = Field(description="VideoTạo Prompt")
    transition_to_next: Literal["cut", "fade", "dissolve"] = Field(default="cut", description="Loại Chuyển cảnh")
    note: str | None = Field(default=None, description="Ghi chú Người dùng (không tham gia sinh sản)")
    generated_assets: GeneratedAssets = Field(default_factory=GeneratedAssets, description="Trạng thái Tài nguyên được tạo")


class DramaEpisodeScript(BaseModel):
    """Chế độ hoạt hình kịch bản tập phim"""

    episode: int = Field(description="Số hiệu tập phim")
    title: str = Field(description="Tập phimTiêu đề")
    content_mode: Literal["drama"] = Field(default="drama", description="chế độ nội dung")
    duration_seconds: int = Field(default=0, description="Tổng Thời lượng (giây)")
    summary: str = Field(description="Tập phimTóm tắt")
    novel: NovelInfo = Field(description="Thông tin Nguồn tiểu thuyết")
    scenes: list[DramaScene] = Field(description="Cảnhdanh sách")
