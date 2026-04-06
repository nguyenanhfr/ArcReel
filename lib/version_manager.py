"""
Quản lý phiên bản模块

Quản lý lịch sử phiên bản của Ảnh phân cảnh, Video, Nhân vật đồ họa, Bản đồ manh mối.
Hỗ trợ sao lưu phiên bản, chuyển đổi phiên bản hiện tại, ghi lại và truy vấn.
"""

import json
import shutil
import threading
from datetime import UTC, datetime
from pathlib import Path

_LOCKS_GUARD = threading.Lock()
_LOCKS_BY_VERSIONS_FILE: dict[str, threading.RLock] = {}


def _get_versions_file_lock(versions_file: Path) -> threading.RLock:
    key = str(Path(versions_file).resolve())
    with _LOCKS_GUARD:
        lock = _LOCKS_BY_VERSIONS_FILE.get(key)
        if lock is None:
            lock = threading.RLock()
            _LOCKS_BY_VERSIONS_FILE[key] = lock
        return lock


class VersionManager:
    """Quản lý phiên bản器"""

    # 支持的Loại tài nguyên
    RESOURCE_TYPES = ("storyboards", "videos", "characters", "clues")

    # Loại tài nguyênPhần mở rộng tệp tương ứng
    EXTENSIONS = {
        "storyboards": ".png",
        "videos": ".mp4",
        "characters": ".png",
        "clues": ".png",
    }

    def __init__(self, project_path: Path):
        """
        Khởi tạo Trình quản lý phiên bản

        Args:
            project_path: Dự ánĐường dẫn thư mục gốc
        """
        self.project_path = Path(project_path)
        self.versions_dir = self.project_path / "versions"
        self.versions_file = self.versions_dir / "versions.json"
        self._lock = _get_versions_file_lock(self.versions_file)

        # Đảm bảo thư mục phiên bản tồn tại
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        """Đảm bảo phiên bản Cấu trúc thư mục tồn tại"""
        self.versions_dir.mkdir(parents=True, exist_ok=True)
        for resource_type in self.RESOURCE_TYPES:
            (self.versions_dir / resource_type).mkdir(exist_ok=True)

    def _load_versions(self) -> dict:
        """Tải siêu dữ liệu phiên bản"""
        if not self.versions_file.exists():
            return {rt: {} for rt in self.RESOURCE_TYPES}

        with open(self.versions_file, encoding="utf-8") as f:
            return json.load(f)

    def _save_versions(self, data: dict) -> None:
        """LưuSiêu dữ liệu phiên bản"""
        with open(self.versions_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _generate_timestamp(self) -> str:
        """Tạo chuỗi dấu thời gian (dùng cho tên tệp)"""
        return datetime.now().strftime("%Y%m%dT%H%M%S")

    def _generate_iso_timestamp(self) -> str:
        """Tạo dấu thời gian định dạng ISO (dùng cho siêu dữ liệu)"""
        return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    def get_versions(self, resource_type: str, resource_id: str) -> dict:
        """
        Lấy thông tin tất cả các phiên bản của tài nguyên

        Args:
            resource_type: Loại tài nguyên (bảng phân cảnh, video, nhân vật, manh mối)
            resource_id: ID tài nguyên (Như E1S01, Giang Nguyệt Hồi)

        Returns:
            Thông tin phiên bản từ Điển, bao gồm current_version và danh sách versions
        """
        if resource_type not in self.RESOURCE_TYPES:
            raise ValueError(f"Loại tài nguyên không được hỗ trợ: {resource_type}")

        with self._lock:
            data = self._load_versions()
            resource_data = data.get(resource_type, {}).get(resource_id)

            if not resource_data:
                return {"current_version": 0, "versions": []}

            # Thêm is_current và file_url từ đoạn
            versions = []
            for v in resource_data.get("versions", []):
                version_info = v.copy()
                version_info["is_current"] = v["version"] == resource_data["current_version"]
                version_info["file_url"] = f"/api/v1/files/{self.project_path.name}/{v['file']}"
                versions.append(version_info)

            return {"current_version": resource_data.get("current_version", 0), "versions": versions}

    def get_current_version(self, resource_type: str, resource_id: str) -> int:
        """
        Lấy số phiên bản hiện tại

        Args:
            resource_type: Loại tài nguyên
            resource_id: ID tài nguyên

        Returns:
            Hiện tạiSố phiên bản, nếu không có phiên bản thì trả về 0
        """
        info = self.get_versions(resource_type, resource_id)
        return info["current_version"]

    def add_version(
        self, resource_type: str, resource_id: str, prompt: str, source_file: Path | None = None, **metadata
    ) -> int:
        """
        ThêmGhi nhận phiên bản mới

        Args:
            resource_type: Loại tài nguyên
            resource_id: ID tài nguyên
            prompt: Tạo prompt sử dụng cho phiên bản này
            source_file: Tệp nguồnĐường dẫn (dùng để sao chép vào thư mục phiên bản)
            **metadata: Dữ liệu meta bổ sung (như aspect_ratio, duration_seconds)

        Returns:
            Số phiên bản mới
        """
        if resource_type not in self.RESOURCE_TYPES:
            raise ValueError(f"Loại tài nguyên không được hỗ trợ: {resource_type}")

        with self._lock:
            data = self._load_versions()

            # Đảm bảo Loại tài nguyên tồn tại
            if resource_type not in data:
                data[resource_type] = {}

            # Lấy hoặc Tạo bản ghi tài nguyên
            if resource_id not in data[resource_type]:
                data[resource_type][resource_id] = {"current_version": 0, "versions": []}

            resource_data = data[resource_type][resource_id]
            existing_versions = resource_data.get("versions", [])
            max_version = max(
                (item.get("version", 0) for item in existing_versions),
                default=0,
            )
            new_version = max_version + 1

            # Tạo phiên bản tên tệp và đường dẫn
            timestamp = self._generate_timestamp()
            ext = self.EXTENSIONS.get(resource_type, ".png")
            version_filename = f"{resource_id}_v{new_version}_{timestamp}{ext}"
            version_rel_path = f"versions/{resource_type}/{version_filename}"
            version_abs_path = self.project_path / version_rel_path

            # Nếu có Tệp nguồn, sao chép vào thư mục phiên bản
            if source_file and Path(source_file).exists():
                shutil.copy2(source_file, version_abs_path)

            # TạoGhi lại phiên bản
            version_record = {
                "version": new_version,
                "file": version_rel_path,
                "prompt": prompt,
                "created_at": self._generate_iso_timestamp(),
                **metadata,
            }

            resource_data["versions"].append(version_record)
            resource_data["current_version"] = new_version

            self._save_versions(data)
            return new_version

    def backup_current(
        self, resource_type: str, resource_id: str, current_file: Path, prompt: str, **metadata
    ) -> int | None:
        """
        Sao lưu tệp Hiện tại vào thư mục phiên bản

        Nếu tệp Hiện tại không tồn tại, không thực hiện hành động nào.

        Args:
            resource_type: Loại tài nguyên
            resource_id: ID tài nguyên
            current_file: Hiện tại文件路径
            prompt: Hiện tạiPrompt của phiên bản
            **metadata: Siêu dữ liệu bổ sung

        Returns:
            Số phiên bản đã sao lưu, nếu chưa sao lưu thì trả về None
        """
        current_file = Path(current_file)
        if not current_file.exists():
            return None

        return self.add_version(
            resource_type=resource_type, resource_id=resource_id, prompt=prompt, source_file=current_file, **metadata
        )

    def ensure_current_tracked(
        self, resource_type: str, resource_id: str, current_file: Path, prompt: str, **metadata
    ) -> int | None:
        """
        Đảm bảo “Hiện tạiTệp ít nhất có một bản ghi phiên bản

        Dùng để nâng cấp/di chuyển Cảnh: trên đĩa đã có current_file, nhưng versions.json vẫn chưa ghi nhận.
        Nếu tài nguyên đó Đã tồn tại bản ghi phiên bản (current_version > 0）thì sẽ không ghi lại lần nữa.

        Args:
            resource_type: Loại tài nguyên
            resource_id: ID tài nguyên
            current_file: Hiện tại文件路径
            prompt: Hiện tạiPrompt tương ứng với tệp (dùng để ghi lại)
            **metadata: Metadata bổ sung

        Returns:
            Số phiên bản mới; nếu không cần thêm hoặc tệp không tồn tại thì trả về None
        """
        current_file = Path(current_file)
        if not current_file.exists():
            return None

        if resource_type not in self.RESOURCE_TYPES:
            raise ValueError(f"Loại tài nguyên không được hỗ trợ: {resource_type}")

        with self._lock:
            if self.get_current_version(resource_type, resource_id) > 0:
                return None
            return self.add_version(
                resource_type=resource_type,
                resource_id=resource_id,
                prompt=prompt,
                source_file=current_file,
                **metadata,
            )

    def restore_version(self, resource_type: str, resource_id: str, version: int, current_file: Path) -> dict:
        """
        Chuyển sang phiên bản được chỉ định

        Sao chép phiên bản được chỉ định vào đường dẫn Hiện tại, và đặt current_version trỏ tới phiên bản đó.

        Args:
            resource_type: Loại tài nguyên
            resource_id: ID tài nguyên
            version: Số phiên bản cần khôi phục
            current_file: Hiện tại文件路径

        Returns:
            Thông tin chuyển đổi, bao gồm restored_version, current_version, prompt
        """
        if resource_type not in self.RESOURCE_TYPES:
            raise ValueError(f"Loại tài nguyên không được hỗ trợ: {resource_type}")

        current_file = Path(current_file)

        with self._lock:
            data = self._load_versions()
            resource_data = data.get(resource_type, {}).get(resource_id)

            if not resource_data:
                raise ValueError(f"Nguồn không tồn tại: {resource_type}/{resource_id}")

            target_version = None
            for v in resource_data["versions"]:
                if v["version"] == version:
                    target_version = v
                    break

            if not target_version:
                raise ValueError(f"Phiên bản không tồn tại: {version}")

            target_file = self.project_path / target_version["file"]
            if not target_file.exists():
                raise FileNotFoundError(f"Tệp phiên bản không tồn tại: {target_file}")

            current_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target_file, current_file)

            resource_data["current_version"] = version
            self._save_versions(data)

        restored_prompt = target_version.get("prompt", "")
        return {
            "restored_version": version,
            "current_version": version,
            "prompt": restored_prompt,
        }

    def get_version_file_url(self, resource_type: str, resource_id: str, version: int) -> str | None:
        """
        Lấy URL của tệp phiên bản được chỉ định

        Args:
            resource_type: Loại tài nguyên
            resource_id: ID tài nguyên
            version: 版本号

        Returns:
            URL tệp, nếu không tồn tại thì trả về None
        """
        info = self.get_versions(resource_type, resource_id)
        for v in info["versions"]:
            if v["version"] == version:
                return v.get("file_url")
        return None

    def get_version_prompt(self, resource_type: str, resource_id: str, version: int) -> str | None:
        """
        Lấy prompt của phiên bản được chỉ định

        Args:
            resource_type: Loại tài nguyên
            resource_id: ID tài nguyên
            version: 版本号

        Returns:
            prompt Văn bản，Trả về None nếu không tồn tại
        """
        info = self.get_versions(resource_type, resource_id)
        for v in info["versions"]:
            if v["version"] == version:
                return v.get("prompt")
        return None

    def has_versions(self, resource_type: str, resource_id: str) -> bool:
        """
        Kiểm tra xem tài nguyên có bản ghi phiên bản hay không

        Args:
            resource_type: Loại tài nguyên
            resource_id: ID tài nguyên

        Returns:
            Có bản ghi phiên bản hay không
        """
        return self.get_current_version(resource_type, resource_id) > 0
