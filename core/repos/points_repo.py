# File: core/repos/points_repo.py
from __future__ import annotations

from pathlib import Path

from core.io.json_store import atomic_write_json, ensure_dir, read_json
from core.models.point import PointsFile


class PointsRepo:
    """
    Step 1 change:
    - migrations 已移除：不再 migrate_points_json / LATEST_POINTS_SCHEMA_VERSION
    - 不存在则创建默认文件；存在则直读
    """

    def __init__(self, profile_dir: Path) -> None:
        self._profile_dir = profile_dir
        ensure_dir(self._profile_dir)

    @property
    def path(self) -> Path:
        return self._profile_dir / "points.json"

    def load_or_create(self) -> PointsFile:
        existed = self.path.exists()
        data = read_json(self.path, default={})
        points_file = PointsFile.from_dict(data)

        if not existed:
            self.save(points_file, backup=False)

        return points_file

    def save(self, points_file: PointsFile, *, backup: bool = False) -> None:
        atomic_write_json(self.path, points_file.to_dict(), backup=backup)