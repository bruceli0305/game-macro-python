# core/app/services/points_service.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from core.app.session import ProfileSession
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

    tolerance: int

    captured_at: str
    sample_mode: str
    sample_radius: int

    note: str


class PointsService:
    """
    取色点位配置编辑服务：
    - 通过 ProfileSession 管理脏状态与提交
    - autosave 失败通过 notify_error 回调（由 UI 注入）
    """

    def __init__(
        self,
        *,
        session: ProfileSession,
        notify_dirty: Optional[Callable[[], None]] = None,
        notify_error: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        self._session = session
        self._notify_dirty = notify_dirty or (lambda: None)
        self._notify_error = notify_error or (lambda _m, _d="": None)

    @property
    def ctx(self):
        return self._session.ctx

    @property
    def profile(self):
        return self._session.profile

    def find(self, pid: str) -> Optional[Point]:
        for p in self.profile.points.points:
            if p.id == pid:
                return p
        return None

    def mark_dirty(self) -> None:
        self._session.mark_dirty("points")

    def _apply_patch_to_point(self, p: Point, patch: PointFormPatch) -> None:
        p.name = (patch.name or "").strip()
        p.monitor = (patch.monitor or "primary").strip() or "primary"
        p.vx = clamp_int(int(patch.vx), -10**9, 10**9)
        p.vy = clamp_int(int(patch.vy), -10**9, 10**9)

        r = clamp_int(int(patch.r), 0, 255)
        g = clamp_int(int(patch.g), 0, 255)
        b = clamp_int(int(patch.b), 0, 255)
        p.color = ColorRGB(r=r, g=g, b=b)

        p.tolerance = clamp_int(int(patch.tolerance), 0, 255)

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
            saved = self._maybe_autosave()
            self._notify_dirty()

        return (True, bool(saved))

    def apply_pick_cmd(
        self,
        pid: str,
        *,
        vx: int,
        vy: int,
        monitor: str,
        r: int,
        g: int,
        b: int,
    ) -> tuple[bool, bool]:
        p = self.find(pid)
        if p is None:
            return (False, False)

        p.vx = int(vx)
        p.vy = int(vy)
        if monitor:
            p.monitor = str(monitor)
        p.color = ColorRGB(r=int(r), g=int(g), b=int(b))
        p.captured_at = now_iso_utc()

        self.mark_dirty()
        self._notify_dirty()

        saved = self._maybe_autosave()
        self._notify_dirty()
        return (True, bool(saved))

    # ---------- helpers ----------

    def create_point(self, *, name: str = "新点位") -> Point:
        pid = self.ctx.idgen.next_id()
        p = Point(
            id=pid,
            name=name,
            monitor="primary",
            vx=0,
            vy=0,
            color=ColorRGB(0, 0, 0),
            tolerance=0,
            captured_at=now_iso_utc(),
        )
        p.sample.mode = "single"
        p.sample.radius = 0
        self.profile.points.points.append(p)
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
        self.profile.points.points.append(clone)
        self.mark_dirty()
        return clone

    def delete_point(self, pid: str) -> bool:
        before = len(self.profile.points.points)
        self.profile.points.points = [x for x in self.profile.points.points if x.id != pid]
        after = len(self.profile.points.points)
        if after != before:
            self.mark_dirty()
            return True
        return False

    # ---------- autosave ----------

    def _maybe_autosave(self) -> bool:
        try:
            auto = bool(getattr(self.profile.base.io, "auto_save", False))
        except Exception:
            auto = False
        if not auto:
            return False

        try:
            backup = bool(getattr(self.profile.base.io, "backup_on_save", True))
        except Exception:
            backup = True

        try:
            self._session.commit(parts={"points"}, backup=backup, touch_meta=False)
            return True
        except Exception as e:
            self._notify_error("自动保存失败", str(e))
            return False

    # ---------- cmd API ----------

    def create_cmd(self, *, name: str = "新点位") -> Point:
        p = self.create_point(name=name)
        self._notify_dirty()
        _ = self._maybe_autosave()
        self._notify_dirty()
        return p

    def clone_cmd(self, src_id: str) -> Optional[Point]:
        clone = self.clone_point(src_id)
        if clone is None:
            return None
        self._notify_dirty()
        _ = self._maybe_autosave()
        self._notify_dirty()
        return clone

    def delete_cmd(self, pid: str) -> bool:
        ok = self.delete_point(pid)
        if not ok:
            return False
        self._notify_dirty()
        _ = self._maybe_autosave()
        self._notify_dirty()
        return True

    def save_cmd(self, *, backup: Optional[bool] = None) -> None:
        self._session.commit(parts={"points"}, backup=backup, touch_meta=True)
        self._notify_dirty()

    def reload_cmd(self) -> None:
        """
        从 profile.json 重新加载 points 部分。
        """
        try:
            self._session.reload_parts({"points"})
        except Exception:
            pass
        self._notify_dirty()