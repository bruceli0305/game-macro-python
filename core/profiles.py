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
    profile_name: str
    profile_dir: Path

    idgen: SnowflakeGenerator

    meta_repo: MetaRepo
    base_repo: BaseRepo
    skills_repo: SkillsRepo
    points_repo: PointsRepo

    meta: ProfileMeta
    base: BaseFile
    skills: SkillsFile
    points: PointsFile

    def save_all(self, *, backup: bool = True) -> None:
        self.base_repo.save(self.base, backup=backup)
        self.skills_repo.save(self.skills, backup=backup)
        self.points_repo.save(self.points, backup=backup)
        self.meta_repo.save(self.meta, backup=backup)  # 内部会更新 updated_at


class ProfileManager:
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

    def copy_profile(self, src_name: str, dst_name: str) -> ProfileContext:
        """
        复制一个 profile 目录（包含多个 JSON）。
        复制后会“重置 meta.profile_id/created_at/updated_at/profile_name”，确保是新的 profile。
        """
        src = sanitize_profile_name(src_name)
        dst = sanitize_profile_name(dst_name)

        src_dir = self._profiles_root / src
        dst_dir = self._profiles_root / dst

        if not src_dir.exists():
            raise FileNotFoundError(f"Source profile not found: {src}")
        if dst_dir.exists():
            # 已存在就直接打开
            return self.open_profile(dst)

        shutil.copytree(src_dir, dst_dir)

        # 强制刷新 meta（生成新 profile_id 等）
        meta_repo = MetaRepo(dst_dir)
        meta = meta_repo.load_or_create(profile_name=dst, idgen=self._idgen)
        meta.profile_name = dst
        # 这里把 profile_id 重置成新的（避免 copy 后 ID 相同）
        meta.profile_id = self._idgen.next_id()
        # 复制应当当作“新 profile”，重置 created_at
        meta.created_at = now_iso_utc()
        meta.updated_at = now_iso_utc()
        meta_repo.save(meta, backup=False)

        # 其他文件若缺失/损坏，load_or_create 会自动补齐
        ctx = self._load_profile_dir(profile_dir=dst_dir, profile_name=dst)
        self._set_last_profile(dst)
        self.current = ctx
        return ctx

    def delete_profile(self, name: str) -> None:
        """
        删除 profile 目录（危险操作）。如果删的是 last_profile，会自动切到 fallback 并更新 app_state。
        """
        name = sanitize_profile_name(name)
        profile_dir = self._profiles_root / name
        if not profile_dir.exists():
            return

        shutil.rmtree(profile_dir, ignore_errors=False)

        if sanitize_profile_name(self._app_state.last_profile) == name:
            # 删除 last_profile 后，切换到 fallback（或 Default）
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
            # 目标已存在，直接打开目标
            return self.open_profile(new_name)

        old_dir.rename(new_dir)

        # 更新 meta.profile_name
        meta_repo = MetaRepo(new_dir)
        meta = meta_repo.load_or_create(profile_name=new_name, idgen=self._idgen)
        meta.profile_name = new_name
        meta_repo.save(meta, backup=False)

        ctx = self._load_profile_dir(profile_dir=new_dir, profile_name=new_name)
        self._set_last_profile(new_name)
        self.current = ctx
        return ctx

    def _set_last_profile(self, name: str) -> None:
        self._app_state.last_profile = sanitize_profile_name(name)
        self._app_state_repo.save(self._app_state)

    def _load_profile_dir(self, *, profile_dir: Path, profile_name: str) -> ProfileContext:
        meta_repo = MetaRepo(profile_dir)
        base_repo = BaseRepo(profile_dir)
        skills_repo = SkillsRepo(profile_dir)
        points_repo = PointsRepo(profile_dir)

        meta = meta_repo.load_or_create(profile_name=profile_name, idgen=self._idgen)
        base = base_repo.load_or_create()
        skills = skills_repo.load_or_create(idgen=self._idgen)
        points = points_repo.load_or_create(idgen=self._idgen)

        return ProfileContext(
            profile_name=profile_name,
            profile_dir=profile_dir,
            idgen=self._idgen,
            meta_repo=meta_repo,
            base_repo=base_repo,
            skills_repo=skills_repo,
            points_repo=points_repo,
            meta=meta,
            base=base,
            skills=skills,
            points=points,
        )