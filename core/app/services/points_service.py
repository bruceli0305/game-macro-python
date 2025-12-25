from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from core.app.uow import ProfileUnitOfWork
from core.event_bus import EventBus
from core.event_types import EventType
from core.events.payloads import RecordUpdatedPayload, RecordDeletedPayload
from core.io.json_store import now_iso_utc
from core.models.common import clamp_int
from core.models.point import Point
from core.models.skill import ColorRGB


@dataclass(frozen=True)
class PointFormPatch:
    name: str
    monitor: str
    vx: int
    vy: int

    r: int
    g: int
    b: int

    captured_at: str
    sample_mode: str
    sample_radius: int

    note: str


class PointsService:
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

    def find(self, pid: str) -> Optional[Point]:
        for p in self.ctx.points.points:
            if p.id == pid:
                return p
        return None

    def mark_dirty(self) -> None:
        self._uow.mark_dirty("points")

    def _apply_patch_to_point(self, p: Point, patch: PointFormPatch) -> None:
        p.name = (patch.name or "").strip()
        p.monitor = (patch.monitor or "primary").strip() or "primary"
        p.vx = clamp_int(int(patch.vx), -10**9, 10**9)
        p.vy = clamp_int(int(patch.vy), -10**9, 10**9)

        r = clamp_int(int(patch.r), 0, 255)
        g = clamp_int(int(patch.g), 0, 255)
        b = clamp_int(int(patch.b), 0, 255)
        p.color = ColorRGB(r=r, g=g, b=b)

        p.captured_at = (patch.captured_at or "").strip()
        p.sample.mode = (patch.sample_mode or "single").strip() or "single"
        p.sample.radius = clamp_int(int(patch.sample_radius), 0, 50)

        p.note = patch.note or ""

    def apply_form_patch(self, pid: str, patch: PointFormPatch, *, auto_save: bool) -> tuple[bool, bool]:
        p = self.find(pid)
        if p is None:
            return (False, False)

        before = p.to_dict()
        tmp = Point.from_dict(before)
        self._apply_patch_to_point(tmp, patch)
        after = tmp.to_dict()

        if after == before:
            return (False, False)

        self._apply_patch_to_point(p, patch)
        self.mark_dirty()
        self._notify_dirty()

        saved = False
        if auto_save:
            try:
                if bool(getattr(self.ctx.base.io, "auto_save", False)):
                    backup = bool(getattr(self.ctx.base.io, "backup_on_save", True))
                    self._uow.commit(parts={"points"}, backup=backup, touch_meta=False)
                    saved = True
                    self._notify_dirty()
            except Exception:
                saved = False

        # Step 5: 变更后统一发事件，让 UI 刷新（不要由页面主动 update_tree_row）
        if self._bus is not None:
            self._bus.post_payload(
                EventType.RECORD_UPDATED,
                RecordUpdatedPayload(record_type="point", id=pid, source="form", saved=bool(saved)),
            )

        return (True, saved)
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
        self._uow.commit(parts={"points"}, backup=backup, touch_meta=True)

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
        self._uow.commit(parts={"points"}, backup=backup, touch_meta=False)
        return True

    def create_point_cmd(self, *, name: str = "新点位") -> Point:
        p = self.create_point(name=name)
        self._notify_dirty()

        saved = False
        try:
            saved = self._maybe_autosave()
        finally:
            self._notify_dirty()

        if self._bus is not None:
            self._bus.post_payload(
                EventType.RECORD_UPDATED,
                RecordUpdatedPayload(record_type="point", id=p.id, source="crud_add", saved=bool(saved)),
            )
        return p

    def clone_point_cmd(self, src_id: str) -> Optional[Point]:
        clone = self.clone_point(src_id)
        if clone is None:
            return None

        self._notify_dirty()
        saved = False
        try:
            saved = self._maybe_autosave()
        finally:
            self._notify_dirty()

        if self._bus is not None:
            self._bus.post_payload(
                EventType.RECORD_UPDATED,
                RecordUpdatedPayload(record_type="point", id=clone.id, source="crud_duplicate", saved=bool(saved)),
            )
        return clone

    def delete_point_cmd(self, pid: str) -> bool:
        ok = self.delete_point(pid)
        if not ok:
            return False

        self._notify_dirty()
        saved = False
        try:
            saved = self._maybe_autosave()
        finally:
            self._notify_dirty()

        if self._bus is not None:
            self._bus.post_payload(
                EventType.RECORD_DELETED,
                RecordDeletedPayload(record_type="point", id=pid, source="crud_delete", saved=bool(saved)),
            )
        return True