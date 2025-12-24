from __future__ import annotations

from pathlib import Path
from typing import Set, Any, Dict

from core.idgen.snowflake import SnowflakeGenerator
from core.io.json_store import atomic_write_json, ensure_dir, read_json
from core.models.skill import SkillsFile
from core.pick.capture import ScreenCapture


class SkillsRepo:
    """
    skills.json schema:
      v1: skills[].pixel: {monitor,x,y,...} (x/y were RELATIVE to monitor)
      v2: skills[].pixel: {monitor,vx,vy,...} (vx/vy are VIRTUAL/ABS coords)
    """

    LATEST_SCHEMA_VERSION = 2

    def __init__(self, profile_dir: Path) -> None:
        self._profile_dir = profile_dir
        ensure_dir(self._profile_dir)

    @property
    def path(self) -> Path:
        return self._profile_dir / "skills.json"

    def load_or_create(self, *, idgen: SnowflakeGenerator) -> SkillsFile:
        data = read_json(self.path, default={})
        data = self._migrate_dict_if_needed(data)

        skills_file = SkillsFile.from_dict(data)

        changed = False

        # 规范化：确保 schema_version
        if int(getattr(skills_file, "schema_version", 0) or 0) != self.LATEST_SCHEMA_VERSION:
            skills_file.schema_version = self.LATEST_SCHEMA_VERSION
            changed = True

        # 规范化：为缺失/重复 ID 的技能补 ID
        seen: Set[str] = set()
        for s in skills_file.skills:
            if (not s.id) or (s.id in seen):
                s.id = idgen.next_id()
                changed = True
            seen.add(s.id)

        if (not self.path.exists()) or changed:
            self.save(skills_file, backup=False)

        return skills_file

    def save(self, skills_file: SkillsFile, *, backup: bool = True) -> None:
        atomic_write_json(self.path, skills_file.to_dict(), backup=backup)

    def _migrate_dict_if_needed(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        In-place migrate dict from v1 -> v2.

        v1 stored pixel x/y as REL coords relative to pixel.monitor.
        v2 stores pixel vx/vy as ABS coords (OS virtual screen).
        """
        try:
            ver = int(data.get("schema_version", 1) or 1)
        except Exception:
            ver = 1

        if ver >= self.LATEST_SCHEMA_VERSION:
            return data

        skills = data.get("skills", [])
        if not isinstance(skills, list):
            data["schema_version"] = self.LATEST_SCHEMA_VERSION
            return data

        cap = ScreenCapture()
        try:
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

                # legacy rel coords
                x_rel = pixel.get("x", 0)
                y_rel = pixel.get("y", 0)

                try:
                    abs_x, abs_y = cap.rel_to_abs(int(x_rel), int(y_rel), mon)
                except Exception:
                    abs_x, abs_y = int(x_rel) if x_rel is not None else 0, int(y_rel) if y_rel is not None else 0

                pixel["vx"] = int(abs_x)
                pixel["vy"] = int(abs_y)

            data["schema_version"] = self.LATEST_SCHEMA_VERSION
            return data
        finally:
            try:
                cap.close()
            except Exception:
                pass