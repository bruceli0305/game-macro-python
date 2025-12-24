from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from core.event_bus import EventBus
from core.event_types import EventType
from core.io.json_store import now_iso_utc
from core.models.common import clamp_int
from core.models.point import Point
from core.models.skill import ColorRGB
from core.pick.capture import ScreenCapture
from core.profiles import ProfileContext


@dataclass(frozen=True)
class PointRow:
    id: str
    values: tuple


class PointsService:
    """
    Points application service (phase-1):
    - owns coordinate conversion logic
    - owns default record creation / cloning
    - owns persistence + error reporting
    - owns pick payload application
    """

    def __init__(self, *, ctx_provider: Callable[[], ProfileContext], bus: EventBus) -> None:
        self._ctx_provider = ctx_provider
        self._bus = bus
        self._cap = ScreenCapture()

    def close(self) -> None:
        try:
            self._cap.close()
        except Exception:
            pass

    def _ctx(self) -> ProfileContext:
        return self._ctx_provider()

    def make_new(self) -> Point:
        ctx = self._ctx()
        pid = ctx.idgen.next_id()
        try:
            vx, vy = self._cap.rel_to_abs(0, 0, "primary")
        except Exception:
            vx, vy = 0, 0

        p = Point(
            id=pid,
            name="新点位",
            monitor="primary",
            vx=int(vx),
            vy=int(vy),
            color=ColorRGB(0, 0, 0),
            captured_at=now_iso_utc(),
        )
        p.sample.mode = "single"
        p.sample.radius = 0
        return p

    def clone(self, record: Point) -> Point:
        ctx = self._ctx()
        new_id = ctx.idgen.next_id()
        clone = Point.from_dict(record.to_dict())
        clone.id = new_id
        clone.name = f"{record.name} (副本)"
        clone.captured_at = now_iso_utc()
        return clone

    def delete_by_id(self, rid: str) -> None:
        ctx = self._ctx()
        ctx.points.points = [x for x in ctx.points.points if x.id != rid]

    def save(self) -> bool:
        ctx = self._ctx()
        try:
            ctx.points_repo.save(ctx.points, backup=ctx.base.io.backup_on_save)
            return True
        except Exception as e:
            self._bus.post(EventType.ERROR, msg=f"保存 points.json 失败: {e}")
            return False

    def row_values(self, p: Point) -> tuple:
        pid = p.id or ""
        short = pid[-6:] if len(pid) >= 6 else pid

        mon = p.monitor or "primary"
        try:
            rx, ry = self._cap.abs_to_rel(int(p.vx), int(p.vy), mon)
        except Exception:
            rx, ry = int(p.vx), int(p.vy)

        pos = f"({rx},{ry})"
        hx = f"#{clamp_int(p.color.r,0,255):02X}{clamp_int(p.color.g,0,255):02X}{clamp_int(p.color.b,0,255):02X}"
        return (p.name, short, mon, pos, hx, p.captured_at)

    def load_rel_xy(self, p: Point) -> tuple[int, int]:
        mon = p.monitor or "primary"
        try:
            rx, ry = self._cap.abs_to_rel(int(p.vx), int(p.vy), mon)
            return int(rx), int(ry)
        except Exception:
            return 0, 0

    def apply_form(
        self,
        p: Point,
        *,
        name: str,
        monitor: str,
        rel_x: int,
        rel_y: int,
        r: int,
        g: int,
        b: int,
        captured_at: str,
        sample_mode: str,
        sample_radius: int,
        note: str,
    ) -> None:
        p.name = name
        mon = (monitor or "primary").strip() or "primary"
        p.monitor = mon

        rel_x = clamp_int(int(rel_x), 0, 10**9)
        rel_y = clamp_int(int(rel_y), 0, 10**9)
        try:
            vx, vy = self._cap.rel_to_abs(rel_x, rel_y, mon)
        except Exception:
            vx, vy = rel_x, rel_y

        p.vx = clamp_int(int(vx), -10**9, 10**9)
        p.vy = clamp_int(int(vy), -10**9, 10**9)

        rr = clamp_int(int(r), 0, 255)
        gg = clamp_int(int(g), 0, 255)
        bb = clamp_int(int(b), 0, 255)
        p.color = ColorRGB(r=rr, g=gg, b=bb)

        p.captured_at = (captured_at or "").strip()
        p.sample.mode = (sample_mode or "single")
        p.sample.radius = clamp_int(int(sample_radius), 0, 50)

        p.note = note

    def apply_pick_payload(self, p: Point, payload: dict) -> None:
        if "vx" in payload and "vy" in payload:
            vx = int(payload.get("vx", 0))
            vy = int(payload.get("vy", 0))
        else:
            vx = int(payload.get("abs_x", 0))
            vy = int(payload.get("abs_y", 0))

        mon = payload.get("monitor")
        if isinstance(mon, str) and mon:
            p.monitor = mon

        r = clamp_int(int(payload.get("r", 0)), 0, 255)
        g = clamp_int(int(payload.get("g", 0)), 0, 255)
        b = clamp_int(int(payload.get("b", 0)), 0, 255)

        p.vx = clamp_int(vx, -10**9, 10**9)
        p.vy = clamp_int(vy, -10**9, 10**9)
        p.color = ColorRGB(r=r, g=g, b=b)
        p.captured_at = now_iso_utc()

    def find_by_id(self, rid: str) -> Optional[Point]:
        for p in self._ctx().points.points:
            if p.id == rid:
                return p
        return None