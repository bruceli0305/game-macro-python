from __future__ import annotations

from typing import Any, Dict, Tuple

from core.migrations.types import MigrationOutcome
from core.pick.capture import ScreenCapture


LATEST_SKILLS_SCHEMA_VERSION = 2


def _as_int(v: Any, default: int) -> int:
    try:
        if v is None:
            return default
        if isinstance(v, bool):
            return int(v)
        return int(v)
    except Exception:
        return default


def migrate_skills_json(data: Dict[str, Any]) -> MigrationOutcome:
    """
    skills.json migrations:

    v1 -> v2:
      - skills[].pixel used x/y (REL coords under pixel.monitor)
      - v2 uses vx/vy (ABS virtual screen coords)
      - remove legacy keys x/y/abs_x/abs_y to avoid ambiguity
    """
    if not isinstance(data, dict):
        data = {}

    from_ver = _as_int(data.get("schema_version", 1), 1)

    if from_ver >= LATEST_SKILLS_SCHEMA_VERSION:
        # normalize schema_version (optional)
        if from_ver != LATEST_SKILLS_SCHEMA_VERSION:
            data["schema_version"] = LATEST_SKILLS_SCHEMA_VERSION
            return MigrationOutcome(data=data, changed=True, from_version=from_ver, to_version=LATEST_SKILLS_SCHEMA_VERSION)
        return MigrationOutcome(data=data, changed=False, from_version=from_ver, to_version=from_ver)

    changed = False
    cap = ScreenCapture()
    try:
        skills = data.get("skills", [])
        if not isinstance(skills, list):
            # badly formed -> just bump version and let from_dict handle empty
            data["skills"] = []
            data["schema_version"] = LATEST_SKILLS_SCHEMA_VERSION
            return MigrationOutcome(data=data, changed=True, from_version=from_ver, to_version=LATEST_SKILLS_SCHEMA_VERSION, notes="skills was not a list")

        # v1 -> v2
        if from_ver <= 1:
            for item in skills:
                if not isinstance(item, dict):
                    continue
                pixel = item.get("pixel")
                if not isinstance(pixel, dict):
                    continue

                # already migrated?
                if "vx" in pixel and "vy" in pixel:
                    continue

                mon = str(pixel.get("monitor", "primary") or "primary")

                x_rel = _as_int(pixel.get("x", 0), 0)
                y_rel = _as_int(pixel.get("y", 0), 0)

                try:
                    abs_x, abs_y = cap.rel_to_abs(x_rel, y_rel, mon)
                except Exception:
                    # fallback: treat legacy x/y as abs
                    abs_x, abs_y = x_rel, y_rel

                pixel["vx"] = int(abs_x)
                pixel["vy"] = int(abs_y)

                # remove ambiguous legacy keys
                pixel.pop("x", None)
                pixel.pop("y", None)
                pixel.pop("abs_x", None)
                pixel.pop("abs_y", None)

                changed = True

            data["schema_version"] = LATEST_SKILLS_SCHEMA_VERSION
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