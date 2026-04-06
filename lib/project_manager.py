"""
Dự ánQuản lý tập tinThiết bị

Quản lý cấu trúc thư mục dự án Video, đọc ghi phân cảnh Kịch bản, theo dõi trạng thái.
"""

import json
import logging
import os
import re
import secrets
import unicodedata
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from lib.project_change_hints import emit_project_change_hint

logger = logging.getLogger(__name__)

PROJECT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9-]+$")
PROJECT_SLUG_SANITIZER = re.compile(r"[^a-zA-Z0-9]+")

# ==================== Mô hình dữ liệu ====================


class ProjectOverview(BaseModel):
    """Mô tả dự ánMô hình dữ liệu, dùng cho Gemini Structured Outputs"""

    synopsis: str = Field(description="Tóm tắt câu chuyện, 200-300 từ, tóm tắt cốt truyện chính")
    genre: str = Field(description="Thể loạiLoại，Ví dụ: Cung đấu cổ trang, hiện đại huyền bí, huyền huyễn tu tiên")
    theme: str = Field(description="Chủ đề cốt lõi, ví dụ: Báo thù và chuộc tội, trưởng thành và chuyển hóa")
    world_setting: str = Field(description="Bối cảnh thời đại và thiết lập thế giới quan, 100-200 từ")


