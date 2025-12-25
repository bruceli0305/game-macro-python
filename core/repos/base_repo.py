from __future__ import annotations

from pathlib import Path

from core.io.json_store import atomic_write_json, ensure_dir, read_json
from core.migrations.base_json import migrate_base_json
from core.models.base import BaseFile


class BaseRepo:
    def __init__(self, profile_dir: Path) -> None:
        self._profile_dir = profile_dir
        ensure_dir(self._profile_dir)

    @property
    def path(self) -> Path:
        return self._profile_dir / "base.json"

    def load_or_create(self) -> BaseFile:
        existed = self.path.exists()
        data = read_json(self.path, default={})

        mig = migrate_base_json(data)
        data = mig.data

        base = BaseFile.from_dict(data)

        # If file missing or migration changed, write back canonicalized form.
        if (not existed) or mig.changed:
            # backup only when migrating an existing file
            self.save(base, backup=bool(existed and mig.changed))
        return base

    def save(self, base: BaseFile, *, backup: bool = True) -> None:
        atomic_write_json(self.path, base.to_dict(), backup=backup)