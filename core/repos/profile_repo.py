from __future__ import annotations

from pathlib import Path

from core.idgen.snowflake import SnowflakeGenerator
from core.io.json_store import ensure_dir, read_json, atomic_write_json
from core.domain.profile import Profile
from core.profiles import sanitize_profile_name


class ProfileRepository:
    """
    Profile 聚合仓储：
    - 负责 profiles/<name>/profile.json 的读写
    - 不关心 ProfileManager/AppState 等，只管单个 profile
    """

    def __init__(self, profiles_root: Path) -> None:
        self._root = profiles_root
        ensure_dir(self._root)

    @property
    def root(self) -> Path:
        return self._root

    # ---------- 路径 ----------

    def _dir_for(self, name: str) -> Path:
        """
        返回某个 profile 名称对应的目录路径（已 sanitize）。
        """
        return self._root / sanitize_profile_name(name)

    def path_for(self, name: str) -> Path:
        """
        返回某个 profile 名称对应的 profile.json 路径。
        """
        return self._dir_for(name) / "profile.json"

    # ---------- 读写 ----------

    def load_or_create(self, name: str, idgen: SnowflakeGenerator) -> Profile:
        """
        读取 profiles/<name>/profile.json：
        - 若文件不存在：创建一个全新的 Profile.new(name, idgen) 并写盘，再返回；
        - 若存在：read_json -> Profile.from_dict。
        """
        p = self.path_for(name)
        ensure_dir(p.parent)

        if not p.exists():
            prof = Profile.new(name, idgen)
            atomic_write_json(p, prof.to_dict(), backup=False)
            return prof

        data = read_json(p, default={})
        prof = Profile.from_dict(data)
        return prof

    def save(self, name: str, profile: Profile, *, backup: bool = True) -> None:
        """
        将 Profile 聚合写回 profiles/<name>/profile.json。
        """
        p = self.path_for(name)
        ensure_dir(p.parent)
        atomic_write_json(p, profile.to_dict(), backup=backup)