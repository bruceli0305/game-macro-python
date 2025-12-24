from __future__ import annotations

from pathlib import Path
from typing import Set

from core.idgen.snowflake import SnowflakeGenerator
from core.io.json_store import atomic_write_json, ensure_dir, read_json
from core.models.skill import SkillsFile


class SkillsRepo:
    def __init__(self, profile_dir: Path) -> None:
        self._profile_dir = profile_dir
        ensure_dir(self._profile_dir)

    @property
    def path(self) -> Path:
        return self._profile_dir / "skills.json"

    def load_or_create(self, *, idgen: SnowflakeGenerator) -> SkillsFile:
        data = read_json(self.path, default={})
        skills_file = SkillsFile.from_dict(data)

        changed = False

        # 规范化：确保 schema_version
        if "schema_version" not in data:
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