"""
Công cụ xác thực dữ liệu

Xác thực tính toàn vẹn cấu trúc dữ liệu và tính nhất quán tham chiếu của project.json và episode JSON.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ValidationResult:
    """Kết quả xác thực"""

    valid: bool
    errors: list[str] = field(default_factory=list)  # Danh sách lỗi (ngăn không tiếp tục)
    warnings: list[str] = field(default_factory=list)  # Cảnh báodanh sách（Chỉ cảnh báo)

    def __str__(self) -> str:
        if self.valid:
            msg = "Xác thực thành công"
            if self.warnings:
                msg += f"\nCảnh báo ({len(self.warnings)}):\n" + "\n".join(f"  - {warning}" for warning in self.warnings)
            return msg

        msg = f"Xác thực thất bại ({len(self.errors)} Lỗi)"
        msg += "\nLỗi:" + "\n".join(f"  - {error}" for error in self.errors)
        if self.warnings:
            msg += f"\nCảnh báo ({len(self.warnings)}):\n" + "\n".join(f"  - {warning}" for warning in self.warnings)
        return msg


class DataValidator:
    """Trình xác thực dữ liệu"""

    VALID_CONTENT_MODES = {"narration", "drama"}
    VALID_DURATIONS = {4, 6, 8}
    VALID_CLUE_TYPES = {"prop", "location"}
    VALID_CLUE_IMPORTANCE = {"major", "minor"}
    VALID_SCENE_TYPES = {"Cốt truyện", "Cảnh trống"}
    ID_PATTERN = re.compile(r"^E\d+S\d+(?:_\d+)?$")
    EXTERNAL_URI_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")
    ALLOWED_ROOT_ENTRIES = {
        "project.json",
        "style_reference.png",
        "style_reference.jpg",
        "style_reference.jpeg",
        "style_reference.webp",
        "source",
        "scripts",
        "drafts",
        "characters",
        "clues",
        "storyboards",
        "videos",
        "thumbnails",
        "output",
        "versions",
    }

    def __init__(self, projects_root: str | None = None):
        """
        Khởi tạo bộ xác thực

        Args:
            projects_root: Dự ánThư mục gốc, mặc định là projects/
        """
        import os

        if projects_root is None:
            projects_root = os.environ.get("AI_ANIME_PROJECTS", "projects")
        self.projects_root = Path(projects_root)

    def _load_json(self, file_path: Path) -> dict[str, Any] | None:
        """Tải tệp JSON"""
        try:
            with open(file_path, encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None

    @staticmethod
    def _is_hidden_path(path: Path) -> bool:
        return any(part.startswith(".") or part == "__MACOSX" for part in path.parts)

    def _resolve_existing_path(
        self,
        project_dir: Path,
        raw_path: str,
        *,
        default_dir: str | None = None,
    ) -> tuple[str | None, str | None]:
        normalized = str(raw_path).strip().replace("\\", "/")
        if not normalized:
            return None, "Đường dẫn không được để trống"

        candidate_paths = [Path(normalized)]
        if default_dir and len(candidate_paths[0].parts) == 1:
            candidate_paths.append(Path(default_dir) / candidate_paths[0])

        project_root = project_dir.resolve()
        seen: set[str] = set()
        for candidate in candidate_paths:
            candidate_key = candidate.as_posix()
            if candidate_key in seen:
                continue
            seen.add(candidate_key)

            try:
                resolved = (project_dir / candidate).resolve(strict=False)
                resolved.relative_to(project_root)
            except ValueError:
                return None, f"Vượt quá phạm vi đường dẫn tham chiếu: {normalized}"

            if resolved.exists():
                return candidate.as_posix(), None

        return None, f"Tệp được tham chiếu không tồn tại: {normalized}"

    def _validate_local_reference(
        self,
        project_dir: Path,
        value: Any,
        errors: list[str],
        field_name: str,
        *,
        default_dir: str | None = None,
        allow_external: bool = False,
    ) -> str | None:
        if value in (None, ""):
            return None
        if not isinstance(value, str):
            errors.append(f"{field_name} Phải là chuỗi")
            return None

        raw_value = value.strip()
        if not raw_value:
            return None

        if self.EXTERNAL_URI_PATTERN.match(raw_value):
            if allow_external:
                return raw_value
            errors.append(f"{field_name} Phải là đường dẫn tương đối trong Dự án: {raw_value}")
            return None

        resolved_path, error = self._resolve_existing_path(
            project_dir,
            raw_value,
            default_dir=default_dir,
        )
        if error:
            errors.append(f"{field_name}: {error}")
        return resolved_path

    def _validate_project_payload(
        self,
        project: dict[str, Any],
        errors: list[str],
        warnings: list[str],
    ) -> None:
        if not project.get("title"):
            errors.append("Thiếu trường bắt buộc: title")

        content_mode = project.get("content_mode")
        if not content_mode:
            errors.append("Thiếu trường bắt buộc: content_mode")
        elif content_mode not in self.VALID_CONTENT_MODES:
            errors.append(f"content_mode Giá trị không hợp lệ: '{content_mode}'，Phải là {self.VALID_CONTENT_MODES}")

        if not project.get("style"):
            errors.append("Thiếu trường bắt buộc: style")

        episodes = project.get("episodes", [])
        if not isinstance(episodes, list):
            errors.append("episodes Phải là mảng")
        else:
            for index, episode in enumerate(episodes):
                prefix = f"episodes[{index}]"
                if not isinstance(episode, dict):
                    errors.append(f"{prefix}: Lỗi định dạng dữ liệu, phải là đối tượng")
                    continue

                if not isinstance(episode.get("episode"), int):
                    errors.append(f"{prefix}: Thiếu trường bắt buộc: episode (số nguyên)")
                if not episode.get("title"):
                    errors.append(f"{prefix}: Thiếu trường bắt buộc: title")

                script_file = episode.get("script_file")
                if not script_file:
                    errors.append(f"{prefix}: Thiếu trường bắt buộc: script_file")
                elif not isinstance(script_file, str):
                    errors.append(f"{prefix}: script_file Phải là chuỗi")

        characters = project.get("characters", {})
        if isinstance(characters, dict):
            for char_name, char_data in characters.items():
                if not isinstance(char_data, dict):
                    errors.append(f"Nhân vật '{char_name}' Lỗi định dạng dữ liệu, phải là đối tượng")
                    continue
                if not char_data.get("description"):
                    errors.append(f"Nhân vật '{char_name}' Thiếu trường bắt buộc: description")

        clues = project.get("clues", {})
        if isinstance(clues, dict):
            for clue_name, clue_data in clues.items():
                if not isinstance(clue_data, dict):
                    errors.append(f"Manh mối '{clue_name}' Lỗi định dạng dữ liệu, phải là đối tượng")
                    continue

                clue_type = clue_data.get("type")
                if not clue_type:
                    errors.append(f"Manh mối '{clue_name}' Thiếu trường bắt buộc: type")
                elif clue_type not in self.VALID_CLUE_TYPES:
                    errors.append(f"Manh mối '{clue_name}' type Giá trị không hợp lệ: '{clue_type}'，Phải là {self.VALID_CLUE_TYPES}")

                if not clue_data.get("description"):
                    errors.append(f"Manh mối '{clue_name}' Thiếu trường bắt buộc: description")

                importance = clue_data.get("importance")
                if not importance:
                    errors.append(f"Manh mối '{clue_name}' Thiếu trường bắt buộc: importance")
                elif importance not in self.VALID_CLUE_IMPORTANCE:
                    errors.append(
                        f"Manh mối '{clue_name}' importance Giá trị không hợp lệ: '{importance}'，Phải là {self.VALID_CLUE_IMPORTANCE}"
                    )

    def validate_project(self, project_name: str) -> ValidationResult:
        """Xác minh project.json"""
        return self.validate_project_dir(self.projects_root / project_name)

    def validate_project_dir(self, project_dir: Path) -> ValidationResult:
        """Xác minh project.json trong thư mục được chỉ định."""
        errors: list[str] = []
        warnings: list[str] = []

        project_path = Path(project_dir) / "project.json"
        project = self._load_json(project_path)
        if project is None:
            return ValidationResult(
                valid=False,
                errors=[f"Không thể tải project.json: {project_path}"],
            )

        self._validate_project_payload(project, errors, warnings)
        return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)

    def _validate_generated_assets(
        self,
        project_dir: Path,
        prefix: str,
        assets: Any,
        errors: list[str],
    ) -> None:
        if assets in (None, ""):
            return
        if not isinstance(assets, dict):
            errors.append(f"{prefix}.generated_assets Phải là một đối tượng")
            return

        self._validate_local_reference(
            project_dir,
            assets.get("storyboard_image"),
            errors,
            f"{prefix}.generated_assets.storyboard_image",
            default_dir="storyboards",
        )
        self._validate_local_reference(
            project_dir,
            assets.get("video_clip"),
            errors,
            f"{prefix}.generated_assets.video_clip",
            default_dir="videos",
        )
        self._validate_local_reference(
            project_dir,
            assets.get("video_uri"),
            errors,
            f"{prefix}.generated_assets.video_uri",
            default_dir="videos",
            allow_external=True,
        )

    def _validate_segments(
        self,
        segments: list[dict[str, Any]],
        project_characters: set[str],
        project_clues: set[str],
        errors: list[str],
        warnings: list[str],
        *,
        project_dir: Path | None = None,
    ) -> None:
        """Xác minh các segments (chế độ narration)"""
        if not segments:
            errors.append("segments Mảng trống")
            return

        for index, segment in enumerate(segments):
            prefix = f"segments[{index}]"

            segment_id = segment.get("segment_id")
            if not segment_id:
                errors.append(f"{prefix}: Thiếu trường bắt buộc: segment_id")
            elif not self.ID_PATTERN.match(segment_id):
                errors.append(f"{prefix}: định dạng segment_id không hợp lệ '{segment_id}'，Phải là E{{n}}S{{nn}}")

            duration = segment.get("duration_seconds")
            if duration is None:
                warnings.append(f"{prefix}: Thiếu duration_seconds, sẽ sử dụng giá trị mặc định 4")
            elif duration not in self.VALID_DURATIONS:
                errors.append(f"{prefix}: duration_seconds Giá trị không hợp lệ '{duration}'，Phải là {self.VALID_DURATIONS}")

            if not segment.get("novel_text"):
                errors.append(f"{prefix}: Thiếu đoạn bắt buộc novel_text")

            chars_in_segment = segment.get("characters_in_segment")
            if chars_in_segment is None:
                errors.append(f"{prefix}: Thiếu đoạn bắt buộc characters_in_segment")
            elif not isinstance(chars_in_segment, list):
                errors.append(f"{prefix}: characters_in_segment Phải là mảng")
            else:
                invalid = set(chars_in_segment) - project_characters
                if invalid:
                    errors.append(f"{prefix}: characters_in_segment Tham chiếu đến Nhân vật không tồn tại trong project.json: {invalid}")

            clues_in_segment = segment.get("clues_in_segment")
            if clues_in_segment is None:
                warnings.append(f"{prefix}: Thiếu clues_in_segment, sẽ sử dụng mảng trống mặc định")
            elif not isinstance(clues_in_segment, list):
                errors.append(f"{prefix}: clues_in_segment Phải là mảng")
            else:
                invalid = set(clues_in_segment) - project_clues
                if invalid:
                    errors.append(f"{prefix}: clues_in_segment Tham chiếu đến Manh mối không tồn tại trong project.json: {invalid}")

            if not segment.get("image_prompt"):
                errors.append(f"{prefix}: Thiếu đoạn bắt buộc image_prompt")
            if not segment.get("video_prompt"):
                errors.append(f"{prefix}: Thiếu đoạn bắt buộc video_prompt")

            if project_dir is not None:
                self._validate_generated_assets(
                    project_dir,
                    prefix,
                    segment.get("generated_assets"),
                    errors,
                )

    def _validate_scenes(
        self,
        scenes: list[dict[str, Any]],
        project_characters: set[str],
        project_clues: set[str],
        errors: list[str],
        warnings: list[str],
        *,
        project_dir: Path | None = None,
    ) -> None:
        """Xác thực scenes (chế độ drama)"""
        if not scenes:
            errors.append("scenes Mảng trống")
            return

        for index, scene in enumerate(scenes):
            prefix = f"scenes[{index}]"

            scene_id = scene.get("scene_id")
            if not scene_id:
                errors.append(f"{prefix}: Thiếu đoạn bắt buộc scene_id")
            elif not self.ID_PATTERN.match(scene_id):
                errors.append(f"{prefix}: định dạng scene_id không đúng '{scene_id}'，Phải là E{{n}}S{{nn}}")

            scene_type = scene.get("scene_type")
            if not scene_type:
                errors.append(f"{prefix}: Thiếu đoạn bắt buộc scene_type")
            elif scene_type not in self.VALID_SCENE_TYPES:
                errors.append(f"{prefix}: scene_type Giá trị không hợp lệ '{scene_type}'，Phải là {self.VALID_SCENE_TYPES}")

            duration = scene.get("duration_seconds")
            if duration is None:
                warnings.append(f"{prefix}: Thiếu duration_seconds, sẽ sử dụng giá trị mặc định 8")
            elif duration not in self.VALID_DURATIONS:
                errors.append(f"{prefix}: duration_seconds Giá trị không hợp lệ '{duration}'，Phải là {self.VALID_DURATIONS}")

            chars_in_scene = scene.get("characters_in_scene")
            if chars_in_scene is None:
                errors.append(f"{prefix}: Thiếu đoạn bắt buộc characters_in_scene")
            elif not isinstance(chars_in_scene, list):
                errors.append(f"{prefix}: characters_in_scene Phải là mảng")
            else:
                invalid = set(chars_in_scene) - project_characters
                if invalid:
                    errors.append(f"{prefix}: characters_in_scene Tham chiếu đến Nhân vật không tồn tại trong project.json: {invalid}")

            clues_in_scene = scene.get("clues_in_scene")
            if clues_in_scene is None:
                warnings.append(f"{prefix}: Thiếu clues_in_scene, sẽ sử dụng mảng trống mặc định")
            elif not isinstance(clues_in_scene, list):
                errors.append(f"{prefix}: clues_in_scene Phải là mảng")
            else:
                invalid = set(clues_in_scene) - project_clues
                if invalid:
                    errors.append(f"{prefix}: clues_in_scene Tham chiếu đến Manh mối không tồn tại trong project.json: {invalid}")

            if not scene.get("image_prompt"):
                errors.append(f"{prefix}: Thiếu đoạn bắt buộc image_prompt")
            if not scene.get("video_prompt"):
                errors.append(f"{prefix}: Thiếu đoạn bắt buộc video_prompt")

            if project_dir is not None:
                self._validate_generated_assets(
                    project_dir,
                    prefix,
                    scene.get("generated_assets"),
                    errors,
                )

    def _validate_episode_payload(
        self,
        project_dir: Path,
        project: dict[str, Any],
        episode: dict[str, Any],
        errors: list[str],
        warnings: list[str],
    ) -> None:
        project_characters = set(project.get("characters", {}).keys())
        project_clues = set(project.get("clues", {}).keys())

        if not isinstance(episode.get("episode"), int):
            errors.append("Thiếu đoạn bắt buộc: episode (số nguyên)")

        if not episode.get("title"):
            errors.append("Thiếu trường bắt buộc: title")

        content_mode = episode.get(
            "content_mode",
            project.get("content_mode", "narration"),
        )

        characters_in_episode = episode.get("characters_in_episode")
        if characters_in_episode is not None:
            warnings.append("characters_in_episode từĐoạn đã lỗi thời (được tính toán khi đọc), có thể Xóa an toàn")

        clues_in_episode = episode.get("clues_in_episode")
        if clues_in_episode is not None:
            warnings.append("clues_in_episode từĐoạn đã lỗi thời (được tính toán khi đọc), có thể Xóa an toàn")

        novel = episode.get("novel")
        if novel is not None and not isinstance(novel, dict):
            errors.append("novel từĐoạn phải là đối tượng")

        if content_mode == "narration":
            self._validate_segments(
                episode.get("segments", []),
                project_characters,
                project_clues,
                errors,
                warnings,
                project_dir=project_dir,
            )
        else:
            self._validate_scenes(
                episode.get("scenes", []),
                project_characters,
                project_clues,
                errors,
                warnings,
                project_dir=project_dir,
            )

    def validate_episode(self, project_name: str, episode_file: str) -> ValidationResult:
        """Xác thực episode JSON"""
        return self.validate_episode_file(self.projects_root / project_name, episode_file)

    def validate_episode_file(
        self,
        project_dir: Path,
        episode_file: str | Path,
    ) -> ValidationResult:
        """Xác thực tệp Kịch bản trong thư mục chỉ định."""
        errors: list[str] = []
        warnings: list[str] = []

        project_dir = Path(project_dir)
        project_path = project_dir / "project.json"
        project = self._load_json(project_path)
        if project is None:
            return ValidationResult(
                valid=False,
                errors=[f"Không thể tải project.json: {project_path}"],
            )

        resolved_episode_path, error = self._resolve_existing_path(
            project_dir,
            str(episode_file),
            default_dir="scripts",
        )
        if error or resolved_episode_path is None:
            return ValidationResult(
                valid=False,
                errors=[f"Không thể tải tệp Kịch bản: {project_dir / str(episode_file)}"],
            )

        episode_path = project_dir / resolved_episode_path
        episode = self._load_json(episode_path)
        if episode is None:
            return ValidationResult(
                valid=False,
                errors=[f"Không thể tải tệp Kịch bản: {episode_path}"],
            )

        self._validate_episode_payload(project_dir, project, episode, errors, warnings)
        return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)

    def validate_project_tree(self, project_dir: str | Path) -> ValidationResult:
        """
        Xác thực toàn bộ thư mục Dự án.

        Ngoài cấu trúc project.json / episode, còn xác thực cả tham chiếu tệp cục bộ và tệp bổ sung cấp cao.
        """
        project_dir = Path(project_dir)
        project_result = self.validate_project_dir(project_dir)
        errors = list(project_result.errors)
        warnings = list(project_result.warnings)

        project_path = project_dir / "project.json"
        project = self._load_json(project_path)
        if project is None:
            return ValidationResult(valid=False, errors=errors, warnings=warnings)

        self._validate_local_reference(
            project_dir,
            project.get("style_image"),
            errors,
            "project.style_image",
        )

        characters = project.get("characters", {})
        if isinstance(characters, dict):
            for char_name, char_data in characters.items():
                if not isinstance(char_data, dict):
                    continue
                self._validate_local_reference(
                    project_dir,
                    char_data.get("character_sheet"),
                    errors,
                    f"characters[{char_name}].character_sheet",
                    default_dir="characters",
                )
                self._validate_local_reference(
                    project_dir,
                    char_data.get("reference_image"),
                    errors,
                    f"characters[{char_name}].reference_image",
                    default_dir="characters/refs",
                )

        clues = project.get("clues", {})
        if isinstance(clues, dict):
            for clue_name, clue_data in clues.items():
                if not isinstance(clue_data, dict):
                    continue
                self._validate_local_reference(
                    project_dir,
                    clue_data.get("clue_sheet"),
                    errors,
                    f"clues[{clue_name}].clue_sheet",
                    default_dir="clues",
                )

        episodes = project.get("episodes", [])
        if isinstance(episodes, list):
            for index, episode_meta in enumerate(episodes):
                if not isinstance(episode_meta, dict):
                    continue

                script_file = episode_meta.get("script_file")
                if not isinstance(script_file, str) or not script_file.strip():
                    continue

                resolved_path = self._validate_local_reference(
                    project_dir,
                    script_file,
                    errors,
                    f"episodes[{index}].script_file",
                    default_dir="scripts",
                )
                if not resolved_path:
                    continue

                episode = self._load_json(project_dir / resolved_path)
                if episode is None:
                    errors.append(f"Không thể tải tệp Kịch bản: {project_dir / resolved_path}")
                    continue

                episode_errors: list[str] = []
                episode_warnings: list[str] = []
                self._validate_episode_payload(
                    project_dir,
                    project,
                    episode,
                    episode_errors,
                    episode_warnings,
                )
                errors.extend(episode_errors)
                warnings.extend(episode_warnings)

        if project_dir.exists():
            for child in sorted(project_dir.iterdir(), key=lambda item: item.name):
                if self._is_hidden_path(Path(child.name)):
                    continue
                if child.name not in self.ALLOWED_ROOT_ENTRIES:
                    warnings.append(f"Phát hiện tệp/thư mục bổ sung không nhận dạng được: {child.name}")

        return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)


def validate_project(
    project_name: str,
    projects_root: str | None = None,
) -> ValidationResult:
    """Xác minh project.json"""
    validator = DataValidator(projects_root)
    return validator.validate_project(project_name)


def validate_episode(
    project_name: str,
    episode_file: str,
    projects_root: str | None = None,
) -> ValidationResult:
    """Xác thực episode JSON"""
    validator = DataValidator(projects_root)
    return validator.validate_episode(project_name, episode_file)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Cách dùng: python data_validator.py <project_name> [episode_file]")
        print("  Xác thực project.json: python data_validator.py my_project")
        print("  Xác thực episode JSON: python data_validator.py my_project episode_1.json")
        sys.exit(1)

    project_name = sys.argv[1]

    if len(sys.argv) >= 3:
        episode_file = sys.argv[2]
        result = validate_episode(project_name, episode_file)
        print(f"Xác minh {project_name}/scripts/{episode_file}:")
    else:
        result = validate_project(project_name)
        print(f"Xác minh {project_name}/project.json:")

    print(result)
    sys.exit(0 if result.valid else 1)
