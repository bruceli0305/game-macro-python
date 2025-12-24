from __future__ import annotations

from pathlib import Path

from core.io.json_store import atomic_write_json, ensure_dir, read_json
from core.models.base import BaseFile


class BaseRepo:
    def __init__(self, profile_dir: Path) -> None:
        self._profile_dir = profile_dir
        ensure_dir(self._profile_dir)

    @property
    def path(self) -> Path:
        return self._profile_dir / "base.json"

    def load_or_create(self) -> BaseFile:
        data = read_json(self.path, default={})
        base = BaseFile.from_dict(data)

        # 文件不存在或缺 schema_version 时，写回一个规范化版本
        if (not self.path.exists()) or ("schema_version" not in data):
            self.save(base, backup=False)

        return base

    def save(self, base: BaseFile, *, backup: bool = True) -> None:
        atomic_write_json(self.path, base.to_dict(), backup=backup)