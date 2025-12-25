# File: core/repos/base_repo.py
from __future__ import annotations

from pathlib import Path

from core.io.json_store import atomic_write_json, ensure_dir, read_json
from core.models.base import BaseFile


class BaseRepo:
    """
    Step 1 change:
    - migrations 已移除：不再 migrate_base_json
    - 只负责：不存在则创建默认文件；存在则直读
    """

    def __init__(self, profile_dir: Path) -> None:
        self._profile_dir = profile_dir
        ensure_dir(self._profile_dir)

    @property
    def path(self) -> Path:
        return self._profile_dir / "base.json"

    def load_or_create(self) -> BaseFile:
        existed = self.path.exists()
        data = read_json(self.path, default={})
        base = BaseFile.from_dict(data)

        if not existed:
            self.save(base, backup=False)

        return base

    def save(self, base: BaseFile, *, backup: bool = False) -> None:
        atomic_write_json(self.path, base.to_dict(), backup=backup)