from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from core.idgen.snowflake import SnowflakeGenerator
from core.io.json_store import ensure_dir, now_iso_utc
from core.models.app_state import AppState
from core.models.base import BaseFile
from core.models.meta import ProfileMeta
from core.models.point import PointsFile
from core.models.skill import SkillsFile
from core.repos.app_state_repo import AppStateRepo
from core.repos.base_repo import BaseRepo
from core.repos.meta_repo import MetaRepo
from core.repos.points_repo import PointsRepo
from core.repos.skills_repo import SkillsRepo
from core.domain.profile import Profile
from rotation_editor.core.models import RotationsFile
from rotation_editor.core.storage import load_or_create_rotations

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
    - *_repo      : 旧的 JSON 拆文件仓储（base/meta/skills/points），
                    目前仍用于持久化；后续会统一替换为 ProfileRepository。
    - profile     : 聚合后的 Profile 对象（meta/base/skills/points/rotations）

    为了兼容现有调用代码，这里提供 meta/base/skills/points/rotations
    的 property 访问与赋值。
    """

    profile_name: str
    profile_dir: Path

    idgen: SnowflakeGenerator

    meta_repo: MetaRepo
    base_repo: BaseRepo
    skills_repo: SkillsRepo
    points_repo: PointsRepo

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

    # ---------- 旧的批量保存接口（仍留给少数调用使用） ----------

    def save_all(self, *, backup: bool = True) -> None:
        """
        兼容旧接口：分别保存 base / skills / points / meta。
        目前仍依赖旧的 Repo；后续切到 ProfileRepository 时可以移除。
        """
        self.base_repo.save(self.base, backup=backup)
        self.skills_repo.save(self.skills, backup=backup)
        self.points_repo.save(self.points, backup=backup)
        self.meta_repo.save(self.meta, backup=backup)  # 内部会更新 updated_at


class ProfileManager:
    """
    负责管理 profiles 根目录下的多个 Profile：

    - 目前仍使用拆散的 JSON 文件（base.json / skills.json / points.json / meta.json / rotation.json）
      来加载各部分，然后组装成 Profile 聚合，挂到 ProfileContext.profile 上。
    - 后续会逐步迁移到单一的 profile.json + ProfileRepository。
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

        self.current: Optional[ProfileContext] = None

    @property
    def profiles_root(self) -> Path:
        return self._profiles_root

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

        shutil.copytree(src_dir, dst_dir)

        # refresh meta（仍通过旧的 MetaRepo）
        meta_repo = MetaRepo(dst_dir)
        meta = meta_repo.load_or_create(profile_name=dst, idgen=self._idgen)
        meta.profile_name = dst
        meta.profile_id = self._idgen.next_id()
        meta.created_at = now_iso_utc()
        meta.updated_at = now_iso_utc()
        meta_repo.save(meta, backup=False)

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

        meta_repo = MetaRepo(new_dir)
        meta = meta_repo.load_or_create(profile_name=new_name, idgen=self._idgen)
        meta.profile_name = new_name
        meta_repo.save(meta, backup=False)

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
        从拆散的 JSON 文件加载各部分，然后组装为 Profile 聚合，挂到 ProfileContext 上。

        当前阶段：
        - 仍按 base.json / skills.json / points.json / meta.json / rotation.json 分文件读取；
        - Profile 聚合只是“内存视图”，方便之后统一改为 profile.json。
        """
        meta_repo = MetaRepo(profile_dir)
        base_repo = BaseRepo(profile_dir)
        skills_repo = SkillsRepo(profile_dir)
        points_repo = PointsRepo(profile_dir)

        meta = meta_repo.load_or_create(profile_name=profile_name, idgen=self._idgen)
        base = base_repo.load_or_create()
        skills = skills_repo.load_or_create()
        points = points_repo.load_or_create()
        rotations = load_or_create_rotations(profile_dir)

        profile = Profile(
            schema_version=1,
            meta=meta,
            base=base,
            skills=skills,
            points=points,
            rotations=rotations,
        )

        return ProfileContext(
            profile_name=profile_name,
            profile_dir=profile_dir,
            idgen=self._idgen,
            meta_repo=meta_repo,
            base_repo=base_repo,
            skills_repo=skills_repo,
            points_repo=points_repo,
            profile=profile,
        )