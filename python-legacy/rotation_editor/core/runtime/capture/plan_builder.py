from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from core.profiles import ProfileContext
from core.pick.capture import ScreenCapture
from core.pick.scanner import MonitorCapturePlan, CapturePlan

from rotation_editor.ast import ProbeRequirements


@dataclass(frozen=True)
class ProbeMeta:
    monitor: str
    vx: int
    vy: int
    radius: int


@dataclass(frozen=True)
class PlanBuildResult:
    plan: CapturePlan
    probes_by_monitor: Dict[str, List[ProbeMeta]]


def _norm_monitor(monitor: str) -> str:
    mk = (monitor or "primary").strip().lower()
    return mk or "primary"


def _radius_from_sample(obj) -> int:
    try:
        s = getattr(obj, "sample", None)
        r = int(getattr(s, "radius", 0) or 0) if s is not None else 0
    except Exception:
        r = 0
    return max(0, int(r))


def _add_probe(by_mon: Dict[str, List[ProbeMeta]], monitor: str, vx: int, vy: int, radius: int) -> None:
    mk = _norm_monitor(monitor)
    by_mon.setdefault(mk, []).append(
        ProbeMeta(monitor=mk, vx=int(vx), vy=int(vy), radius=int(max(0, radius)))
    )


class CapturePlanBuilder:
    """
    将 ProbeRequirements 转为 CapturePlan（ROI/full）。

    依赖来源：
    - probes.point_ids -> points 中的点位（vx/vy/monitor/sample.radius）
    - probes.skill_pixel_ids -> skills 中的 skill.pixel（vx/vy/monitor/sample.radius）
    - 可选：base.cast_bar(mode="bar") 的 point_id（确保施法条模式即便 expr 未引用也能抓到）

    ROI 规则沿用旧实现：
    - 计算包含所有 probe 的最小包围矩形
    - 若 ROI 面积占屏比 < roi_ratio_threshold -> mode="roi"
      否则 mode="full"
    """
    def __init__(self, *, roi_ratio_threshold: float = 0.4, include_profile_cast_bar: bool = True) -> None:
        self._roi_ratio_threshold = float(roi_ratio_threshold)
        self._include_profile_cast_bar = bool(include_profile_cast_bar)

    def build(
        self,
        *,
        ctx: ProfileContext,
        probes: ProbeRequirements,
        capture: Optional[ScreenCapture] = None,
    ) -> PlanBuildResult:
        sc = capture or ScreenCapture()

        by_mon: Dict[str, List[ProbeMeta]] = {}

        # --- 索引 points / skills ---
        points_by_id = {p.id: p for p in (getattr(ctx.points, "points", []) or []) if getattr(p, "id", "")}
        skills_by_id = {s.id: s for s in (getattr(ctx.skills, "skills", []) or []) if getattr(s, "id", "")}

        # --- points probes ---
        for pid in sorted(set(probes.point_ids or set())):
            p = points_by_id.get(pid)
            if p is None:
                continue
            mon = getattr(p, "monitor", None) or "primary"
            vx = int(getattr(p, "vx", 0))
            vy = int(getattr(p, "vy", 0))
            rad = _radius_from_sample(p)
            _add_probe(by_mon, mon, vx, vy, rad)

        # --- skill pixel probes ---
        for sid in sorted(set(probes.skill_pixel_ids or set())):
            s = skills_by_id.get(sid)
            if s is None:
                continue
            pix = getattr(s, "pixel", None)
            if pix is None:
                continue
            mon = getattr(pix, "monitor", None) or "primary"
            vx = int(getattr(pix, "vx", 0))
            vy = int(getattr(pix, "vy", 0))
            rad = _radius_from_sample(pix)
            _add_probe(by_mon, mon, vx, vy, rad)

        # --- include base.cast_bar point (bar mode) ---
        if self._include_profile_cast_bar:
            try:
                cb = getattr(ctx.base, "cast_bar", None)
                mode = (getattr(cb, "mode", "timer") or "timer").strip().lower() if cb is not None else "timer"
                pid = (getattr(cb, "point_id", "") or "").strip() if cb is not None else ""
                if mode == "bar" and pid:
                    p = points_by_id.get(pid)
                    if p is not None:
                        mon = getattr(p, "monitor", None) or "primary"
                        vx = int(getattr(p, "vx", 0))
                        vy = int(getattr(p, "vy", 0))
                        rad = _radius_from_sample(p)
                        _add_probe(by_mon, mon, vx, vy, rad)
            except Exception:
                pass

        plans: Dict[str, MonitorCapturePlan] = {}

        for mk, metas in by_mon.items():
            rect = sc.get_monitor_rect(mk)
            W = int(getattr(rect, "width", 0) or 0)
            H = int(getattr(rect, "height", 0) or 0)
            if W <= 0 or H <= 0:
                continue
            if not metas:
                continue

            xs: List[int] = []
            ys: List[int] = []
            for m in metas:
                r = max(0, int(m.radius))
                xs.append(int(m.vx) - r)
                xs.append(int(m.vx) + r)
                ys.append(int(m.vy) - r)
                ys.append(int(m.vy) + r)

            roi_left = max(int(getattr(rect, "left", 0) or 0), min(xs))
            roi_top = max(int(getattr(rect, "top", 0) or 0), min(ys))
            roi_right = min(int(getattr(rect, "right", 0) or 0), max(xs) + 1)
            roi_bottom = min(int(getattr(rect, "bottom", 0) or 0), max(ys) + 1)

            roi_w = roi_right - roi_left
            roi_h = roi_bottom - roi_top
            if roi_w <= 0 or roi_h <= 0:
                continue

            ratio = (roi_w * roi_h) / float(max(1, W * H))
            if ratio < float(self._roi_ratio_threshold):
                mode = "roi"
            else:
                mode = "full"
                roi_left = int(getattr(rect, "left", 0) or 0)
                roi_top = int(getattr(rect, "top", 0) or 0)
                roi_w = int(getattr(rect, "width", 0) or 0)
                roi_h = int(getattr(rect, "height", 0) or 0)

            plans[mk] = MonitorCapturePlan(
                monitor=mk,
                mode=mode,
                roi_left=int(roi_left),
                roi_top=int(roi_top),
                roi_width=int(roi_w),
                roi_height=int(roi_h),
            )

        return PlanBuildResult(plan=CapturePlan(plans=plans), probes_by_monitor=by_mon)