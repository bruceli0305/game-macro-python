from __future__ import annotations

from typing import Callable, Optional

from core.app.uow import ProfileUnitOfWork
from core.event_bus import EventBus
from core.event_types import EventType
from core.models.skill import Skill, ColorRGB


class SkillsService:
    """
    Two layers of API:
    - Pure mutation methods: create_skill / clone_skill / delete_skill (no events)
    - Command methods: create_skill_cmd / clone_skill_cmd / delete_skill_cmd
      (publish RECORD_UPDATED/RECORD_DELETED + optional auto-save + notify_dirty)
    """

    def __init__(
        self,
        *,
        uow: ProfileUnitOfWork,
        bus: Optional[EventBus] = None,
        notify_dirty: Optional[Callable[[], None]] = None,
    ) -> None:
        self._uow = uow
        self._bus = bus
        self._notify_dirty = notify_dirty or (lambda: None)

    @property
    def ctx(self):
        return self._uow.ctx

    def find(self, sid: str) -> Optional[Skill]:
        for s in self.ctx.skills.skills:
            if s.id == sid:
                return s
        return None

    def mark_dirty(self) -> None:
        self._uow.mark_dirty("skills")

    # ---------------- pure mutation CRUD (no events) ----------------
    def create_skill(self, *, name: str = "新技能") -> Skill:
        sid = self.ctx.idgen.next_id()
        s = Skill(id=sid, name=name, enabled=True)
        s.pixel.monitor = "primary"
        s.pixel.vx = 0
        s.pixel.vy = 0
        self.ctx.skills.skills.append(s)
        self.mark_dirty()
        return s

    def clone_skill(self, src_id: str) -> Optional[Skill]:
        src = self.find(src_id)
        if src is None:
            return None
        new_id = self.ctx.idgen.next_id()
        clone = Skill.from_dict(src.to_dict())
        clone.id = new_id
        clone.name = f"{src.name} (副本)"
        self.ctx.skills.skills.append(clone)
        self.mark_dirty()
        return clone

    def delete_skill(self, sid: str) -> bool:
        before = len(self.ctx.skills.skills)
        self.ctx.skills.skills = [x for x in self.ctx.skills.skills if x.id != sid]
        after = len(self.ctx.skills.skills)
        if after != before:
            self.mark_dirty()
            return True
        return False

    # ---------------- save ----------------
    def save(self, *, backup: Optional[bool] = None) -> None:
        self._uow.commit(parts={"skills"}, backup=backup)

    # ---------------- pick apply (no events; orchestrator publishes) ----------------
    def apply_pick(self, sid: str, *, vx: int, vy: int, monitor: str, r: int, g: int, b: int) -> bool:
        s = self.find(sid)
        if s is None:
            return False
        s.pixel.vx = int(vx)
        s.pixel.vy = int(vy)
        if monitor:
            s.pixel.monitor = str(monitor)
        s.pixel.color = ColorRGB(r=int(r), g=int(g), b=int(b))
        self.mark_dirty()
        return True

    # ---------------- command CRUD (events + autosave + notify) ----------------
    def _maybe_autosave(self) -> bool:
        try:
            auto = bool(getattr(self.ctx.base.io, "auto_save", False))
        except Exception:
            auto = False
        if not auto:
            return False
        try:
            backup = bool(getattr(self.ctx.base.io, "backup_on_save", True))
        except Exception:
            backup = True
        self._uow.commit(parts={"skills"}, backup=backup)
        return True

    def create_skill_cmd(self, *, name: str = "新技能") -> Skill:
        s = self.create_skill(name=name)
        self._notify_dirty()

        saved = False
        try:
            saved = self._maybe_autosave()
        finally:
            self._notify_dirty()

        if self._bus is not None:
            self._bus.post(EventType.RECORD_UPDATED, record_type="skill_pixel", id=s.id, source="crud_add", saved=bool(saved))
        return s

    def clone_skill_cmd(self, src_id: str) -> Optional[Skill]:
        clone = self.clone_skill(src_id)
        if clone is None:
            return None

        self._notify_dirty()
        saved = False
        try:
            saved = self._maybe_autosave()
        finally:
            self._notify_dirty()

        if self._bus is not None:
            self._bus.post(EventType.RECORD_UPDATED, record_type="skill_pixel", id=clone.id, source="crud_duplicate", saved=bool(saved))
        return clone

    def delete_skill_cmd(self, sid: str) -> bool:
        ok = self.delete_skill(sid)
        if not ok:
            return False

        self._notify_dirty()
        saved = False
        try:
            saved = self._maybe_autosave()
        finally:
            self._notify_dirty()

        if self._bus is not None:
            self._bus.post(EventType.RECORD_DELETED, record_type="skill_pixel", id=sid, source="crud_delete", saved=bool(saved))
        return True