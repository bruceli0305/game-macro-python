from __future__ import annotations

from typing import Optional

from core.app.uow import ProfileUnitOfWork
from core.models.skill import Skill, ColorRGB


class SkillsService:
    def __init__(self, uow: ProfileUnitOfWork) -> None:
        self._uow = uow

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

    # ---- CRUD ----
    def create_skill(self, *, name: str = "新技能") -> Skill:
        sid = self.ctx.idgen.next_id()
        s = Skill(id=sid, name=name, enabled=True)
        # keep safe defaults
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

    def save(self, *, backup: Optional[bool] = None) -> None:
        self._uow.commit(parts={"skills"}, backup=backup)

    # ---- pick apply ----
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