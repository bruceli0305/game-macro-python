from __future__ import annotations

from typing import Any, Dict

from core.migrations.types import MigrationOutcome
from core.pick.capture import ScreenCapture


LATEST_POINTS_SCHEMA_VERSION = 2


def _as_int(v: Any, default: int) -> int:
    try:
        if v is None:
            return default
        if isinstance(v, bool):
            return int(v)
        return int(v)
    except Exception:
        return default


def migrate_points_json(data: Dict[str, Any]) -> MigrationOutcome:
    """
    points.json migrations:

    v1 -> v2:
      - points[] used x/y (REL coords under point.monitor)
      - v2 uses vx/vy (ABS virtual screen coords)
      - remove legacy keys x/y/abs_x/abs_y
    """
    if not isinstance(data, dict):
        data = {}

    from_ver = _as_int(data.get("schema_version", 1), 1)

    if from_ver >= LATEST_POINTS_SCHEMA_VERSION:
        if from_ver != LATEST_POINTS_SCHEMA_VERSION:
            data["schema_version"] = LATEST_POINTS_SCHEMA_VERSION
            return MigrationOutcome(data=data, changed=True, from_version=from_ver, to_version=LATEST_POINTS_SCHEMA_VERSION)
        return MigrationOutcome(data=data, changed=False, from_version=from_ver, to_version=from_ver)

    changed = False
    cap = ScreenCapture()
    try:
        pts = data.get("points", [])
        if not isinstance(pts, list):
            data["points"] = []
            data["schema_version"] = LATEST_POINTS_SCHEMA_VERSION
            return MigrationOutcome(data=data, changed=True, from_version=from_ver, to_version=LATEST_POINTS_SCHEMA_VERSION, notes="points was not a list")

        if from_ver <= 1:
            for item in pts:
                if not isinstance(item, dict):
                    continue

                if "vx" in item and "vy" in item:
                    continue

                mon = str(item.get("monitor", "primary") or "primary")
                x_rel = _as_int(item.get("x", 0), 0)
                y_rel = _as_int(item.get("y", 0), 0)

                try:
                    abs_x, abs_y = cap.rel_to_abs(x_rel, y_rel, mon)
                except Exception:
                    abs_x, abs_y = x_rel, y_rel

                item["vx"] = int(abs_x)
                item["vy"] = int(abs_y)

                item.pop("x", None)
                item.pop("y", None)
                item.pop("abs_x", None)
                item.pop("abs_y", None)

                changed = True

            data["schema_version"] = LATEST_POINTS_SCHEMA_VERSION
            changed = True

        return MigrationOutcome(
            data=data,
            changed=changed,
            from_version=from_ver,
            to_version=_as_int(data.get("schema_version", from_ver), from_ver),
        )
    finally:
        try:
            cap.close()
        except Exception:
            pass