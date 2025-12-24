from __future__ import annotations

from pathlib import Path
from typing import Set

from core.idgen.snowflake import SnowflakeGenerator
from core.io.json_store import atomic_write_json, ensure_dir, read_json
from core.migrations.skills_json import migrate_skills_json, LATEST_SKILLS_SCHEMA_VERSION
from core.models.skill import SkillsFile


class SkillsRepo:
    def __init__(self, profile_dir: Path) -> None:
        self._profile_dir = profile_dir
        ensure_dir(self._profile_dir)

    @property
    def path(self) -> Path:
        return self._profile_dir / "skills.json"

    def load_or_create(self, *, idgen: SnowflakeGenerator) -> SkillsFile:
        existed = self.path.exists()
        data = read_json(self.path, default={})

        mig = migrate_skills_json(data)
        data = mig.data

        skills_file = SkillsFile.from_dict(data)

        changed = bool(mig.changed)

        # keep schema_version consistent in object
        if int(getattr(skills_file, "schema_version", 0) or 0) != LATEST_SKILLS_SCHEMA_VERSION:
            skills_file.schema_version = LATEST_SKILLS_SCHEMA_VERSION
            changed = True

        # 规范化：为缺失/重复 ID 的技能补 ID（临时保留，后续会迁到 service）
        seen: Set[str] = set()
        for s in skills_file.skills:
            if (not s.id) or (s.id in seen):
                s.id = idgen.next_id()
                changed = True
            seen.add(s.id)

        if (not existed) or changed:
            # 只有 schema migration 才做 .bak，避免 load_or_create 每次都生成备份
            backup = bool(existed and mig.changed)
            self.save(skills_file, backup=backup)

        return skills_file

    def save(self, skills_file: SkillsFile, *, backup: bool = True) -> None:
        atomic_write_json(self.path, skills_file.to_dict(), backup=backup)