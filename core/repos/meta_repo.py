from __future__ import annotations

from pathlib import Path

from core.idgen.snowflake import SnowflakeGenerator
from core.io.json_store import atomic_write_json, ensure_dir, now_iso_utc, read_json
from core.migrations.meta_json import migrate_meta_json
from core.models.meta import ProfileMeta


class MetaRepo:
    def __init__(self, profile_dir: Path) -> None:
        self._profile_dir = profile_dir
        ensure_dir(self._profile_dir)

    @property
    def path(self) -> Path:
        return self._profile_dir / "meta.json"

    def load_or_create(self, *, profile_name: str, idgen: SnowflakeGenerator) -> ProfileMeta:
        existed = self.path.exists()
        data = read_json(self.path, default={})

        mig = migrate_meta_json(data)
        data = mig.data

        meta = ProfileMeta.from_dict(data)

        changed = bool(mig.changed)
        now = now_iso_utc()

        if not meta.profile_id:
            meta.profile_id = idgen.next_id()
            changed = True

        if not meta.profile_name:
            meta.profile_name = profile_name
            changed = True

        if not meta.created_at:
            meta.created_at = now
            changed = True

        if not meta.updated_at:
            meta.updated_at = now
            changed = True

        # if file missing or anything changed, persist
        if (not existed) or changed:
            # if existing file and only migration changed, create a backup; otherwise keep old behavior
            backup = bool(existed and mig.changed)
            self.save(meta, backup=backup)

        return meta

    def save(self, meta: ProfileMeta, *, backup: bool = True) -> None:
        # 保存时更新 updated_at
        now = now_iso_utc()
        if not meta.created_at:
            meta.created_at = now
        meta.updated_at = now
        atomic_write_json(self.path, meta.to_dict(), backup=backup)