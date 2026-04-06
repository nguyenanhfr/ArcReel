"""
script_generator.py - Kịch bảnBộ tạo

đọc Step 1/2 Tệp trung gian Markdown, gọi Backend tạo Văn bản để tạo JSON Kịch bản cuối cùng
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from pydantic import ValidationError

from lib.prompt_builders_script import (
    build_drama_prompt,
    build_narration_prompt,
)
from lib.script_models import (
    DramaEpisodeScript,
    NarrationEpisodeScript,
)
from lib.text_backends.base import TextGenerationRequest, TextTaskType
from lib.text_generator import TextGenerator

logger = logging.getLogger(__name__)


class ScriptGenerator:
    """
    Kịch bảnBộ tạo

    đọc Step 1/2 Tệp trung gian Markdown, gọi TextBackend để tạo JSON Kịch bản cuối cùng
    """

    def __init__(self, project_path: str | Path, generator: Optional["TextGenerator"] = None):
        """
        Khởi tạo bộ tạo

        Args:
            project_path: Dự ánĐường dẫn thư mục, ví dụ projects/test0205
            generator: TextGenerator Ví dụ (tùy chọn). Nếu là None thì chỉ hỗ trợ build_prompt() dry-run.
        """
        self.project_path = Path(project_path)
        self.generator = generator

        # Tải project.json
        self.project_json = self._load_project_json()
        self.content_mode = self.project_json.get("content_mode", "narration")

    @classmethod
    async def create(cls, project_path: str | Path) -> "ScriptGenerator":
        """Phương thức nhà máy bất đồng bộ, tự động tải cấu hình nhà cung cấp từ DB để tạo TextGenerator."""
        project_name = Path(project_path).name
        generator = await TextGenerator.create(TextTaskType.SCRIPT, project_name)
        return cls(project_path, generator)

    async def generate(
        self,
        episode: int,
        output_path: Path | None = None,
    ) -> Path:
        """
        Tạo Kịch bản Tập phim bất đồng bộ

        Args:
            episode: Tập phim编号
            output_path: Đầu raĐường dẫn, mặc định là scripts/episode_{episode}.json

        Returns:
            Đường dẫn tệp JSON tạo ra
        """
        if self.generator is None:
            raise RuntimeError("TextGenerator Chưa khởi tạo, vui lòng sử dụng phương thức nhà máy ScriptGenerator.create()")

        # 1. Đang tải tệp trung gian
        step1_md = self._load_step1(episode)

        # 2. Trích xuất Nhân vật và Manh mối (từ project.json)
        characters = self.project_json.get("characters", {})
        clues = self.project_json.get("clues", {})

        # 3. Xây dựng Prompt
        if self.content_mode == "narration":
            prompt = build_narration_prompt(
                project_overview=self.project_json.get("overview", {}),
                style=self.project_json.get("style", ""),
                style_description=self.project_json.get("style_description", ""),
                characters=characters,
                clues=clues,
                segments_md=step1_md,
            )
            schema = NarrationEpisodeScript
        else:
            prompt = build_drama_prompt(
                project_overview=self.project_json.get("overview", {}),
                style=self.project_json.get("style", ""),
                style_description=self.project_json.get("style_description", ""),
                characters=characters,
                clues=clues,
                scenes_md=step1_md,
            )
            schema = DramaEpisodeScript

        # 4. Gọi TextBackend
        logger.info("Đang tạo Không. %d tập Kịch bản...", episode)
        project_name = self.project_path.name
        result = await self.generator.generate(
            TextGenerationRequest(prompt=prompt, response_schema=schema),
            project_name=project_name,
        )
        response_text = result.text

        # 5. Phân tích và xác thực phản hồi
        script_data = self._parse_response(response_text, episode)

        # 6. Bổ sung một số siêu dữ liệu
        script_data = self._add_metadata(script_data, episode)

        # 7. Lưu文件
        if output_path is None:
            output_path = self.project_path / "scripts" / f"episode_{episode}.json"

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(script_data, f, ensure_ascii=False, indent=2)

        logger.info("Kịch bảnĐã LưuĐến %s", output_path)
        return output_path

    def build_prompt(self, episode: int) -> str:
        """
        Xây dựng Prompt (dành cho chế độ dry-run)

        Args:
            episode: Tập phim编号

        Returns:
            Prompt đã xây dựng
        """
        step1_md = self._load_step1(episode)
        characters = self.project_json.get("characters", {})
        clues = self.project_json.get("clues", {})

        if self.content_mode == "narration":
            return build_narration_prompt(
                project_overview=self.project_json.get("overview", {}),
                style=self.project_json.get("style", ""),
                style_description=self.project_json.get("style_description", ""),
                characters=characters,
                clues=clues,
                segments_md=step1_md,
            )
        else:
            return build_drama_prompt(
                project_overview=self.project_json.get("overview", {}),
                style=self.project_json.get("style", ""),
                style_description=self.project_json.get("style_description", ""),
                characters=characters,
                clues=clues,
                scenes_md=step1_md,
            )

    def _load_project_json(self) -> dict:
        """Tải project.json"""
        path = self.project_path / "project.json"
        if not path.exists():
            raise FileNotFoundError(f"Không tìm thấy project.json: {path}")

        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _load_step1(self, episode: int) -> str:
        """Tải file Markdown của Bước 1, hỗ trợ hai cách đặt tên file"""
        drafts_path = self.project_path / "drafts" / f"episode_{episode}"
        if self.content_mode == "narration":
            primary_path = drafts_path / "step1_segments.md"
            fallback_path = drafts_path / "step1_normalized_script.md"
        else:
            primary_path = drafts_path / "step1_normalized_script.md"
            fallback_path = drafts_path / "step1_segments.md"

        if not primary_path.exists():
            if fallback_path.exists():
                logger.warning("Không tìm thấy file Bước 1: %s, chuyển sang %s", primary_path, fallback_path)
                primary_path = fallback_path
            else:
                raise FileNotFoundError(f"Không tìm thấy file Bước 1: {primary_path}")

        with open(primary_path, encoding="utf-8") as f:
            return f.read()

    def _parse_response(self, response_text: str, episode: int) -> dict:
        """
        Phân tích và xác thực phản hồi của TextBackend

        Args:
            response_text: API Trả về JSON Văn bản
            episode: Tập phim编号

        Returns:
            Dữ liệu Kịch bản đã được xác thực từ điển
        """
        # Dọn dẹp có thể có bao bọc markdown
        text = response_text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        # Phân tích JSON
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON Phân tích thất bại: {e}")

        # Pydantic 验证
        try:
            if self.content_mode == "narration":
                validated = NarrationEpisodeScript.model_validate(data)
            else:
                validated = DramaEpisodeScript.model_validate(data)
            return validated.model_dump()
        except ValidationError as e:
            logger.warning("Cảnh báo xác thực dữ liệu: %s", e)
            # Trả lại dữ liệu gốc, cho phép một phần không phù hợp với schema
            return data

    def _add_metadata(self, script_data: dict, episode: int) -> dict:
        """
        Bổ sung siêu dữ liệu kịch bản

        Args:
            script_data: Kịch bản数据
            episode: Tập phim编号

        Returns:
            Dữ liệu kịch bản sau khi bổ sung siêu dữ liệu
        """
        # Đảm bảo các đoạn cơ bản tồn tại
        script_data.setdefault("episode", episode)
        script_data.setdefault("content_mode", self.content_mode)

        # ThêmThông tin tiểu thuyết
        if "novel" not in script_data:
            script_data["novel"] = {
                "title": self.project_json.get("title", ""),
                "chapter": f"Không.{episode}集",
            }
        # Loại bỏ source_file đã bị bỏ (AI có thể tưởng tượng)
        novel = script_data.get("novel")
        if isinstance(novel, dict):
            novel.pop("source_file", None)

        # Thêm时间戳
        now = datetime.now().isoformat()
        script_data.setdefault("metadata", {})
        script_data["metadata"]["created_at"] = now
        script_data["metadata"]["updated_at"] = now
        script_data["metadata"]["generator"] = self.generator.model if self.generator else "unknown"

        # Tính toán thống kê + tổng hợp nhân vật/gợi ý theo tập (thu thập từ đoạn/cảnh)
        if self.content_mode == "narration":
            segments = script_data.get("segments", [])
            script_data["metadata"]["total_segments"] = len(segments)
            script_data["duration_seconds"] = sum(int(s.get("duration_seconds", 4)) for s in segments)
            chars_field, clues_field = "characters_in_segment", "clues_in_segment"
            items = segments
        else:
            scenes = script_data.get("scenes", [])
            script_data["metadata"]["total_scenes"] = len(scenes)
            script_data["duration_seconds"] = sum(int(s.get("duration_seconds", 8)) for s in scenes)
            chars_field, clues_field = "characters_in_scene", "clues_in_scene"
            items = scenes

        all_chars: set[str] = set()
        all_clues: set[str] = set()
        for item in items:
            for name in item.get(chars_field, []):
                if isinstance(name, str):
                    all_chars.add(name)
            for name in item.get(clues_field, []):
                if isinstance(name, str):
                    all_clues.add(name)
        script_data.pop("characters_in_episode", None)
        script_data.pop("clues_in_episode", None)

        return script_data
