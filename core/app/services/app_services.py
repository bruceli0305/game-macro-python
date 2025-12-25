from __future__ import annotations

from core.app.uow import ProfileUnitOfWork
from core.app.services.base_settings_service import BaseSettingsService
from core.app.services.skills_service import SkillsService
from core.app.services.points_service import PointsService
from core.event_bus import EventBus
from core.event_types import EventType
from core.events.payloads import DirtyStateChangedPayload
from core.profiles import ProfileContext


class AppServices:
    def __init__(self, *, bus: EventBus, ctx: ProfileContext) -> None:
        self.bus = bus
        self.uow = ProfileUnitOfWork(ctx)

        self.base = BaseSettingsService(uow=self.uow, bus=self.bus, notify_dirty=self.notify_dirty)
        self.skills = SkillsService(uow=self.uow, bus=self.bus, notify_dirty=self.notify_dirty)
        self.points = PointsService(uow=self.uow, bus=self.bus, notify_dirty=self.notify_dirty)

    @property
    def ctx(self) -> ProfileContext:
        return self.uow.ctx

    def set_context(self, ctx: ProfileContext) -> None:
        self.uow.set_context(ctx)
        self.notify_dirty()

    def notify_dirty(self) -> None:
        parts = sorted(list(self.uow.dirty_parts()))
        payload = DirtyStateChangedPayload(dirty=bool(self.uow.is_dirty()), parts=parts)
        self.bus.post_payload(EventType.DIRTY_STATE_CHANGED, payload)