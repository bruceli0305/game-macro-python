from __future__ import annotations

from pathlib import Path
from typing import Set

from core.idgen.snowflake import SnowflakeGenerator
from core.io.json_store import atomic_write_json, ensure_dir, read_json
from core.models.point import PointsFile


class PointsRepo:
    def __init__(self, profile_dir: Path) -> None:
        self._profile_dir = profile_dir
        ensure_dir(self._profile_dir)

    @property
    def path(self) -> Path:
        return self._profile_dir / "points.json"

    def load_or_create(self, *, idgen: SnowflakeGenerator) -> PointsFile:
        data = read_json(self.path, default={})
        points_file = PointsFile.from_dict(data)

        changed = False

        if "schema_version" not in data:
            changed = True

        seen: Set[str] = set()
        for p in points_file.points:
            if (not p.id) or (p.id in seen):
                p.id = idgen.next_id()
                changed = True
            seen.add(p.id)

        if (not self.path.exists()) or changed:
            self.save(points_file, backup=False)

        return points_file

    def save(self, points_file: PointsFile, *, backup: bool = True) -> None:
        atomic_write_json(self.path, points_file.to_dict(), backup=backup)