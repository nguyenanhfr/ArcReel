"""Dịch vụ xuất bản nháp từ Jianying

Đưa Video đã tạo của ArcReel từng tập làm bản nháp Jianying ZIP.
Sử dụng thư viện pyJianYingDraft để tạo draft_content.json,
Đường dẫn xử lý hậu kỳ thay thế để bản nháp trỏ tới thư mục cục bộ của người dùng trên Jianying.
"""

import json
import logging
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import pyJianYingDraft as draft
from pyJianYingDraft import (
    ClipSettings,
    TextBorder,
    TextSegment,
    TextShadow,
    TextStyle,
    TrackType,
    VideoMaterial,
    VideoSegment,
    trange,
)

from lib.project_manager import ProjectManager

logger = logging.getLogger(__name__)


class JianyingDraftService:
    """Dịch vụ xuất bản nháp từ Jianying"""

    def __init__(self, project_manager: ProjectManager):
        self.pm = project_manager

    # ------------------------------------------------------------------
    # Phương pháp nội bộ: Trích xuất dữ liệu
    # ------------------------------------------------------------------

    def _find_episode_script(self, project_name: str, project: dict, episode: int) -> tuple[dict, str]:
        """Định vị tệp Kịch bản của tập chỉ định, trả về (script_dict, filename)"""
        episodes = project.get("episodes", [])
        ep_entry = next((e for e in episodes if e.get("episode") == episode), None)
        if ep_entry is None:
            raise FileNotFoundError(f"Không. {episode} Tập không tồn tại")

        script_file = ep_entry.get("script_file", "")
        filename = Path(script_file).name
        script_data = self.pm.load_script(project_name, filename)
        return script_data, filename

    def _collect_video_clips(self, script: dict, project_dir: Path) -> list[dict[str, Any]]:
        """Trích xuất danh sách ĐoạnVideo đã hoàn thành từ Kịch bản"""
        content_mode = script.get("content_mode", "narration")
        items = script.get("segments" if content_mode == "narration" else "scenes", [])
        id_field = "segment_id" if content_mode == "narration" else "scene_id"

        clips = []
        for item in items:
            assets = item.get("generated_assets") or {}
            video_clip = assets.get("video_clip")
            if not video_clip:
                continue

            abs_path = (project_dir / video_clip).resolve()
            if not abs_path.is_relative_to(project_dir.resolve()):
                logger.warning("video_clip Vượt quá giới hạn đường dẫn, đã bỏ qua: %s", video_clip)
                continue
            if not abs_path.exists():
                continue

            clips.append(
                {
                    "id": item.get(id_field, ""),
                    "duration_seconds": item.get("duration_seconds", 8),
                    "video_clip": video_clip,
                    "abs_path": abs_path,
                    "novel_text": item.get("novel_text", ""),
                }
            )

        return clips

    def _resolve_canvas_size(self, project: dict, first_video_path: Path | None = None) -> tuple[int, int]:
        """Xác định kích thước khung theo tỷ lệ khung hình Dự án, nếu thiếu thì tự động phát hiện từ Video đầu tiên"""
        aspect = project.get("aspect_ratio", {}).get("video")
        if aspect is None and first_video_path is not None:
            mat = VideoMaterial(str(first_video_path))
            aspect = "9:16" if mat.height > mat.width else "16:9"
        if aspect == "9:16":
            return 1080, 1920
        return 1920, 1080

    # ------------------------------------------------------------------
    # Phương thức nội bộ: tạo bản nháp
    # ------------------------------------------------------------------

    def _generate_draft(
        self,
        *,
        draft_dir: Path,
        draft_name: str,
        clips: list[dict],
        width: int,
        height: int,
        content_mode: str,
    ) -> None:
        """Sử dụng pyJianYingDraft để tạo tệp nháp trong draft_dir"""
        draft_dir.parent.mkdir(parents=True, exist_ok=True)
        folder = draft.DraftFolder(str(draft_dir.parent))
        script_file = folder.create_draft(draft_name, width=width, height=height, allow_replace=True)

        # VideoĐường ray
        script_file.add_track(TrackType.video)

        # từĐường ray cảnh (chỉ chế độ narration)
        has_subtitle = content_mode == "narration"
        text_style: TextStyle | None = None
        text_border: TextBorder | None = None
        text_shadow: TextShadow | None = None
        subtitle_position: ClipSettings | None = None
        is_portrait = height > width
        if has_subtitle:
            script_file.add_track(TrackType.text, "từCảnh")
            text_style = TextStyle(
                size=12.0 if is_portrait else 8.0,
                color=(1.0, 1.0, 1.0),
                align=1,
                bold=True,
                auto_wrapping=True,
                max_line_width=0.82 if is_portrait else 0.6,
            )
            text_border = TextBorder(
                color=(0.0, 0.0, 0.0),
                width=30.0,
            )
            text_shadow = TextShadow(
                color=(0.0, 0.0, 0.0),
                alpha=0.7,
                diffuse=8.0,
                distance=3.0,
                angle=-45.0,
            )
            subtitle_position = ClipSettings(
                transform_y=-0.75 if is_portrait else -0.8,
            )

        # Thêm theo đoạn
        offset_us = 0
        for clip in clips:
            # Đọc trước thời lượng Video thực tế
            material = VideoMaterial(clip["local_path"])
            actual_duration_us = material.duration

            # VideoĐoạn
            video_seg = VideoSegment(
                material,
                trange(offset_us, actual_duration_us),
            )
            script_file.add_segment(video_seg)

            # từCảnh đoạn
            if has_subtitle and clip.get("novel_text"):
                text_seg = TextSegment(
                    text=clip["novel_text"],
                    timerange=trange(offset_us, actual_duration_us),
                    style=text_style,
                    border=text_border,
                    shadow=text_shadow,
                    clip_settings=subtitle_position,
                )
                script_file.add_segment(text_seg)

            offset_us += actual_duration_us

        script_file.save()

    def _replace_paths_in_draft(self, *, json_path: Path, tmp_prefix: str, target_prefix: str) -> None:
        """JSON Thay thế an toàn đường dẫn tạm trong draft_content.json"""
        real = os.path.realpath(json_path)
        tmp = os.path.realpath(tempfile.gettempdir()) + os.sep
        if not real.startswith(tmp):
            raise ValueError(f"Vượt quá giới hạn đường dẫn, từ chối ghi: {real}")

        with open(real, encoding="utf-8") as f:  # noqa: PTH123
            data = json.load(f)

        def _walk(obj: Any) -> Any:
            if isinstance(obj, str) and tmp_prefix in obj:
                return obj.replace(tmp_prefix, target_prefix)
            if isinstance(obj, dict):
                return {k: _walk(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_walk(v) for v in obj]
            return obj

        data = _walk(data)
        with open(real, "w", encoding="utf-8") as f:  # noqa: PTH123
            json.dump(data, f, ensure_ascii=False)

    # ------------------------------------------------------------------
    # Phương pháp công khai
    # ------------------------------------------------------------------

    def export_episode_draft(
        self,
        project_name: str,
        episode: int,
        draft_path: str,
        *,
        use_draft_info_name: bool = True,
    ) -> Path:
        """
        Xuất bản nháp Clip Studio của tập được chỉ định dưới dạng ZIP.

        Returns:
            ZIP Đường dẫn tệp (tệp tạm thời, bên gọi chịu trách nhiệm dọn dẹp)

        Raises:
            FileNotFoundError: Dự ánHoặc kịch bản không tồn tại
            ValueError: Không có Video Đoạn nào có thể xuất
        """
        project = self.pm.load_project(project_name)
        project_dir = self.pm.get_project_path(project_name)

        # 1. Định vị kịch bản
        script_data, _ = self._find_episode_script(project_name, project, episode)

        # 2. Thu thập các Video đã hoàn thành của tập
        content_mode = script_data.get("content_mode", "narration")
        clips = self._collect_video_clips(script_data, project_dir)
        if not clips:
            raise ValueError(f"Không. {episode} Tập không có Video Đoạn nào đã hoàn thành, vui lòng tạo video trước")

        # 3. Kích thước khung vẽ (nếu dự án chưa đặt tỉ lệ khung hình, tự động phát hiện từ video đầu tiên)
        width, height = self._resolve_canvas_size(project, clips[0]["abs_path"])

        # 4. TạoThư mục tạm thời + sao chép nguyên liệu vào khu vực tạm
        raw_title = project.get("title", project_name)
        safe_title = raw_title.replace("/", "_").replace("\\", "_").replace("..", "_")
        draft_name = f"{safe_title}_Tập.{episode}"
        tmp_dir = Path(tempfile.mkdtemp(prefix="arcreel_jy_"))
        try:
            staging_dir = tmp_dir / "staging"
            staging_dir.mkdir()

            local_clips = []
            for clip in clips:
                src = clip["abs_path"]
                dst = staging_dir / src.name
                try:
                    dst.hardlink_to(src)
                except OSError:
                    shutil.copy2(src, dst)
                local_clips.append({**clip, "local_path": str(dst)})

            # 5. Tạo bản nháp (create_draft sẽ xây dựng lại thư mục draft_dir)
            draft_dir = tmp_dir / draft_name
            self._generate_draft(
                draft_dir=draft_dir,
                draft_name=draft_name,
                clips=local_clips,
                width=width,
                height=height,
                content_mode=content_mode,
            )

            # 6. Di chuyển nguyên liệu vào thư mục nháp
            assets_dir = draft_dir / "assets"
            assets_dir.mkdir(exist_ok=True)
            for clip in local_clips:
                src = Path(clip["local_path"])
                dst = assets_dir / src.name
                shutil.move(str(src), str(dst))

            # 7. Xử lý đường dẫn hậu kỳ: đường dẫn staging → đường dẫn cục bộ người dùng
            draft_content_path = draft_dir / "draft_content.json"
            self._replace_paths_in_draft(
                json_path=draft_content_path,
                tmp_prefix=str(staging_dir),
                target_prefix=f"{draft_path}/{draft_name}/assets",
            )

            # 8. Clip Studio 6+ sử dụng draft_info.json, các phiên bản thấp hơn sử dụng draft_content.json
            if use_draft_info_name:
                draft_content_path.rename(draft_dir / "draft_info.json")

            # 9. Đóng gói ZIP
            zip_path = tmp_dir / f"{draft_name}.zip"
            video_suffixes = {".mp4", ".webm", ".mov", ".avi", ".mkv"}
            with zipfile.ZipFile(zip_path, "w") as zf:
                for file in draft_dir.rglob("*"):
                    if file.is_file():
                        arcname = f"{draft_name}/{file.relative_to(draft_dir)}"
                        compress = zipfile.ZIP_STORED if file.suffix.lower() in video_suffixes else zipfile.ZIP_DEFLATED
                        zf.write(file, arcname, compress_type=compress)

            return zip_path
        except Exception:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise
