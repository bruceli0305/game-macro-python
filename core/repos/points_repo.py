from __future__ import annotations

from pathlib import Path
from typing import Set

from core.idgen.snowflake import SnowflakeGenerator
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

    def load_or_create(self, *, idgen: SnowflakeGenerator) -> PointsFile:
        existed = self.path.exists()
        data = read_json(self.path, default={})

        mig = migrate_points_json(data)
        data = mig.data

        points_file = PointsFile.from_dict(data)

        changed = bool(mig.changed)

        if int(getattr(points_file, "schema_version", 0) or 0) != LATEST_POINTS_SCHEMA_VERSION:
            points_file.schema_version = LATEST_POINTS_SCHEMA_VERSION
            changed = True

        # 规范化：为缺失/重复 ID 的点位补 ID（临时保留，后续会迁到 service）
        seen: Set[str] = set()
        for p in points_file.points:
            if (not p.id) or (p.id in seen):
                p.id = idgen.next_id()
                changed = True
            seen.add(p.id)

        if (not existed) or changed:
            backup = bool(existed and mig.changed)
            self.save(points_file, backup=backup)

        return points_file

    def save(self, points_file: PointsFile, *, backup: bool = True) -> None:
        atomic_write_json(self.path, points_file.to_dict(), backup=backup)