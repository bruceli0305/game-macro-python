# File: core/app/services/app_services.py
from __future__ import annotations

from typing import Set, Optional, Iterable

from core.app.uow import ProfileUnitOfWork, Part
from core.app.services.base_settings_service import BaseSettingsService
from core.app.services.skills_service import SkillsService
from core.app.services.points_service import PointsService
from core.event_bus import EventBus
from core.event_types import EventType
from core.events.payloads import DirtyStateChangedPayload, ErrorPayload
from core.profiles import ProfileContext


class AppServices:
    def __init__(self, *, bus: EventBus, ctx: ProfileContext) -> None:
        self.bus = bus
        self.uow = ProfileUnitOfWork(ctx)

        self.base = BaseSettingsService(uow=self.uow, bus=self.bus, notify_dirty=self.notify_dirty)
        self.skills = SkillsService(uow=self.uow, bus=self.bus, notify_dirty=self.notify_dirty)
        self.points = PointsService(uow=self.uow, bus=self.bus, notify_dirty=self.notify_dirty)

        # repair once on startup context
        self._repair_ids_and_persist()

    @property
    def ctx(self) -> ProfileContext:
        return self.uow.ctx

    def set_context(self, ctx: ProfileContext) -> None:
        self.uow.set_context(ctx)
        self._repair_ids_and_persist()
        self.notify_dirty()

    # ---------- UoW state facade ----------
    def dirty_parts(self) -> Set[Part]:
        try:
            return set(self.uow.dirty_parts())
        except Exception:
            return set()

    def is_dirty(self) -> bool:
        try:
            return bool(self.uow.is_dirty())
        except Exception:
            return False

    def commit_parts_cmd(
        self,
        *,
        parts: Iterable[str],
        backup: Optional[bool] = None,
        touch_meta: bool = True,
    ) -> bool:
        """
        Centralized commit entry for non-UI orchestrators.

        parts: iterable of {"base","skills","points","meta"} (strings)
        Returns True if commit performed, False if no valid parts.
        """
        valid = {"base", "skills", "points", "meta"}
        target: Set[Part] = set()

        for p in parts:
            ps = (str(p) if p is not None else "").strip()
            if not ps:
                continue
            if ps not in valid:
                raise ValueError(f"Unknown part: {ps!r}")
            target.add(ps)  # type: ignore[arg-type]

        if not target:
            return False

        if backup is None:
            try:
                backup = bool(getattr(self.ctx.base.io, "backup_on_save", True))
            except Exception:
                backup = True

        self.uow.commit(parts=set(target), backup=bool(backup), touch_meta=bool(touch_meta))
        self.notify_dirty()
        return True

    def save_dirty_cmd(self, *, backup: Optional[bool] = None, touch_meta: bool = True) -> bool:
        parts = self.dirty_parts()
        if not parts:
            return False

        if backup is None:
            try:
                backup = bool(getattr(self.ctx.base.io, "backup_on_save", True))
            except Exception:
                backup = True

        self.uow.commit(parts=set(parts), backup=bool(backup), touch_meta=bool(touch_meta))
        self.notify_dirty()
        return True

    def rollback_cmd(self) -> None:
        self.uow.rollback()
        self.notify_dirty()

    # ---------- dirty broadcast ----------
    def notify_dirty(self) -> None:
        parts = sorted(list(self.uow.dirty_parts()))
        self.bus.post_payload(
            EventType.DIRTY_STATE_CHANGED,
            DirtyStateChangedPayload(dirty=bool(self.uow.is_dirty()), parts=parts),
        )

    def _repair_ids_and_persist(self) -> None:
        ctx = self.ctx
        changed_parts: Set[str] = set()

        # ---- skills ----
        seen: Set[str] = set()
        for s in ctx.skills.skills:
            if (not s.id) or (s.id in seen):
                s.id = ctx.idgen.next_id()
                changed_parts.add("skills")
            seen.add(s.id)

        # ---- points ----
        seen_p: Set[str] = set()
        for p in ctx.points.points:
            if (not p.id) or (p.id in seen_p):
                p.id = ctx.idgen.next_id()
                changed_parts.add("points")
            seen_p.add(p.id)

        if not changed_parts:
            return

        try:
            backup = bool(getattr(ctx.base.io, "backup_on_save", True))
        except Exception:
            backup = True

        try:
            self.uow.commit(parts=set(changed_parts), backup=backup, touch_meta=False)
            try:
                for part in changed_parts:
                    self.uow.clear_dirty(part)  # type: ignore[arg-type]
            except Exception:
                pass
        except Exception as e:
            for part in changed_parts:
                try:
                    self.uow.mark_dirty(part)  # type: ignore[arg-type]
                except Exception:
                    pass
            self.bus.post_payload(EventType.ERROR, ErrorPayload(msg="数据修复保存失败", detail=str(e)))