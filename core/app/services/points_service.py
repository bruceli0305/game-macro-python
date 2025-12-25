from __future__ import annotations

from typing import Optional

from core.app.uow import ProfileUnitOfWork
from core.io.json_store import now_iso_utc
from core.models.point import Point
from core.models.skill import ColorRGB


class PointsService:
    def __init__(self, uow: ProfileUnitOfWork) -> None:
        self._uow = uow

    @property
    def ctx(self):
        return self._uow.ctx

    def find(self, pid: str) -> Optional[Point]:
        for p in self.ctx.points.points:
            if p.id == pid:
                return p
        return None

    def mark_dirty(self) -> None:
        self._uow.mark_dirty("points")

    # ---- CRUD ----
    def create_point(self, *, name: str = "新点位") -> Point:
        pid = self.ctx.idgen.next_id()
        p = Point(
            id=pid,
            name=name,
            monitor="primary",
            vx=0,
            vy=0,
            color=ColorRGB(0, 0, 0),
            captured_at=now_iso_utc(),
        )
        p.sample.mode = "single"
        p.sample.radius = 0
        self.ctx.points.points.append(p)
        self.mark_dirty()
        return p

    def clone_point(self, src_id: str) -> Optional[Point]:
        src = self.find(src_id)
        if src is None:
            return None
        new_id = self.ctx.idgen.next_id()
        clone = Point.from_dict(src.to_dict())
        clone.id = new_id
        clone.name = f"{src.name} (副本)"
        clone.captured_at = now_iso_utc()
        self.ctx.points.points.append(clone)
        self.mark_dirty()
        return clone

    def delete_point(self, pid: str) -> bool:
        before = len(self.ctx.points.points)
        self.ctx.points.points = [x for x in self.ctx.points.points if x.id != pid]
        after = len(self.ctx.points.points)
        if after != before:
            self.mark_dirty()
            return True
        return False

    def save(self, *, backup: Optional[bool] = None) -> None:
        self._uow.commit(parts={"points"}, backup=backup)

    # ---- pick apply ----
    def apply_pick(self, pid: str, *, vx: int, vy: int, monitor: str, r: int, g: int, b: int) -> bool:
        p = self.find(pid)
        if p is None:
            return False
        p.vx = int(vx)
        p.vy = int(vy)
        if monitor:
            p.monitor = str(monitor)
        p.color = ColorRGB(r=int(r), g=int(g), b=int(b))
        p.captured_at = now_iso_utc()
        self.mark_dirty()
        return True