from __future__ import annotations

from pathlib import Path
from typing import Set, Any, Dict

from core.idgen.snowflake import SnowflakeGenerator
from core.io.json_store import atomic_write_json, ensure_dir, read_json
from core.models.point import PointsFile
from core.pick.capture import ScreenCapture


class PointsRepo:
    """
    points.json schema:
      v1: points[]: {monitor,x,y,...} (x/y were RELATIVE to monitor)
      v2: points[]: {monitor,vx,vy,...} (vx/vy are VIRTUAL/ABS coords)
    """

    LATEST_SCHEMA_VERSION = 2

    def __init__(self, profile_dir: Path) -> None:
        self._profile_dir = profile_dir
        ensure_dir(self._profile_dir)

    @property
    def path(self) -> Path:
        return self._profile_dir / "points.json"

    def load_or_create(self, *, idgen: SnowflakeGenerator) -> PointsFile:
        data = read_json(self.path, default={})
        data = self._migrate_dict_if_needed(data)

        points_file = PointsFile.from_dict(data)

        changed = False

        if int(getattr(points_file, "schema_version", 0) or 0) != self.LATEST_SCHEMA_VERSION:
            points_file.schema_version = self.LATEST_SCHEMA_VERSION
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

    def _migrate_dict_if_needed(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        In-place migrate dict from v1 -> v2.

        v1 stored x/y as REL coords relative to monitor.
        v2 stores vx/vy as ABS coords (OS virtual screen).
        """
        try:
            ver = int(data.get("schema_version", 1) or 1)
        except Exception:
            ver = 1

        if ver >= self.LATEST_SCHEMA_VERSION:
            return data

        pts = data.get("points", [])
        if not isinstance(pts, list):
            data["schema_version"] = self.LATEST_SCHEMA_VERSION
            return data

        cap = ScreenCapture()
        try:
            for item in pts:
                if not isinstance(item, dict):
                    continue

                if "vx" in item and "vy" in item:
                    continue

                mon = str(item.get("monitor", "primary") or "primary")
                x_rel = item.get("x", 0)
                y_rel = item.get("y", 0)

                try:
                    abs_x, abs_y = cap.rel_to_abs(int(x_rel), int(y_rel), mon)
                except Exception:
                    abs_x, abs_y = int(x_rel) if x_rel is not None else 0, int(y_rel) if y_rel is not None else 0

                item["vx"] = int(abs_x)
                item["vy"] = int(abs_y)

            data["schema_version"] = self.LATEST_SCHEMA_VERSION
            return data
        finally:
            try:
                cap.close()
            except Exception:
                pass