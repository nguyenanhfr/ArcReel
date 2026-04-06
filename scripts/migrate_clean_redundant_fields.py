"""
Dọn dẹp các đoạn từ dư thừa trong Dự án hiện có

Script này dùng để di chuyển dữ liệu hiện có, Xóa các đoạn từ dư thừa đã chuyển sang tính toán khi đọc.
Trước khi chạy, vui lòng đảm bảo đã sao lưu dữ liệu.

用法:
    python scripts/migrate_clean_redundant_fields.py
    python scripts/migrate_clean_redundant_fields.py --dry-run  # Chỉ xem trước, không sửa đổi
"""

import argparse
import json
from pathlib import Path


def migrate_project(project_dir: Path, dry_run: bool = False) -> dict:
    """
    Dọn dẹp các đoạn từ dư thừa của một Dự án riêng lẻ

    Args:
        project_dir: Dự án目录路径
        dry_run: Có chỉ xem trước, không sửa đổi

    Returns:
        Di chuyển số liệu thống kê
    """
    stats = {"project_cleaned": False, "scripts_cleaned": 0, "fields_removed": []}

    # Dọn dẹp project.json
    project_file = project_dir / "project.json"
    if project_file.exists():
        with open(project_file, encoding="utf-8") as f:
            project = json.load(f)

        original = json.dumps(project)

        # Xóa status Đối tượng (chuyển sang tính toán khi đọc)
        if "status" in project:
            stats["fields_removed"].append("project.json: status")
            if not dry_run:
                project.pop("status", None)

        # Xóa episodes Các đoạn từ trong
        for ep in project.get("episodes", []):
            if "scenes_count" in ep:
                stats["fields_removed"].append(f"project.json: episodes[{ep.get('episode')}].scenes_count")
                if not dry_run:
                    ep.pop("scenes_count", None)
            if "status" in ep:
                stats["fields_removed"].append(f"project.json: episodes[{ep.get('episode')}].status")
                if not dry_run:
                    ep.pop("status", None)

        if json.dumps(project) != original:
            stats["project_cleaned"] = True
            if not dry_run:
                with open(project_file, "w", encoding="utf-8") as f:
                    json.dump(project, f, ensure_ascii=False, indent=2)

    # Dọn dẹp scripts/*.json
    scripts_dir = project_dir / "scripts"
    if scripts_dir.exists():
        for script_file in scripts_dir.glob("*.json"):
            with open(script_file, encoding="utf-8") as f:
                script = json.load(f)

            original = json.dumps(script)
            script_name = script_file.name

            # XóaĐoạn từ dư thừa
            if "characters_in_episode" in script:
                stats["fields_removed"].append(f"{script_name}: characters_in_episode")
                if not dry_run:
                    script.pop("characters_in_episode", None)

            if "clues_in_episode" in script:
                stats["fields_removed"].append(f"{script_name}: clues_in_episode")
                if not dry_run:
                    script.pop("clues_in_episode", None)

            if "duration_seconds" in script:
                stats["fields_removed"].append(f"{script_name}: duration_seconds")
                if not dry_run:
                    script.pop("duration_seconds", None)

            if "metadata" in script:
                if "total_scenes" in script["metadata"]:
                    stats["fields_removed"].append(f"{script_name}: metadata.total_scenes")
                    if not dry_run:
                        script["metadata"].pop("total_scenes", None)
                if "estimated_duration_seconds" in script["metadata"]:
                    stats["fields_removed"].append(f"{script_name}: metadata.estimated_duration_seconds")
                    if not dry_run:
                        script["metadata"].pop("estimated_duration_seconds", None)

            if json.dumps(script) != original:
                stats["scripts_cleaned"] += 1
                if not dry_run:
                    with open(script_file, "w", encoding="utf-8") as f:
                        json.dump(script, f, ensure_ascii=False, indent=2)

    return stats


def main():
    parser = argparse.ArgumentParser(description="Dọn dẹp các đoạn từ dư thừa trong Dự án")
    parser.add_argument("--dry-run", action="store_true", help="Chỉ xem trước, không sửa đổi")
    parser.add_argument("--projects-root", default="projects", help="Dự án根目录")
    args = parser.parse_args()

    projects_root = Path(args.projects_root)

    if not projects_root.exists():
        print(f"❌ Dự ánThư mục gốc không tồn tại: {projects_root}")
        return

    if args.dry_run:
        print("🔍 Chế độ xem trước - sẽ không chỉnh sửa bất kỳ tệp nào")

    total_stats = {"projects_processed": 0, "projects_cleaned": 0, "scripts_cleaned": 0, "fields_removed": []}

    for project_dir in projects_root.iterdir():
        if project_dir.is_dir() and not project_dir.name.startswith("."):
            print(f"Xử lý Dự án: {project_dir.name}")
            stats = migrate_project(project_dir, args.dry_run)

            total_stats["projects_processed"] += 1
            if stats["project_cleaned"] or stats["scripts_cleaned"] > 0:
                total_stats["projects_cleaned"] += 1
            total_stats["scripts_cleaned"] += stats["scripts_cleaned"]
            total_stats["fields_removed"].extend(stats["fields_removed"])

            if stats["fields_removed"]:
                for field in stats["fields_removed"]:
                    print(f"  - Xóa: {field}")
            else:
                print("  - Không cần dọn dẹp")

    print(f"\n{'预览' if args.dry_run else '迁移'}Hoàn thành:")
    print(f"  - Xử lý Dự án: {total_stats['projects_processed']}")
    print(f"  - Dọn dẹp Dự án: {total_stats['projects_cleaned']}")
    print(f"  - Dọn dẹp Kịch bản: {total_stats['scripts_cleaned']}")
    print(f"  - Xóatừ段: {len(total_stats['fields_removed'])}")

    if args.dry_run and total_stats["fields_removed"]:
        print("\nĐể thực hiện một Thực tế di cư, hãy Xóa tham số --dry-run và chạy lại")


if __name__ == "__main__":
    main()
