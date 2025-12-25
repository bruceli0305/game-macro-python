from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from core.app.uow import ProfileUnitOfWork
from core.event_bus import EventBus
from core.event_types import EventType
from core.models.common import clamp_int
from core.models.skill import Skill, ColorRGB


@dataclass(frozen=True)
class SkillFormPatch:
    name: str
    enabled: bool
    trigger_key: str
    readbar_ms: int

    monitor: str
    vx: int
    vy: int

    r: int
    g: int
    b: int

    tolerance: int
    sample_mode: str
    sample_radius: int

    note: str


class SkillsService:
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

    # -------- patch apply (idempotent) --------
    def _apply_patch_to_skill(self, s: Skill, patch: SkillFormPatch) -> None:
        s.name = (patch.name or "").strip()
        s.enabled = bool(patch.enabled)

        s.trigger.type = "key"
        s.trigger.key = (patch.trigger_key or "").strip()
        s.cast.readbar_ms = clamp_int(int(patch.readbar_ms), 0, 10**9)

        s.pixel.monitor = (patch.monitor or "primary").strip() or "primary"
        s.pixel.vx = clamp_int(int(patch.vx), -10**9, 10**9)
        s.pixel.vy = clamp_int(int(patch.vy), -10**9, 10**9)

        r = clamp_int(int(patch.r), 0, 255)
        g = clamp_int(int(patch.g), 0, 255)
        b = clamp_int(int(patch.b), 0, 255)
        s.pixel.color = ColorRGB(r=r, g=g, b=b)

        s.pixel.tolerance = clamp_int(int(patch.tolerance), 0, 255)
        s.pixel.sample.mode = (patch.sample_mode or "single").strip() or "single"
        s.pixel.sample.radius = clamp_int(int(patch.sample_radius), 0, 50)

        s.note = patch.note or ""

    def apply_form_patch(self, sid: str, patch: SkillFormPatch, *, auto_save: bool) -> tuple[bool, bool]:
        """
        Returns (changed, saved).
        - changed=False -> no-op, do not mark dirty
        - saved=True only when auto_save triggered and commit succeeded
        """
        s = self.find(sid)
        if s is None:
            return (False, False)

        before = s.to_dict()
        tmp = Skill.from_dict(before)
        self._apply_patch_to_skill(tmp, patch)
        after = tmp.to_dict()

        if after == before:
            return (False, False)

        # apply for real
        self._apply_patch_to_skill(s, patch)
        self.mark_dirty()
        self._notify_dirty()

        saved = False
        if auto_save:
            try:
                if bool(getattr(self.ctx.base.io, "auto_save", False)):
                    backup = bool(getattr(self.ctx.base.io, "backup_on_save", True))
                    self._uow.commit(parts={"skills"}, backup=backup, touch_meta=False)
                    saved = True
                    self._notify_dirty()
            except Exception:
                saved = False

        return (True, saved)

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

    # ---------------- manual save ----------------
    def save(self, *, backup: Optional[bool] = None) -> None:
        self._uow.commit(parts={"skills"}, backup=backup, touch_meta=True)

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
        self._uow.commit(parts={"skills"}, backup=backup, touch_meta=False)
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