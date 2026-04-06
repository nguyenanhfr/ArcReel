#!/usr/bin/env python3
"""
Kịch bản di chuyển dữ liệu: Di chuyển characters từ dự án hiện tại sang project.json

Cách sử dụng:
    python scripts/migrate_to_project_json.py <Dự án名>
    python scripts/migrate_to_project_json.py --all  # Di chuyển tất cả Dự án
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Thêm lib Mục lục đến đường dẫn Python
lib_path = Path(__file__).parent.parent / "lib"
sys.path.insert(0, str(lib_path))

from project_manager import ProjectManager


def migrate_project(pm: ProjectManager, project_name: str, dry_run: bool = False) -> bool:
    """
    Di chuyển một Dự án

    Args:
        pm: ProjectManager Ví dụ
        project_name: Dự ánTên
        dry_run: Chỉ xem trước không thực hiện

    Returns:
        Có thành công không
    """
    print(f"\n{'=' * 50}")
    print(f"Di chuyển Dự án: {project_name}")
    print("=" * 50)

    try:
        project_dir = pm.get_project_path(project_name)
    except FileNotFoundError:
        print(f"  ❌ Dự ánKhông tồn tại: {project_name}")
        return False

    # Kiểm tra xem đã có project.json chưa
    project_file = project_dir / "project.json"
    if project_file.exists():
        print("  ⚠️  project.json Đã tồn tại，Bỏ qua di chuyển")
        print(f"  Nếu cần di chuyển lại, hãy Xóa trước {project_file}")
        return True

    # Thu thập tất cả Nhân vật trong Kịch bản
    scripts_dir = project_dir / "scripts"
    all_characters = {}
    episodes = []
    script_files = list(scripts_dir.glob("*.json")) if scripts_dir.exists() else []

    if not script_files:
        print("  ⚠️  Không tìm thấy tệp Kịch bản")

    for script_file in sorted(script_files):
        print(f"\n  📖 Xử lý Kịch bản: {script_file.name}")

        with open(script_file, encoding="utf-8") as f:
            script = json.load(f)

        # 提取Nhân vật
        characters = script.get("characters", {})
        for name, char_data in characters.items():
            if name not in all_characters:
                all_characters[name] = char_data.copy()
                print(f"      👤 Phát hiện Nhân vật: {name}")
            else:
                # Hợp nhất dữ liệu (ưu tiên giữ phiên bản có bản thiết kế)
                if char_data.get("character_sheet") and not all_characters[name].get("character_sheet"):
                    all_characters[name] = char_data.copy()
                    print(f"      👤 Cập nhật nhân vật: {name} (Có bản thiết kế)")

        # Trích xuất thông tin Tập phim
        novel_info = script.get("novel", {})
        scenes_count = len(script.get("scenes", []))

        # Thử suy luận số tập từ tên tệp hoặc nội dung
        episode_num = 1
        filename_lower = script_file.stem.lower()
        for i in range(1, 100):
            if f"episode_{i:02d}" in filename_lower or f"episode{i}" in filename_lower:
                episode_num = i
                break
            if f"chapter_{i:02d}" in filename_lower or f"chapter{i}" in filename_lower:
                episode_num = i
                break
            if f"_{i:02d}_" in filename_lower or f"_{i}_" in filename_lower:
                episode_num = i
                break

        # ThêmTập phimThông tin (không bao gồm thống kê từ đoạn, do StatusCalculator tính khi đọc)
        episodes.append(
            {
                "episode": episode_num,
                "title": novel_info.get("chapter", script_file.stem),
                "script_file": f"scripts/{script_file.name}",
            }
        )
        print(f"      📺 Tập phim {episode_num}: {scenes_count} cảnh")

    # Loại bỏ trùng lặp và sắp xếp Tập phim
    seen_episodes = {}
    for ep in episodes:
        if ep["episode"] not in seen_episodes:
            seen_episodes[ep["episode"]] = ep
    episodes = sorted(seen_episodes.values(), key=lambda x: x["episode"])

    # Xây dựng project.json
    project_title = project_name
    if script_files:
        with open(script_files[0], encoding="utf-8") as f:
            first_script = json.load(f)
            project_title = first_script.get("novel", {}).get("title", project_name)

    # Xây dựng project.json (không bao gồm trường status, sẽ được StatusCalculator tính toán khi đọc)
    project_data = {
        "title": project_title,
        "style": "",
        "episodes": episodes,
        "characters": all_characters,
        "clues": {},
        "metadata": {
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "migrated_from": "script_based_characters",
        },
    }

    # Thống kê số Ảnh thiết kế nhân vật đã hoàn thành (chỉ dùng cho log Đầu ra)
    completed_chars = 0
    for name, char_data in all_characters.items():
        sheet = char_data.get("character_sheet")
        if sheet:
            sheet_path = project_dir / sheet
            if sheet_path.exists():
                completed_chars += 1

    # Tạo clues 目录
    clues_dir = project_dir / "clues"
    if not clues_dir.exists():
        if not dry_run:
            clues_dir.mkdir(parents=True, exist_ok=True)
        print("\n  📁 TạoThư mục: clues/")

    print("\n  📊 Tóm tắt di chuyển:")
    print(f"      - Nhân vật: {len(all_characters)} cái ({completed_chars} cái có thiết kế)")
    print(f"      - Tập phim: {len(episodes)} 个")
    print("      - Manh mối: 0 cái (chờ Thêm)")

    if dry_run:
        print("\n  🔍 Chế độ xem trước - sẽ không Thực tế ghi vào tệp")
        print("\n  Bắt đầu Tạo project.json:")
        print(json.dumps(project_data, ensure_ascii=False, indent=2)[:500] + "...")
    else:
        # Ghi vào project.json
        with open(project_file, "w", encoding="utf-8") as f:
            json.dump(project_data, f, ensure_ascii=False, indent=2)
        print("\n  ✅ Đã tạo project.json")

        # Tùy chọn: Xóa các ký tự từ đoạn trong Kịch bản (giữ bản sao lưu của Văn bản gốc)
        # Ở đây chúng tôi giữ các ký tự trong Kịch bản để duy trì tương thích ngược
        print("  ℹ️  Giữ các ký tự từ đoạn trong Kịch bản để duy trì tương thích ngược")

    return True


def main():
    parser = argparse.ArgumentParser(description="Di chuyển dữ liệu dự án sang project.json")
    parser.add_argument("project", nargs="?", help="Dự ánTên，Hoặc sử dụng --all để di chuyển tất cả Dự án")
    parser.add_argument("--all", action="store_true", help="Di chuyển tất cả Dự án")
    parser.add_argument("--dry-run", action="store_true", help="Chế độ xem trước, không thực sự thực hiện")
    parser.add_argument("--projects-root", default=None, help="Dự án根目录")

    args = parser.parse_args()

    if not args.project and not args.all:
        parser.print_help()
        print("\n❌ Vui lòng chỉ định Tên Dự án hoặc sử dụng --all")
        sys.exit(1)

    # Khởi tạo ProjectManager
    pm = ProjectManager(projects_root=args.projects_root)

    print("🚀 Bắt đầu di chuyển...")
    print(f"   Dự ánThư mục gốc: {pm.projects_root}")

    if args.dry_run:
        print("   📋 Chế độ xem trước đã được bật")

    success_count = 0
    fail_count = 0

    if args.all:
        projects = pm.list_projects()
        print(f"   发现 {len(projects)} 个Dự án")

        for project_name in projects:
            if migrate_project(pm, project_name, dry_run=args.dry_run):
                success_count += 1
            else:
                fail_count += 1
    else:
        if migrate_project(pm, args.project, dry_run=args.dry_run):
            success_count = 1
        else:
            fail_count = 1

    print("\n" + "=" * 50)
    print("Di chuyển Hoàn thành!")
    print(f"   ✅ Thành công: {success_count}")
    print(f"   ❌ Thất bại: {fail_count}")
    print("=" * 50)

    sys.exit(0 if fail_count == 0 else 1)


if __name__ == "__main__":
    main()
