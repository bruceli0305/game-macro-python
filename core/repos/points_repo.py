from __future__ import annotations

from pathlib import Path

from core.io.json_store import atomic_write_json, ensure_dir, read_json
from core.migrations.points_json import migrate_points_json, LATEST_POINTS_SCHEMA_VERSION
from core.models.point import PointsFile


class PointsRepo:
    def __init__(self, profile_dir: Path) -> None:
        self._profile_dir = profile_dir
        ensure_dir(self._profile_dir)

    @property
    def path(self) -> Path:
        return self._profile_dir / "points.json"

    def load_or_create(self) -> PointsFile:
        existed = self.path.exists()
        data = read_json(self.path, default={})

        mig = migrate_points_json(data)
        data = mig.data

        points_file = PointsFile.from_dict(data)

        changed = bool(mig.changed)

        if int(getattr(points_file, "schema_version", 0) or 0) != LATEST_POINTS_SCHEMA_VERSION:
            points_file.schema_version = LATEST_POINTS_SCHEMA_VERSION
            changed = True

        if (not existed) or changed:
            backup = bool(existed and mig.changed)
            self.save(points_file, backup=backup)

        return points_file

    def save(self, points_file: PointsFile, *, backup: bool = True) -> None:
        atomic_write_json(self.path, points_file.to_dict(), backup=backup)