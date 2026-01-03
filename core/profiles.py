from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
from copy import deepcopy

from core.idgen.snowflake import SnowflakeGenerator
from core.io.json_store import ensure_dir, now_iso_utc
from core.models.app_state import AppState
from core.models.base import BaseFile
from core.models.meta import ProfileMeta
from core.models.point import PointsFile
from core.models.skill import SkillsFile
from core.repos.app_state_repo import AppStateRepo
from core.domain.profile import Profile
from core.repos.profile_repo import ProfileRepository
from rotation_editor.core.models import RotationsFile

_ILLEGAL_FS_CHARS = r'<>:"/\\|?*'
_ILLEGAL_FS_RE = re.compile(f"[{re.escape(_ILLEGAL_FS_CHARS)}]")


def sanitize_profile_name(name: str) -> str:
    """Windows 友好的目录名清洗。"""
    name = (name or "").strip()
    if not name:
        return "Default"
    name = _ILLEGAL_FS_RE.sub("_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:64] if len(name) > 64 else name


@dataclass
class ProfileContext:
    """
    单个 Profile 的上下文：

    - profile_name: 逻辑名称（目录名）
    - profile_dir : 物理目录路径
    - idgen       : 用于生成各种 ID 的 SnowflakeGenerator
    - repo        : ProfileRepository（负责 profile.json 的读写）
    - profile     : 聚合后的 Profile 对象（meta/base/skills/points/rotations）

    为了兼容现有调用代码，这里提供 meta/base/skills/points/rotations
    的 property 访问与赋值。
    """

    profile_name: str
    profile_dir: Path

    idgen: SnowflakeGenerator
    repo: ProfileRepository

    profile: Profile

    # ---------- 兼容属性访问 ----------

    @property
    def meta(self) -> ProfileMeta:
        return self.profile.meta

    @meta.setter
    def meta(self, value: ProfileMeta) -> None:
        self.profile.meta = value

    @property
    def base(self) -> BaseFile:
        return self.profile.base

    @base.setter
    def base(self, value: BaseFile) -> None:
        self.profile.base = value

    @property
    def skills(self) -> SkillsFile:
        return self.profile.skills

    @skills.setter
    def skills(self, value: SkillsFile) -> None:
        self.profile.skills = value

    @property
    def points(self) -> PointsFile:
        return self.profile.points

    @points.setter
    def points(self, value: PointsFile) -> None:
        self.profile.points = value

    @property
    def rotations(self) -> RotationsFile:
        return self.profile.rotations

    @rotations.setter
    def rotations(self, value: RotationsFile) -> None:
        self.profile.rotations = value

    # ---------- 旧的批量保存接口（现在用 profile.json） ----------

    def save_all(self, *, backup: bool = True) -> None:
        """
        兼容旧接口：统一保存整个 Profile 到 profile.json。
        """
        self.repo.save(self.profile_name, self.profile, backup=backup)


class ProfileManager:
    """
    负责管理 profiles 根目录下的多个 Profile：

    - 现在使用单一的 profiles/<name>/profile.json 存储：
        * meta/base/skills/points/rotations 全部在一个文件中
    """

    def __init__(
        self,
        *,
        app_data_dir: Path,
        app_state_repo: AppStateRepo,
        app_state: AppState,
        idgen: SnowflakeGenerator,
    ) -> None:
        self._app_data_dir = app_data_dir
        self._profiles_root = app_data_dir / "profiles"
        ensure_dir(self._profiles_root)

        self._app_state_repo = app_state_repo
        self._app_state = app_state
        self._idgen = idgen

        # 聚合仓储
        self._repo = ProfileRepository(self._profiles_root)

        self.current: Optional[ProfileContext] = None

    @property
    def profiles_root(self) -> Path:
        return self._profiles_root

    @property
    def repo(self) -> ProfileRepository:
        return self._repo

    # ---------- 列表 / 存在性 ----------

    def list_profiles(self) -> List[str]:
        if not self._profiles_root.exists():
            return []
        names: List[str] = []
        for p in self._profiles_root.iterdir():
            if p.is_dir():
                names.append(p.name)
        names.sort(key=lambda s: s.lower())
        return names

    def profile_exists(self, name: str) -> bool:
        name = sanitize_profile_name(name)
        return (self._profiles_root / name).exists()

    # ---------- 打开 / 创建 ----------

    def open_last_or_fallback(self) -> ProfileContext:
        last = sanitize_profile_name(self._app_state.last_profile)
        if last and self.profile_exists(last):
            return self.open_profile(last)

        profiles = self.list_profiles()
        if profiles:
            return self.open_profile(profiles[0])

        return self.create_profile("Default")

    def create_profile(self, name: str) -> ProfileContext:
        name = sanitize_profile_name(name)
        profile_dir = self._profiles_root / name
        ensure_dir(profile_dir)

        # 若 profile.json 不存在，ProfileRepository 会创建新的 Profile
        ctx = self._load_profile_dir(profile_dir=profile_dir, profile_name=name)
        self._set_last_profile(name)
        self.current = ctx
        return ctx

    def open_profile(self, name: str) -> ProfileContext:
        name = sanitize_profile_name(name)
        profile_dir = self._profiles_root / name
        if not profile_dir.exists():
            raise FileNotFoundError(f"Profile not found: {name} ({profile_dir})")
        ctx = self._load_profile_dir(profile_dir=profile_dir, profile_name=name)
        self._set_last_profile(name)
        self.current = ctx
        return ctx

    # ---------- 复制 / 删除 / 重命名 ----------

    def copy_profile(self, src_name: str, dst_name: str) -> ProfileContext:
        src = sanitize_profile_name(src_name)
        dst = sanitize_profile_name(dst_name)

        src_dir = self._profiles_root / src
        dst_dir = self._profiles_root / dst

        if not src_dir.exists():
            raise FileNotFoundError(f"Source profile not found: {src}")
        if dst_dir.exists():
            return self.open_profile(dst)

        ensure_dir(dst_dir)

        # 通过聚合复制：避免直接拷贝旧 JSON 结构
        src_profile = self._repo.load_or_create(src, self._idgen)
        new_profile = deepcopy(src_profile)

        now = now_iso_utc()
        new_profile.meta.profile_name = dst
        new_profile.meta.profile_id = self._idgen.next_id()
        new_profile.meta.created_at = now
        new_profile.meta.updated_at = now

        self._repo.save(dst, new_profile, backup=False)

        ctx = self._load_profile_dir(profile_dir=dst_dir, profile_name=dst)
        self._set_last_profile(dst)
        self.current = ctx
        return ctx

    def delete_profile(self, name: str) -> None:
        name = sanitize_profile_name(name)
        profile_dir = self._profiles_root / name
        if not profile_dir.exists():
            return

        shutil.rmtree(profile_dir, ignore_errors=False)

        if sanitize_profile_name(self._app_state.last_profile) == name:
            ctx = self.open_last_or_fallback()
            self.current = ctx

    def rename_profile(self, old_name: str, new_name: str) -> ProfileContext:
        old_name = sanitize_profile_name(old_name)
        new_name = sanitize_profile_name(new_name)

        old_dir = self._profiles_root / old_name
        new_dir = self._profiles_root / new_name

        if not old_dir.exists():
            raise FileNotFoundError(f"Profile not found: {old_name}")
        if new_dir.exists():
            return self.open_profile(new_name)

        old_dir.rename(new_dir)

        # 通过聚合更新 meta.profile_name
        prof = self._repo.load_or_create(new_name, self._idgen)
        prof.meta.profile_name = new_name
        self._repo.save(new_name, prof, backup=False)

        ctx = self._load_profile_dir(profile_dir=new_dir, profile_name=new_name)
        self._set_last_profile(new_name)
        self.current = ctx
        return ctx

    # ---------- 内部工具 ----------

    def _set_last_profile(self, name: str) -> None:
        self._app_state.last_profile = sanitize_profile_name(name)
        self._app_state_repo.save(self._app_state)

    def _load_profile_dir(self, *, profile_dir: Path, profile_name: str) -> ProfileContext:
        """
        使用 ProfileRepository 从 profile.json 加载 Profile 聚合。
        """
        profile = self._repo.load_or_create(profile_name, self._idgen)

        return ProfileContext(
            profile_name=profile_name,
            profile_dir=profile_dir,
            idgen=self._idgen,
            repo=self._repo,
            profile=profile,
        )