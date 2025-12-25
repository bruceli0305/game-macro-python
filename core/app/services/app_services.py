from __future__ import annotations

from core.app.uow import ProfileUnitOfWork
from core.app.services.skills_service import SkillsService
from core.app.services.points_service import PointsService
from core.event_bus import EventBus
from core.event_types import EventType
from core.profiles import ProfileContext


class AppServices:
    def __init__(self, *, bus: EventBus, ctx: ProfileContext) -> None:
        self.bus = bus
        self.uow = ProfileUnitOfWork(ctx)

        self.skills = SkillsService(uow=self.uow)
        self.points = PointsService(uow=self.uow)

    @property
    def ctx(self) -> ProfileContext:
        return self.uow.ctx

    def set_context(self, ctx: ProfileContext) -> None:
        self.uow.set_context(ctx)
        self.notify_dirty()

    def notify_dirty(self) -> None:
        parts = sorted(list(self.uow.dirty_parts()))
        self.bus.post(EventType.DIRTY_STATE_CHANGED, dirty=bool(self.uow.is_dirty()), parts=parts)