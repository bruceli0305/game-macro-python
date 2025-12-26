# File: core/app/services/profile_service.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from core.app.services.app_services import AppServices
from core.event_bus import EventBus
from core.event_types import EventType
from core.events.payloads import ProfileChangedPayload, ProfileListChangedPayload
from core.profiles import ProfileContext, ProfileManager


@dataclass(frozen=True)
class ProfileResult:
    ctx: ProfileContext
    names: List[str]


class ProfileService:
    def __init__(self, *, pm: ProfileManager, services: AppServices, bus: EventBus) -> None:
        self._pm = pm
        self._services = services
        self._bus = bus

    def list_profiles(self) -> List[str]:
        names = self._pm.list_profiles()
        return names or ["Default"]

    def _publish_list_changed(self, *, current: str) -> None:
        self._bus.post_payload(
            EventType.PROFILE_LIST_CHANGED,
            ProfileListChangedPayload(names=self.list_profiles(), current=current),
        )

    def _publish_changed(self, *, name: str) -> None:
        self._bus.post_payload(EventType.PROFILE_CHANGED, ProfileChangedPayload(name=name))

    def _bind_ctx(self, ctx: ProfileContext) -> None:
        self._services.set_context(ctx)
        self._publish_changed(name=ctx.profile_name)
        self._publish_list_changed(current=ctx.profile_name)

    def open_and_bind(self, name: str) -> ProfileResult:
        ctx = self._pm.open_profile(name)
        self._bind_ctx(ctx)
        return ProfileResult(ctx=ctx, names=self.list_profiles())

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