class ProjectManager:
    """VideoDự ánTrình quản lý"""

    # Dự ánCấu trúc thư mục con
    SUBDIRS = [
        "source",
        "scripts",
        "drafts",
        "characters",
        "clues",
        "storyboards",
        "videos",
        "thumbnails",
        "output",
    ]

    # Dự ánMetadata tên tập tin
    PROJECT_FILE = "project.json"

    @staticmethod
    def normalize_project_name(name: str) -> str:
        """Validate and normalize a project identifier."""
        normalized = str(name).strip()
        if not normalized:
            raise ValueError("Dự ánBiểu tượng không được để trống")
        if not PROJECT_NAME_PATTERN.fullmatch(normalized):
            raise ValueError("Dự ánBiểu tượng chỉ cho phép chữ cái tiếng Anh, chữ số và dấu gạch ngang")
        return normalized

    @staticmethod
    def _slugify_project_title(title: str) -> str:
        """Build a filesystem-safe slug prefix from the project title."""
        ascii_text = unicodedata.normalize("NFKD", str(title).strip()).encode("ascii", "ignore").decode("ascii")
        slug = PROJECT_SLUG_SANITIZER.sub("-", ascii_text).strip("-_").lower()
        return slug[:24] or "project"

    def generate_project_name(self, title: str | None = None) -> str:
        """Generate a unique internal project identifier."""
        prefix = self._slugify_project_title(title or "")
        while True:
            candidate = f"{prefix}-{secrets.token_hex(4)}"
            if not (self.projects_root / candidate).exists():
                return candidate

    @classmethod
    def from_cwd(cls) -> tuple["ProjectManager", str]:
        """Suy ra ProjectManager và TênDựÁn từ thư mục làm việc hiện tại.

        Giả định cwd là ``projects/{project_name}/`` định dạng。
        Quay lại ``(ProjectManager, project_name)`` Bộ ba.
        """
        cwd = Path.cwd().resolve()
        project_name = cwd.name
        projects_root = cwd.parent
        pm = cls(projects_root)
        if not (projects_root / project_name / cls.PROJECT_FILE).exists():
            raise FileNotFoundError(f"Hiện tạiThư mục không phải là thư mục Dự án hợp lệ: {cwd}")
        return pm, project_name

    def __init__(self, projects_root: str | None = None):
        """
        Khởi tạo quản lý dự án

        Args:
            projects_root: Dự ánThư mục gốc, mặc định là thư mục projects/ dưới thư mục hiện tại
        """
        if projects_root is None:
            # Cố gắng lấy từ biến môi trường hoặc đường dẫn mặc định
            projects_root = os.environ.get("AI_ANIME_PROJECTS", "projects")

        self.projects_root = Path(projects_root)
        self.projects_root.mkdir(parents=True, exist_ok=True)

    def list_projects(self) -> list[str]:
        """Liệt kê tất cả Dự án"""
        return [d.name for d in self.projects_root.iterdir() if d.is_dir() and not d.name.startswith(".")]

    def create_project(self, name: str) -> Path:
        """
        Tạo Dự án Mới

        Args:
            name: Dự ánBiểu tượng (duy nhất toàn cầu, dùng cho URL và Hệ thống tệp)

        Returns:
            Dự ánĐường dẫn thư mục
        """
        name = self.normalize_project_name(name)
        project_dir = self.projects_root / name

        if project_dir.exists():
            raise FileExistsError(f"Dự án '{name}' Đã tồn tại")

        # TạoTất cả các thư mục con
        for subdir in self.SUBDIRS:
            (project_dir / subdir).mkdir(parents=True, exist_ok=True)

        self.repair_claude_symlink(project_dir)

        return project_dir

    def repair_claude_symlink(self, project_dir: Path) -> dict:
        """Sửa liên kết mềm .claude và CLAUDE.md trong thư mục Dự án.

        Thực hiện với mỗi liên kết mềm:
        - Hỏng (is_symlink nhưng không tồn tại) → Xóa và xây dựng lại
        - Thiếu (không tồn tại và không phải is_symlink) → Tạo
        - Bình thường (tồn tại) → Bỏ qua

        Returns:
            {"created": int, "repaired": int, "skipped": int, "errors": int}
        """
        project_root = self.projects_root.parent
        profile_dir = project_root / "agent_runtime_profile"

        SYMLINKS = {
            ".claude": profile_dir / ".claude",
            "CLAUDE.md": profile_dir / "CLAUDE.md",
        }
        REL_TARGETS = {
            ".claude": Path("../../agent_runtime_profile/.claude"),
            "CLAUDE.md": Path("../../agent_runtime_profile/CLAUDE.md"),
        }

        stats = {"created": 0, "repaired": 0, "skipped": 0, "errors": 0}
        for name, target_source in SYMLINKS.items():
            if not target_source.exists():
                continue
            symlink_path = project_dir / name
            if symlink_path.is_symlink() and not symlink_path.exists():
                # Liên kết mềm bị hỏng
                try:
                    symlink_path.unlink()
                    symlink_path.symlink_to(REL_TARGETS[name])
                    stats["repaired"] += 1
                except OSError as e:
                    logger.warning("Không thể sửa liên kết biểu tượng %s của Dự án %s: %s", project_dir.name, name, e)
                    stats["errors"] += 1
            elif not symlink_path.exists() and not symlink_path.is_symlink():
                # Thiếu
                try:
                    symlink_path.symlink_to(REL_TARGETS[name])
                    stats["created"] += 1
                except OSError as e:
                    logger.warning("Không thể tạo liên kết biểu tượng %s cho Dự án %s: %s", project_dir.name, name, e)
                    stats["errors"] += 1
            else:
                stats["skipped"] += 1
        return stats

    def repair_all_symlinks(self) -> dict:
        """Quét tất cả các thư mục Dự án, sửa các liên kết mềm.

        Returns:
            {"created": int, "repaired": int, "skipped": int, "errors": int}
        """
        totals = {"created": 0, "repaired": 0, "skipped": 0, "errors": 0}
        if not self.projects_root.exists():
            return totals
        for project_dir in sorted(self.projects_root.iterdir()):
            if not project_dir.is_dir() or project_dir.name.startswith("."):
                continue
            try:
                result = self.repair_claude_symlink(project_dir)
                for key in ("created", "repaired", "skipped", "errors"):
                    totals[key] += result.get(key, 0)
            except Exception as e:
                logger.warning("Lỗi khi sửa liên kết mềm của Dự án %s: %s", project_dir.name, e)
                totals["errors"] += 1
        return totals

    def get_project_path(self, name: str) -> Path:
        """Lấy đường dẫn Dự án (bao gồm bảo vệ truy cập đường dẫn)"""
        name = self.normalize_project_name(name)
        real = os.path.realpath(self.projects_root / name)
        base = os.path.realpath(self.projects_root) + os.sep
        if not real.startswith(base):
            raise ValueError(f"Tên Dự án không hợp lệ: '{name}'")
        project_dir = Path(real)
        if not project_dir.exists():
            raise FileNotFoundError(f"Dự án '{name}' không tồn tại")
        return project_dir

    @staticmethod
    def _safe_subpath(base_dir: Path, filename: str) -> str:
        """Kiểm tra sau khi ghép filename không vượt ra ngoài base_dir, trả về realpath của chuỗi."""
        real = os.path.realpath(base_dir / filename)
        bound = os.path.realpath(base_dir) + os.sep
        if not real.startswith(bound):
            raise ValueError(f"Tên tập tin không hợp lệ: '{filename}'")
        return real

    def get_project_status(self, name: str) -> dict[str, Any]:
        """
        Lấy trạng thái Dự án

        Returns:
            Bao gồm từ điển tình trạng Hoàn thành các giai đoạn
        """
        project_dir = self.get_project_path(name)

        status = {
            "name": name,
            "path": str(project_dir),
            "source_files": [],
            "scripts": [],
            "characters": [],
            "clues": [],
            "storyboards": [],
            "videos": [],
            "outputs": [],
            "current_stage": "empty",
        }

        # Kiểm tra nội dung từng thư mục
        for subdir in self.SUBDIRS:
            subdir_path = project_dir / subdir
            if subdir_path.exists():
                files = list(subdir_path.glob("*"))
                if subdir == "source":
                    status["source_files"] = [f.name for f in files if f.is_file()]
                elif subdir == "scripts":
                    status["scripts"] = [f.name for f in files if f.suffix == ".json"]
                elif subdir == "characters":
                    status["characters"] = [f.name for f in files if f.suffix in [".png", ".jpg", ".jpeg"]]
                elif subdir == "clues":
                    status["clues"] = [f.name for f in files if f.suffix in [".png", ".jpg", ".jpeg"]]
                elif subdir == "storyboards":
                    status["storyboards"] = [f.name for f in files if f.suffix in [".png", ".jpg", ".jpeg"]]
                elif subdir == "videos":
                    status["videos"] = [f.name for f in files if f.suffix in [".mp4", ".webm"]]
                elif subdir == "output":
                    status["outputs"] = [f.name for f in files if f.suffix in [".mp4", ".webm"]]

        # Xác định giai đoạn Hiện tại
        if status["outputs"]:
            status["current_stage"] = "completed"
        elif status["videos"]:
            status["current_stage"] = "videos_generated"
        elif status["storyboards"]:
            status["current_stage"] = "storyboards_generated"
        elif status["characters"]:
            status["current_stage"] = "characters_generated"
        elif status["scripts"]:
            status["current_stage"] = "script_created"
        elif status["source_files"]:
            status["current_stage"] = "source_ready"
        else:
            status["current_stage"] = "empty"

        return status

    # ==================== Phân cảnhKịch bảnThao tác ====================

    def create_script(self, project_name: str, title: str, chapter: str) -> dict:
        """
        TạoMẫu Phân cảnh Kịch bản mới

        Args:
            project_name: Dự ánTên
            title: Tiểu thuyết Tiêu đề
            chapter: chươngTên

        Returns:
            Kịch bảntừĐiển
        """
        script = {
            "novel": {"title": title, "chapter": chapter},
            "scenes": [],
            "metadata": {
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "total_scenes": 0,
                "estimated_duration_seconds": 0,
                "status": "draft",
            },
        }

        return script

    def save_script(self, project_name: str, script: dict, filename: str | None = None) -> Path:
        """
        LưuPhân cảnhKịch bản

        Args:
            project_name: Dự ánTên
            script: Kịch bảntừĐiển
            filename: Tên tệp tùy chọn, mặc định sử dụng tên chương

        Returns:
            LưuĐường dẫn tệp
        """
        project_dir = self.get_project_path(project_name)
        scripts_dir = project_dir / "scripts"

        if filename is not None and filename.startswith("scripts/"):
            filename = filename[len("scripts/") :]

        if filename is None:
            chapter = script["novel"].get("chapter", "chapter_01")
            filename = f"{chapter.replace(' ', '_')}_script.json"

        # Cập nhật siêu dữ liệu (tương thích với kịch bản cũ: có thể thiếu metadata, hoặc narration sử dụng segments)
        now = datetime.now().isoformat()
        metadata = script.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
            script["metadata"] = metadata
        metadata.setdefault("created_at", now)
        metadata.setdefault("status", "draft")
        metadata["updated_at"] = now

        scenes = script.get("scenes", [])
        if not isinstance(scenes, list):
            scenes = []
        segments = script.get("segments", [])
        if not isinstance(segments, list):
            segments = []

        content_mode = script.get("content_mode", "narration")
        if content_mode == "narration" and segments:
            items = segments
            items_type = "segments"
        elif scenes:
            items = scenes
            items_type = "scenes"
        else:
            items = segments
            items_type = "segments"

        metadata["total_scenes"] = len(items)

        # Tính tổng thời lượng: dựa trên cấu trúc dữ liệu được chọn hiện tại để quyết định giá trị mặc định, tránh đánh giá sai khi content_mode bị thiếu
        default_duration = 4 if items_type == "segments" else 8
        total_duration = sum(item.get("duration_seconds", default_duration) for item in items)
        metadata["estimated_duration_seconds"] = total_duration

        # LưuTệp (bao gồm bảo vệ truy cập đường dẫn)
        real = self._safe_subpath(scripts_dir, filename)
        with open(real, "w", encoding="utf-8") as f:  # noqa: PTH123
            json.dump(script, f, ensure_ascii=False, indent=2)
        output_path = Path(real)

        emit_project_change_hint(
            project_name,
            changed_paths=[f"scripts/{output_path.name}"],
        )

        # Tự động đồng bộ vào project.json
        if self.project_exists(project_name) and isinstance(script.get("episode"), int):
            self.sync_episode_from_script(project_name, filename)

        return output_path

    def sync_episode_from_script(self, project_name: str, script_filename: str) -> dict:
        """
        Đồng bộ thông tin tập từ tệp Kịch bản vào project.json

        Agent Sau khi ghi Kịch bản phải gọi phương pháp này để đảm bảo WebUI hiển thị đúng danh sách Tập phim.

        Args:
            project_name: Dự ánTên
            script_filename: Kịch bảntên tập tin（Như episode_1.json)

        Returns:
            Dự án cập nhật từ Điển
        """
        script = self.load_script(project_name, script_filename)
        project = self.load_project(project_name)

        episode_num = script.get("episode", 1)
        episode_title = script.get("title", "")
        script_file = f"scripts/{script_filename}"

        # Tìm hoặc Tạo mục episode
        episodes = project.setdefault("episodes", [])
        episode_entry = next((ep for ep in episodes if ep["episode"] == episode_num), None)

        if episode_entry is None:
            episode_entry = {"episode": episode_num}
            episodes.append(episode_entry)

        # Đồng bộ siêu dữ liệu cốt lõi (không bao gồm thống kê đoạn từ, thống kê đoạn từ được StatusCalculator tính khi đọc)
        episode_entry["title"] = episode_title
        episode_entry["script_file"] = script_file

        # Sắp xếp và Lưu
        episodes.sort(key=lambda x: x["episode"])
        self.save_project(project_name, project)

        logger.info("Đã đồng bộ thông tin Tập phim: Tập %d - %s", episode_num, episode_title)
        return project

    def load_script(self, project_name: str, filename: str) -> dict:
        """
        Tải Phân cảnh Kịch bản

        Args:
            project_name: Dự ánTên
            filename: Kịch bảntên tập tin

        Returns:
            Kịch bảntừĐiển
        """
        project_dir = self.get_project_path(project_name)
        if filename.startswith("scripts/"):
            filename = filename[len("scripts/") :]
        real = self._safe_subpath(project_dir / "scripts", filename)

        if not os.path.exists(real):
            raise FileNotFoundError(f"Kịch bảnTệp không tồn tại: {real}")

        with open(real, encoding="utf-8") as f:  # noqa: PTH123
            return json.load(f)

    def list_scripts(self, project_name: str) -> list[str]:
        """Liệt kê tất cả Kịch bản trong Dự án"""
        project_dir = self.get_project_path(project_name)
        scripts_dir = project_dir / "scripts"
        return [f.name for f in scripts_dir.glob("*.json")]

    # ==================== Nhân vậtQuản lý ======================

    def update_character_sheet(self, project_name: str, script_filename: str, name: str, sheet_path: str) -> dict:
        """Cập nhật đường dẫn Ảnh thiết kế nhân vật"""
        script = self.load_script(project_name, script_filename)

        if name not in script["characters"]:
            raise KeyError(f"Nhân vật '{name}' không tồn tại")

        script["characters"][name]["character_sheet"] = sheet_path
        self.save_script(project_name, script, script_filename)
        return script

    # ==================== Chuẩn hóa cấu trúc dữ liệu ====================

    @staticmethod
    def create_generated_assets(content_mode: str = "narration") -> dict:
        """
        TạoCấu trúc generated_assets chuẩn

        Args:
            content_mode: chế độ nội dung（'narration' hoặc 'drama'）

        Returns:
            Từ điển generated_assets chuẩn
        """
        return {
            "storyboard_image": None,
            "video_clip": None,
            "video_thumbnail": None,
            "video_uri": None,
            "status": "pending",
        }

    @staticmethod
    def create_scene_template(scene_id: str, episode: int = 1, duration_seconds: int = 8) -> dict:
        """
        TạoMẫu đối tượng Cảnh chuẩn

        Args:
            scene_id: Cảnh ID（Như "E1S01"）
            episode: Số tập
            duration_seconds: CảnhThời lượng (giây)

        Returns:
            Từ điển Cảnh chuẩn
        """
        return {
            "scene_id": scene_id,
            "episode": episode,
            "title": "",
            "scene_type": "Cốt truyện",
            "duration_seconds": duration_seconds,
            "segment_break": False,
            "characters_in_scene": [],
            "clues_in_scene": [],
            "visual": {
                "description": "",
                "shot_type": "medium shot",
                "camera_movement": "static",
                "lighting": "",
                "mood": "",
            },
            "action": "",
            "dialogue": {"speaker": "", "text": "", "emotion": "neutral"},
            "audio": {"dialogue": [], "narration": "", "sound_effects": []},
            "transition_to_next": "cut",
            "generated_assets": ProjectManager.create_generated_assets(),
        }

    def normalize_scene(self, scene: dict, episode: int = 1) -> dict:
        """
        Hoàn thiện các đoạn từ còn thiếu trong một cảnh

        Args:
            scene: CảnhtừĐiển
            episode: Số tập (dùng để hoàn thiện đoạn từ của episode)

        Returns:
            Từ điển Cảnh sau khi hoàn thiện
        """
        template = self.create_scene_template(
            scene_id=scene.get("scene_id", "000"),
            episode=episode,
            duration_seconds=scene.get("duration_seconds", 8),
        )

        # Hợp nhất đoạn từ visual
        if "visual" not in scene:
            scene["visual"] = template["visual"]
        else:
            for key in template["visual"]:
                if key not in scene["visual"]:
                    scene["visual"][key] = template["visual"][key]

        # Hợp nhất đoạn từ audio
        if "audio" not in scene:
            scene["audio"] = template["audio"]
        else:
            for key in template["audio"]:
                if key not in scene["audio"]:
                    scene["audio"][key] = template["audio"][key]

        # Hoàn thiện các đoạn từ generated_assets
        if "generated_assets" not in scene:
            scene["generated_assets"] = self.create_generated_assets()
        else:
            assets_template = self.create_generated_assets()
            for key in assets_template:
                if key not in scene["generated_assets"]:
                    scene["generated_assets"][key] = assets_template[key]

        # Hoàn thiện Khác đoạn từ cấp trên
        top_level_defaults = {
            "episode": episode,
            "title": "",
            "scene_type": "Cốt truyện",
            "segment_break": False,
            "characters_in_scene": [],
            "clues_in_scene": [],
            "action": "",
            "dialogue": template["dialogue"],
            "transition_to_next": "cut",
        }

        for key, default_value in top_level_defaults.items():
            if key not in scene:
                scene[key] = default_value

        # Cập nhật trạng thái
        self.update_scene_status(scene)

        return scene

    def update_scene_status(self, scene: dict) -> str:
        """
        Cập nhật và trả về trạng thái Cảnh dựa trên nội dung generated_assets

        Giá trị trạng thái:
        - pending: Chưa bắt đầu
        - storyboard_ready: Ảnh phân cảnhHoàn thành
        - completed: VideoHoàn thành

        Args:
            scene: CảnhtừĐiển

        Returns:
            Giá trị trạng thái sau khi cập nhật
        """
        assets = scene.get("generated_assets", {})

        has_image = bool(assets.get("storyboard_image"))
        has_video = bool(assets.get("video_clip"))

        if has_video:
            status = "completed"
        elif has_image:
            status = "storyboard_ready"
        else:
            status = "pending"

        assets["status"] = status
        return status

    def normalize_script(self, project_name: str, script_filename: str, save: bool = True) -> dict:
        """
        Hoàn thiện các đoạn từ còn thiếu trong script.json hiện có

        Args:
            project_name: Dự ánTên
            script_filename: Kịch bảntên tập tin
            save: Có lưu Kịch bản đã chỉnh sửa không

        Returns:
            Kịch bản đã hoàn thiện đoạn từ tiêu chuẩn
        """
        import re

        script = self.load_script(project_name, script_filename)

        # Suy đoán tập phim từ tên tệp hoặc dữ liệu hiện có
        episode = script.get("episode", 1)
        if not episode:
            match = re.search(r"episode[_\s]*(\d+)", script_filename, re.IGNORECASE)
            if match:
                episode = int(match.group(1))
            else:
                episode = 1

        # Hoàn thiện các đoạn từ cấp trên
        script_defaults = {
            "episode": episode,
            "title": script.get("novel", {}).get("chapter", ""),
            "duration_seconds": 0,
            "summary": "",
        }

        for key, default_value in script_defaults.items():
            if key not in script:
                script[key] = default_value

        # Đảm bảo cấu trúc cấp trên cần thiết tồn tại
        if "novel" not in script:
            script["novel"] = {"title": "", "chapter": ""}
        # Loại bỏ các đoạn source_file đã bị hủy
        if isinstance(script.get("novel"), dict):
            script["novel"].pop("source_file", None)

        # Xử lý định dạng cũ: nếu có đối tượng characters, đồng bộ vào project.json
        if "characters" in script and isinstance(script["characters"], dict) and script["characters"]:
            logger.warning("Phát hiện đối tượng characters định dạng cũ, tự động đồng bộ vào project.json")
            self.sync_characters_from_script(project_name, script_filename)
            # sync_characters_from_script Sẽ tải lại và lưu script, nên cần tải lại
            script = self.load_script(project_name, script_filename)

        # Xử lý định dạng cũ: nếu có đối tượng clues, đồng bộ vào project.json
        if "clues" in script and isinstance(script["clues"], dict) and script["clues"]:
            logger.warning("Phát hiện đối tượng clues định dạng cũ, tự động đồng bộ vào project.json")
            self.sync_clues_from_script(project_name, script_filename)
            script = self.load_script(project_name, script_filename)

        # Lưu ý: characters_in_episode và clues_in_episode đã được tính toán khi đọc
        # Không còn tạo các đoạn từ này trong normalize_script

        if "scenes" not in script:
            script["scenes"] = []

        if "metadata" not in script:
            script["metadata"] = {
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "total_scenes": 0,
                "estimated_duration_seconds": 0,
                "status": "draft",
            }

        # Chuẩn hóa từng cảnh
        for scene in script["scenes"]:
            self.normalize_scene(scene, episode)

        # Cập nhật thông tin thống kê
        script["metadata"]["total_scenes"] = len(script["scenes"])
        script["metadata"]["estimated_duration_seconds"] = sum(s.get("duration_seconds", 8) for s in script["scenes"])
        script["duration_seconds"] = script["metadata"]["estimated_duration_seconds"]

        if save:
            self.save_script(project_name, script, script_filename)
            logger.info("Kịch bảnĐã chuẩn hóa và lưu: %s", script_filename)

        return script

    # ==================== CảnhQuản lý ======================

    def add_scene(self, project_name: str, script_filename: str, scene: dict) -> dict:
        """
        Thêm cảnh vào kịch bản

        Args:
            project_name: Dự ánTên
            script_filename: Kịch bảntên tập tin
            scene: CảnhtừĐiển

        Returns:
            Kịch bản đã cập nhật
        """
        script = self.load_script(project_name, script_filename)

        # Tự động tạo ID cảnh
        existing_ids = [s["scene_id"] for s in script["scenes"]]
        next_id = f"{len(existing_ids) + 1:03d}"
        scene["scene_id"] = next_id

        # Đảm bảo có các đoạn generated_assets
        if "generated_assets" not in scene:
            scene["generated_assets"] = {
                "storyboard_image": None,
                "video_clip": None,
                "status": "pending",
            }

        script["scenes"].append(scene)
        self.save_script(project_name, script, script_filename)
        return script

    def update_scene_asset(
        self,
        project_name: str,
        script_filename: str,
        scene_id: str,
        asset_type: str,
        asset_path: str,
    ) -> dict:
        """
        Cập nhật đường dẫn tài nguyên của cảnh

        Args:
            project_name: Dự ánTên
            script_filename: Kịch bảntên tập tin
            scene_id: Cảnh/Đoạn ID
            asset_type: Loại tài nguyên ('storyboard_image' hoặc 'video_clip')
            asset_path: Đường dẫn tài nguyên

        Returns:
            Kịch bản đã cập nhật
        """
        script = self.load_script(project_name, script_filename)

        # Chọn cấu trúc dữ liệu đúng dựa trên chế độ nội dung
        content_mode = script.get("content_mode", "narration")
        if content_mode == "narration" and "segments" in script:
            items = script["segments"]
            id_field = "segment_id"
        else:
            items = script.get("scenes", [])
            id_field = "scene_id"

        for item in items:
            if str(item.get(id_field)) == str(scene_id):
                assets = item.get("generated_assets")
                if not isinstance(assets, dict):
                    assets = {}
                    item["generated_assets"] = assets

                assets_template = self.create_generated_assets(content_mode)
                for key, default_value in assets_template.items():
                    if key not in assets:
                        assets[key] = default_value

                assets[asset_type] = asset_path

                # Sử dụng update_scene_status để cập nhật trạng thái
                self.update_scene_status(item)

                self.save_script(project_name, script, script_filename)
                return script

        raise KeyError(f"Cảnh '{scene_id}' không tồn tại")

    def get_pending_scenes(self, project_name: str, script_filename: str, asset_type: str) -> list[dict]:
        """
        Lấy danh sách Cảnh/Đoạn đang chờ xử lý

        Args:
            project_name: Dự ánTên
            script_filename: Kịch bảntên tập tin
            asset_type: Loại tài nguyên

        Returns:
            Danh sách Cảnh/Đoạn đang chờ xử lý
        """
        script = self.load_script(project_name, script_filename)

        # Chọn cấu trúc dữ liệu đúng dựa trên chế độ nội dung
        content_mode = script.get("content_mode", "narration")
        if content_mode == "narration" and "segments" in script:
            items = script["segments"]
        else:
            items = script.get("scenes", [])

        return [item for item in items if not item["generated_assets"].get(asset_type)]

    # ==================== Đường dẫn tệp Công cụ ====================

    def get_source_path(self, project_name: str, filename: str) -> Path:
        """Lấy đường dẫn tệp nguồn"""
        return self.get_project_path(project_name) / "source" / filename

    def get_character_path(self, project_name: str, filename: str) -> Path:
        """Lấy đường dẫn Ảnh thiết kế nhân vật"""
        return self.get_project_path(project_name) / "characters" / filename

    def get_storyboard_path(self, project_name: str, filename: str) -> Path:
        """Lấy đường dẫn Ảnh phân cảnh"""
        return self.get_project_path(project_name) / "storyboards" / filename

    def get_video_path(self, project_name: str, filename: str) -> Path:
        """Lấy đường dẫn Video"""
        return self.get_project_path(project_name) / "videos" / filename

    def get_output_path(self, project_name: str, filename: str) -> Path:
        """Lấy đường dẫn đầu ra"""
        return self.get_project_path(project_name) / "output" / filename

    def get_scenes_needing_storyboard(self, project_name: str, script_filename: str) -> list[dict]:
        """
        Lấy danh sách Cảnh/Đoạn cần Tạo ảnh phân cảnh (luật logic hai chế độ thống nhất)

        Args:
            project_name: Dự ánTên
            script_filename: Kịch bảntên tập tin

        Returns:
            Danh sách Cảnh/Đoạn cần Tạo ảnh phân cảnh
        """
        script = self.load_script(project_name, script_filename)

        content_mode = script.get("content_mode", "narration")
        if content_mode == "narration" and "segments" in script:
            items = script["segments"]
        else:
            items = script.get("scenes", [])

        return [item for item in items if not item.get("generated_assets", {}).get("storyboard_image")]

    # ==================== Dự ánQuản lý metadata cấp ======================

    def _get_project_file_path(self, project_name: str) -> Path:
        """Lấy đường dẫn tệp metadata Dự án"""
        return self.get_project_path(project_name) / self.PROJECT_FILE

    def project_exists(self, project_name: str) -> bool:
        """Kiểm tra xem tệp metadata Dự án có tồn tại không"""
        try:
            return self._get_project_file_path(project_name).exists()
        except FileNotFoundError:
            return False

    def load_project(self, project_name: str) -> dict:
        """
        Tải metadata Dự án

        Args:
            project_name: Dự ánTên

        Returns:
            Dự ánSiêu dữ liệu từ điển
        """
        project_file = self._get_project_file_path(project_name)

        if not project_file.exists():
            raise FileNotFoundError(f"Dự ánTệp dữ liệu metadata không tồn tại: {project_file}")

        with open(project_file, encoding="utf-8") as f:
            return json.load(f)

    def save_project(self, project_name: str, project: dict) -> Path:
        """
        LưuDự ánSiêu dữ liệu

        Args:
            project_name: Dự ánTên
            project: Dự ánSiêu dữ liệu từ điển

        Returns:
            LưuĐường dẫn tệp
        """
        project_file = self._get_project_file_path(project_name)

        self._touch_metadata(project)

        with open(project_file, "w", encoding="utf-8") as f:
            json.dump(project, f, ensure_ascii=False, indent=2)

        emit_project_change_hint(
            project_name,
            changed_paths=[self.PROJECT_FILE],
        )

        return project_file

    def update_project(
        self,
        project_name: str,
        mutate_fn: Callable[[dict], None],
    ) -> Path:
        """Cập nhật project.json một cách nguyên tử: khóa tệp → đọc → chỉnh sửa → ghi lại.

        Tránh xung đột lost-update giữa các tác vụ đồng thời (ví dụ như tạo nhiều nhân vật ảnh cùng lúc).

        Args:
            project_name: Dự ánTên
            mutate_fn: Hàm callback nhận dict dự án và chỉnh sửa tại chỗ
        """
        project_file = self._get_project_file_path(project_name)

        with open(project_file, "r+", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                project = json.load(f)
                mutate_fn(project)
                self._touch_metadata(project)

                f.seek(0)
                json.dump(project, f, ensure_ascii=False, indent=2)
                f.truncate()
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

        emit_project_change_hint(
            project_name,
            changed_paths=[self.PROJECT_FILE],
        )

        return project_file

    @staticmethod
    def _touch_metadata(project: dict) -> None:
        now = datetime.now().isoformat()
        if "metadata" not in project:
            project["metadata"] = {"created_at": now, "updated_at": now}
        else:
            project["metadata"]["updated_at"] = now

    def create_project_metadata(
        self,
        project_name: str,
        title: str | None = None,
        style: str | None = None,
        content_mode: str = "narration",
    ) -> dict:
        """
        TạoTệp metadata dự án mới

        Args:
            project_name: Dự ánNhận dạng
            title: Dự ánTiêu đề，Để trống sẽ mặc định sử dụng định danh dự án
            style: Mô tả phong cách hình ảnh tổng thể
            content_mode: chế độ nội dung ('narration' hoặc 'drama')

        Returns:
            Dự ánSiêu dữ liệu từ điển
        """
        project_name = self.normalize_project_name(project_name)
        project_title = str(title).strip() if title is not None else ""

        project = {
            "title": project_title or project_name,
            "content_mode": content_mode,
            "style": style or "",
            "episodes": [],
            "characters": {},
            "clues": {},
            "metadata": {
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            },
        }

        self.save_project(project_name, project)
        return project

    def add_episode(self, project_name: str, episode: int, title: str, script_file: str) -> dict:
        """
        Thêm tập phim vào dự án

        Args:
            project_name: Dự ánTên
            episode: Số tập
            title: Tập phimTiêu đề
            script_file: Kịch bảnĐường dẫn tệp tương đối

        Returns:
            Metadata dự án đã được cập nhật
        """
        project = self.load_project(project_name)

        # Kiểm tra xem đã tồn tại chưa
        for ep in project["episodes"]:
            if ep["episode"] == episode:
                ep["title"] = title
                ep["script_file"] = script_file
                self.save_project(project_name, project)
                return project

        # ThêmTập phim mới (không bao gồm các đoạn thống kê từ, được StatusCalculator tính toán khi đọc)
        project["episodes"].append({"episode": episode, "title": title, "script_file": script_file})

        # Sắp xếp theo số tập
        project["episodes"].sort(key=lambda x: x["episode"])

        self.save_project(project_name, project)
        return project

    def sync_project_status(self, project_name: str) -> dict:
        """
        [[Đã bỏ] Đồng bộ trạng thái dự án

        Phương pháp này đã bị bỏ. Các thống kê như status, progress, scenes_count, v.v.
        Hiện tại do StatusCalculator tính toán khi đọc, không còn lưu trong file JSON nữa.

        Giữ lại phương pháp này chỉ để tương thích ngược, thực tế không thực hiện bất kỳ thao tác ghi nào.

        Args:
            project_name: Dự ánTên

        Returns:
            Dự ánMetadata (không bao gồm các thống kê, các thống kê này được StatusCalculator chèn)
        """
        import warnings

        warnings.warn(
            "sync_project_status() Đã bị bỏ. Các thống kê như status hiện được StatusCalculator tính toán khi đọc.",
            DeprecationWarning,
            stacklevel=2,
        )
        # Chỉ trả về dữ liệu dự án, không thực hiện bất kỳ ghi nào
        return self.load_project(project_name)

    # ==================== Dự ánQuản lý nhân vật ======================

    def add_project_character(
        self,
        project_name: str,
        name: str,
        description: str,
        voice_style: str | None = None,
        character_sheet: str | None = None,
    ) -> dict:
        """
        Thêm nhân vật cho dự án (cấp dự án)

        Args:
            project_name: Dự ánTên
            name: Tên nhân vật
            description: Nhân vậtMô tả
            voice_style: Phong cách giọng nói
            character_sheet: Ảnh thiết kế nhân vậtĐường dẫn

        Returns:
            Metadata dự án đã được cập nhật
        """
        project = self.load_project(project_name)

        project["characters"][name] = {
            "description": description,
            "voice_style": voice_style or "",
            "character_sheet": character_sheet or "",
        }

        self.save_project(project_name, project)
        return project

    def update_project_character_sheet(self, project_name: str, name: str, sheet_path: str) -> dict:
        """Cập nhật đường dẫn Ảnh thiết kế nhân vật cấp dự án"""
        project = self.load_project(project_name)

        if name not in project["characters"]:
            raise KeyError(f"Nhân vật '{name}' không tồn tại")

        project["characters"][name]["character_sheet"] = sheet_path
        self.save_project(project_name, project)
        return project

    def update_character_reference_image(self, project_name: str, char_name: str, ref_path: str) -> dict:
        """
        Cập nhật đường dẫn Ảnh tham chiếu của Nhân vật

        Args:
            project_name: Dự ánTên
            char_name: Tên nhân vật
            ref_path: Ảnh tham chiếuĐường dẫn tương đối

        Returns:
            Dữ liệu dự án đã cập nhật
        """
        project = self.load_project(project_name)

        if "characters" not in project or char_name not in project["characters"]:
            raise KeyError(f"Nhân vật '{char_name}' không tồn tại")

        project["characters"][char_name]["reference_image"] = ref_path
        self.save_project(project_name, project)
        return project

    def get_project_character(self, project_name: str, name: str) -> dict:
        """Lấy định nghĩa nhân vật cấp dự án"""
        project = self.load_project(project_name)

        if name not in project["characters"]:
            raise KeyError(f"Nhân vật '{name}' không tồn tại")

        return project["characters"][name]

    # ==================== Manh mốiQuản lý ======================

    def update_clue_sheet(self, project_name: str, name: str, sheet_path: str) -> dict:
        """
        Cập nhật đường dẫn Ảnh thiết kế manh mối

        Args:
            project_name: Dự ánTên
            name: Tên manh mối
            sheet_path: Đường dẫn bản thiết kế

        Returns:
            Metadata dự án đã được cập nhật
        """
        project = self.load_project(project_name)

        if name not in project["clues"]:
            raise KeyError(f"Manh mối '{name}' không tồn tại")

        project["clues"][name]["clue_sheet"] = sheet_path
        self.save_project(project_name, project)
        return project

    def get_clue(self, project_name: str, name: str) -> dict:
        """
        Lấy định nghĩa manh mối

        Args:
            project_name: Dự ánTên
            name: Tên manh mối

        Returns:
            Manh mốiĐịnh nghĩa từ điển
        """
        project = self.load_project(project_name)

        if name not in project["clues"]:
            raise KeyError(f"Manh mối '{name}' không tồn tại")

        return project["clues"][name]

    def get_pending_characters(self, project_name: str) -> list[dict]:
        """
        Lấy danh sách nhân vật cần tạo ảnh thiết kế

        Args:
            project_name: Dự ánTên

        Returns:
            Danh sách nhân vật cần xử lý (không có character_sheet hoặc tệp tin không tồn tại)
        """
        project = self.load_project(project_name)
        project_dir = self.get_project_path(project_name)

        pending = []
        for name, char in project.get("characters", {}).items():
            sheet = char.get("character_sheet")
            if not sheet or not (project_dir / sheet).exists():
                pending.append({"name": name, **char})

        return pending

    def get_pending_clues(self, project_name: str) -> list[dict]:
        """
        Lấy danh sách manh mối cần tạo ảnh thiết kế

        Args:
            project_name: Dự ánTên

        Returns:
            Danh sách manh mối cần xử lý (importance='major' và không có clue_sheet)
        """
        project = self.load_project(project_name)
        project_dir = self.get_project_path(project_name)

        pending = []
        for name, clue in project["clues"].items():
            if clue.get("importance") == "major":
                sheet = clue.get("clue_sheet")
                if not sheet or not (project_dir / sheet).exists():
                    pending.append({"name": name, **clue})

        return pending

    def get_clue_path(self, project_name: str, filename: str) -> Path:
        """Lấy đường dẫn ảnh thiết kế manh mối"""
        return self.get_project_path(project_name) / "clues" / filename

    # ==================== Nhân vật/Manh mốiGhi trực tiếp vào Công cụ ====================

    def add_character(self, project_name: str, name: str, description: str, voice_style: str = "") -> bool:
        """
        Thêm trực tiếp nhân vật vào project.json

        Nếu nhân vật đã tồn tại, bỏ qua không ghi đè.

        Args:
            project_name: Dự ánTên
            name: Tên nhân vật
            description: Nhân vậtMô tả
            voice_style: Phong cách giọng nói(Tùy chọn)

        Returns:
            True Nếu thêm thành công, False nếu đã tồn tại
        """
        project = self.load_project(project_name)

        if name in project.get("characters", {}):
            logger.debug("Nhân vật '%s' Đã tồn tạiTrong project.json, bỏ qua", name)
            return False

        if "characters" not in project:
            project["characters"] = {}

        project["characters"][name] = {
            "description": description,
            "character_sheet": "",
            "voice_style": voice_style,
        }

        self.save_project(project_name, project)
        logger.info("Thêm nhân vật: %s", name)
        return True

    def add_clue(
        self,
        project_name: str,
        name: str,
        clue_type: str,
        description: str,
        importance: str = "minor",
    ) -> bool:
        """
        Thêm trực tiếp manh mối vào project.json

        Nếu manh mối đã tồn tại, bỏ qua không ghi đè.

        Args:
            project_name: Dự ánTên
            name: Tên manh mối
            clue_type: Manh mốiLoại（prop Hoặc location)
            description: Manh mốiMô tả
            importance: Độ quan trọng（major hoặc minor, mặc định minor）

        Returns:
            True Nếu thêm thành công, False nếu đã tồn tại
        """
        project = self.load_project(project_name)

        if name in project.get("clues", {}):
            logger.debug("Manh mối '%s' Đã tồn tạiTrong project.json, bỏ qua", name)
            return False

        if "clues" not in project:
            project["clues"] = {}

        project["clues"][name] = {
            "type": clue_type,
            "description": description,
            "importance": importance,
            "clue_sheet": "",
        }

        self.save_project(project_name, project)
        logger.info("Thêm manh mối: %s", name)
        return True

    def add_characters_batch(self, project_name: str, characters: dict[str, dict]) -> int:
        """
        Thêm nhân vật hàng loạt vào project.json

        Args:
            project_name: Dự ánTên
            characters: Nhân vậttừĐiển {name: {description, voice_style}}

        Returns:
            Số lượng nhân vật mới
        """
        project = self.load_project(project_name)

        if "characters" not in project:
            project["characters"] = {}

        added = 0
        for name, data in characters.items():
            if name not in project["characters"]:
                project["characters"][name] = {
                    "description": data.get("description", ""),
                    "character_sheet": data.get("character_sheet", ""),
                    "voice_style": data.get("voice_style", ""),
                }
                added += 1
                logger.info("Thêm nhân vật: %s", name)
            else:
                logger.debug("Nhân vật '%s' Đã tồn tại, bỏ qua", name)

        if added > 0:
            self.save_project(project_name, project)

        return added

    def add_clues_batch(self, project_name: str, clues: dict[str, dict]) -> int:
        """
        Thêm manh mối hàng loạt vào project.json

        Args:
            project_name: Dự ánTên
            clues: Manh mốitừĐiển {name: {type, description, importance}}

        Returns:
            Số lượng manh mối mới
        """
        project = self.load_project(project_name)

        if "clues" not in project:
            project["clues"] = {}

        added = 0
        for name, data in clues.items():
            if name not in project["clues"]:
                project["clues"][name] = {
                    "type": data.get("type", "prop"),
                    "description": data.get("description", ""),
                    "importance": data.get("importance", "minor"),
                    "clue_sheet": data.get("clue_sheet", ""),
                }
                added += 1
                logger.info("Thêm manh mối: %s", name)
            else:
                logger.debug("Manh mối '%s' Đã tồn tại, bỏ qua", name)

        if added > 0:
            self.save_project(project_name, project)

        return added

    # ==================== Ảnh tham chiếuThu thập Công cụ ====================

    def collect_reference_images(self, project_name: str, scene: dict) -> list[Path]:
        """
        Thu thập tất cả Ảnh tham chiếu cần thiết cho Cảnh

        Args:
            project_name: Dự ánTên
            scene: CảnhtừĐiển

        Returns:
            Ảnh tham chiếuDanh sách đường dẫn
        """
        project = self.load_project(project_name)
        project_dir = self.get_project_path(project_name)
        refs = []

        # Nhân vậtẢnh tham chiếu
        for char in scene.get("characters_in_scene", []):
            char_data = project["characters"].get(char, {})
            sheet = char_data.get("character_sheet")
            if sheet:
                sheet_path = project_dir / sheet
                if sheet_path.exists():
                    refs.append(sheet_path)

        # Manh mốiẢnh tham chiếu
        for clue in scene.get("clues_in_scene", []):
            clue_data = project["clues"].get(clue, {})
            sheet = clue_data.get("clue_sheet")
            if sheet:
                sheet_path = project_dir / sheet
                if sheet_path.exists():
                    refs.append(sheet_path)

        return refs

    # ==================== Mô tả dự ánTạo ====================

    def _read_source_files(self, project_name: str, max_chars: int = 50000) -> str:
        """
        đọcDự án source Nội dung tất cả các tệp Văn bản trong thư mục

        Args:
            project_name: Dự ánTên
            max_chars: Số ký tự đọc tối đa (tránh vượt quá giới hạn API)

        Returns:
            Nội dung Văn bản sau khi hợp nhất
        """
        project_dir = self.get_project_path(project_name)
        source_dir = project_dir / "source"

        if not source_dir.exists():
            return ""

        contents = []
        total_chars = 0

        # Sắp xếp theo tên tệp để đảm bảo thứ tự nhất quán
        for file_path in sorted(source_dir.glob("*")):
            if file_path.is_file() and file_path.suffix.lower() in [".txt", ".md"]:
                try:
                    with open(file_path, encoding="utf-8") as f:
                        content = f.read()
                        remaining = max_chars - total_chars
                        if remaining <= 0:
                            break
                        if len(content) > remaining:
                            content = content[:remaining]
                        contents.append(f"--- {file_path.name} ---\n{content}")
                        total_chars += len(content)
                except Exception as e:
                    logger.error("đọcTệp Thất bại %s: %s", file_path.name, e)

        return "\n\n".join(contents)

    async def generate_overview(self, project_name: str) -> dict:
        """
        Sử dụng API Gemini để tạo Mô tả dự án bất đồng bộ

        Args:
            project_name: Dự ánTên

        Returns:
            Tổng quan tạo ra từ mẫu, bao gồm tóm tắt, thể loại, chủ đề, bối cảnh thế giới, thời gian tạo
        """
        from .text_backends.base import TextGenerationRequest, TextTaskType
        from .text_generator import TextGenerator

        # đọcTệp nguồnNội dung
        source_content = self._read_source_files(project_name)
        if not source_content:
            raise ValueError("source Mục lục trống, không thể tạo tổng quan")

        # Tạo TextGenerator（Tự động theo dõi mức sử dụng
        generator = await TextGenerator.create(TextTaskType.OVERVIEW, project_name)

        # Gọi TextGenerator (Kết quả có cấu trúc)
        prompt = f"Vui lòng phân tích nội dung tiểu thuyết dưới đây, trích xuất thông tin quan trọng:{source_content}"

        result = await generator.generate(
            TextGenerationRequest(
                prompt=prompt,
                response_schema=ProjectOverview,
            ),
            project_name=project_name,
        )
        response_text = result.text

        # Phân tích và xác thực phản hồi
        overview = ProjectOverview.model_validate_json(response_text)
        overview_dict = overview.model_dump()
        overview_dict["generated_at"] = datetime.now().isoformat()

        # LưuĐến project.json
        project = self.load_project(project_name)
        project["overview"] = overview_dict
        self.save_project(project_name, project)

        logger.info("Mô tả dự ánĐã tạo và Lưu")
        return overview_dict
