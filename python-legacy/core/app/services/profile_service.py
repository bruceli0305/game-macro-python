# File: core/app/services/profile_service.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from core.app.services.app_services import AppServices
from core.profiles import ProfileContext, ProfileManager


@dataclass(frozen=True)
class ProfileResult:
    ctx: ProfileContext
    names: List[str]


class ProfileService:
    """
    Step 3-3-3-3-7:
    - ProfileService 不再依赖 EventBus
    - 不发布 PROFILE_CHANGED / PROFILE_LIST_CHANGED
    - 只负责：ProfileManager 文件系统操作 + bind ctx 到 AppServices
    """

    def __init__(self, *, pm: ProfileManager, services: AppServices) -> None:
        self._pm = pm
        self._services = services

    def list_profiles(self) -> List[str]:
        names = self._pm.list_profiles()
        return names or ["Default"]

    def _bind_ctx(self, ctx: ProfileContext) -> None:
        self._services.set_context(ctx)

    # -------- open/switch --------
    def open_and_bind(self, name: str) -> ProfileResult:
        ctx = self._pm.open_profile(name)
        self._bind_ctx(ctx)
        return ProfileResult(ctx=ctx, names=self.list_profiles())

    # -------- create/copy/rename/delete --------
    def create_and_bind(self, name: str) -> ProfileResult:
        ctx = self._pm.create_profile(name)
        self._bind_ctx(ctx)
        return ProfileResult(ctx=ctx, names=self.list_profiles())

    def copy_and_bind(self, src_name: str, dst_name: str) -> ProfileResult:
        ctx = self._pm.copy_profile(src_name, dst_name)
        self._bind_ctx(ctx)
        return ProfileResult(ctx=ctx, names=self.list_profiles())

    def rename_and_bind(self, old_name: str, new_name: str) -> ProfileResult:
        ctx = self._pm.rename_profile(old_name, new_name)
        self._bind_ctx(ctx)
        return ProfileResult(ctx=ctx, names=self.list_profiles())

    def delete_and_bind_fallback(self, name: str) -> ProfileResult:
        self._pm.delete_profile(name)
        ctx = self._pm.current or self._pm.open_last_or_fallback()
        self._bind_ctx(ctx)
        return ProfileResult(ctx=ctx, names=self.list_profiles())