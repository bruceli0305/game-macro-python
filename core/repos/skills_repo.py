# File: core/repos/skills_repo.py
from __future__ import annotations

from pathlib import Path

from core.io.json_store import atomic_write_json, ensure_dir, read_json
from core.models.skill import SkillsFile


class SkillsRepo:
    """
    Step 1 change:
    - migrations 已移除：不再 migrate_skills_json / LATEST_SKILLS_SCHEMA_VERSION
    - 不存在则创建默认文件；存在则直读
    """

    def __init__(self, profile_dir: Path) -> None:
        self._profile_dir = profile_dir
        ensure_dir(self._profile_dir)

    @property
    def path(self) -> Path:
        return self._profile_dir / "skills.json"

    def load_or_create(self) -> SkillsFile:
        existed = self.path.exists()
        data = read_json(self.path, default={})
        skills_file = SkillsFile.from_dict(data)

        if not existed:
            self.save(skills_file, backup=False)

        return skills_file

    def save(self, skills_file: SkillsFile, *, backup: bool = False) -> None:
        atomic_write_json(self.path, skills_file.to_dict(), backup=backup)