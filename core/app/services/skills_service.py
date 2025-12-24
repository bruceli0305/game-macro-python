from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from core.event_bus import EventBus
from core.event_types import EventType
from core.models.common import clamp_int
from core.models.skill import Skill, ColorRGB
from core.pick.capture import ScreenCapture
from core.profiles import ProfileContext


@dataclass(frozen=True)
class SkillRow:
    id: str
    values: tuple


class SkillsService:
    """
    Skills application service (phase-1):
    - owns coordinate conversion logic (rel <-> vx/vy)
    - owns default record creation / cloning
    - owns persistence call + error reporting
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

    # -------- CRUD helpers (used by UI pages) --------

    def make_new(self) -> Skill:
        ctx = self._ctx()
        sid = ctx.idgen.next_id()
        s = Skill(id=sid, name="新技能", enabled=True)

        # default pos: rel(0,0) on primary -> abs(vx/vy)
        try:
            vx, vy = self._cap.rel_to_abs(0, 0, "primary")
        except Exception:
            vx, vy = 0, 0
        s.pixel.monitor = "primary"
        s.pixel.vx = int(vx)
        s.pixel.vy = int(vy)
        return s

    def clone(self, record: Skill) -> Skill:
        ctx = self._ctx()
        new_id = ctx.idgen.next_id()
        clone = Skill.from_dict(record.to_dict())
        clone.id = new_id
        clone.name = f"{record.name} (副本)"
        return clone

    def delete_by_id(self, rid: str) -> None:
        ctx = self._ctx()
        ctx.skills.skills = [x for x in ctx.skills.skills if x.id != rid]

    def save(self) -> bool:
        ctx = self._ctx()
        try:
            ctx.skills_repo.save(ctx.skills, backup=ctx.base.io.backup_on_save)
            return True
        except Exception as e:
            self._bus.post(EventType.ERROR, msg=f"保存 skills.json 失败: {e}")
            return False

    # -------- mapping (model <-> ui) --------

    def row_values(self, s: Skill) -> tuple:
        sid = s.id or ""
        short = sid[-6:] if len(sid) >= 6 else sid

        mon = s.pixel.monitor or "primary"
        try:
            rx, ry = self._cap.abs_to_rel(int(s.pixel.vx), int(s.pixel.vy), mon)
        except Exception:
            rx, ry = int(s.pixel.vx), int(s.pixel.vy)

        pos = f"({rx},{ry})"
        hx = f"#{clamp_int(s.pixel.color.r,0,255):02X}{clamp_int(s.pixel.color.g,0,255):02X}{clamp_int(s.pixel.color.b,0,255):02X}"
        return (
            "是" if s.enabled else "否",
            s.name,
            short,
            s.trigger.key,
            pos,
            hx,
            str(s.pixel.tolerance),
            str(s.cast.readbar_ms),
        )

    def load_rel_xy(self, s: Skill) -> tuple[int, int]:
        mon = s.pixel.monitor or "primary"
        try:
            rx, ry = self._cap.abs_to_rel(int(s.pixel.vx), int(s.pixel.vy), mon)
            return int(rx), int(ry)
        except Exception:
            return 0, 0

    def apply_form(
        self,
        s: Skill,
        *,
        name: str,
        enabled: bool,
        trigger_key: str,
        readbar_ms: int,
        monitor: str,
        rel_x: int,
        rel_y: int,
        r: int,
        g: int,
        b: int,
        tolerance: int,
        sample_mode: str,
        sample_radius: int,
        note: str,
    ) -> None:
        s.name = name
        s.enabled = bool(enabled)
        s.trigger.type = "key"
        s.trigger.key = trigger_key
        s.cast.readbar_ms = clamp_int(int(readbar_ms), 0, 10**9)

        mon = (monitor or "primary").strip() or "primary"
        s.pixel.monitor = mon

        rel_x = clamp_int(int(rel_x), 0, 10**9)
        rel_y = clamp_int(int(rel_y), 0, 10**9)
        try:
            vx, vy = self._cap.rel_to_abs(rel_x, rel_y, mon)
        except Exception:
            vx, vy = rel_x, rel_y

        s.pixel.vx = clamp_int(int(vx), -10**9, 10**9)
        s.pixel.vy = clamp_int(int(vy), -10**9, 10**9)

        rr = clamp_int(int(r), 0, 255)
        gg = clamp_int(int(g), 0, 255)
        bb = clamp_int(int(b), 0, 255)
        s.pixel.color = ColorRGB(r=rr, g=gg, b=bb)

        s.pixel.tolerance = clamp_int(int(tolerance), 0, 255)
        s.pixel.sample.mode = (sample_mode or "single")
        s.pixel.sample.radius = clamp_int(int(sample_radius), 0, 50)

        s.note = note

    def apply_pick_payload(self, s: Skill, payload: dict) -> None:
        # prefer vx/vy
        if "vx" in payload and "vy" in payload:
            vx = int(payload.get("vx", 0))
            vy = int(payload.get("vy", 0))
        else:
            vx = int(payload.get("abs_x", 0))
            vy = int(payload.get("abs_y", 0))

        mon = payload.get("monitor")
        if isinstance(mon, str) and mon:
            s.pixel.monitor = mon

        r = clamp_int(int(payload.get("r", 0)), 0, 255)
        g = clamp_int(int(payload.get("g", 0)), 0, 255)
        b = clamp_int(int(payload.get("b", 0)), 0, 255)

        s.pixel.vx = clamp_int(vx, -10**9, 10**9)
        s.pixel.vy = clamp_int(vy, -10**9, 10**9)
        s.pixel.color = ColorRGB(r=r, g=g, b=b)

    def find_by_id(self, rid: str) -> Optional[Skill]:
        for s in self._ctx().skills.skills:
            if s.id == rid:
                return s
        return None