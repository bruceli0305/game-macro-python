from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from core.profiles import ProfileContext
from core.pick.capture import ScreenCapture
from core.pick.scanner import MonitorCapturePlan, CapturePlan

from rotation_editor.core.models import RotationPreset, Track, GatewayNode


@dataclass(frozen=True)
class ProbeMeta:
    monitor: str
    vx: int
    vy: int
    radius: int


def collect_probes(ctx: ProfileContext, preset: RotationPreset) -> Dict[str, List[ProbeMeta]]:
    """
    Groups-only：
    - cast_bar（若启用 bar 且 point_id 有效）：加入该点位
    - 仅扫描被网关引用到的 conditions（避免 ROI 过大）：
        kind="groups" expr.groups[].atoms[]：
            - pixel_point.point_id -> 点位
            - pixel_skill.skill_id -> 技能 pixel
    """
    by_mon: Dict[str, List[ProbeMeta]] = {}

    def _add(monitor: str, vx: int, vy: int, radius: int) -> None:
        mk = (monitor or "primary").strip().lower() or "primary"
        by_mon.setdefault(mk, []).append(
            ProbeMeta(monitor=mk, vx=int(vx), vy=int(vy), radius=int(max(0, radius)))
        )

    points_by_id = {p.id: p for p in getattr(ctx.points, "points", []) or [] if getattr(p, "id", "")}
    skills_by_id = {s.id: s for s in getattr(ctx.skills, "skills", []) or [] if getattr(s, "id", "")}

    # 0) cast_bar 点位
    try:
        cb = getattr(ctx.base, "cast_bar", None)
        mode = (getattr(cb, "mode", "timer") or "timer").strip().lower() if cb is not None else "timer"
        pid = (getattr(cb, "point_id", "") or "").strip() if cb is not None else ""
        if mode == "bar" and pid:
            p = points_by_id.get(pid)
            if p is not None:
                mon = p.monitor or "primary"
                vx = int(getattr(p, "vx", 0))
                vy = int(getattr(p, "vy", 0))
                rad = int(getattr(getattr(p, "sample", None), "radius", 0) or 0)
                _add(mon, vx, vy, rad)
    except Exception:
        pass

    # 1) 找出被网关引用的 condition_id
    used_cond_ids: set[str] = set()

    def scan_track_for_conditions(track: Track) -> None:
        for n in track.nodes or []:
            if isinstance(n, GatewayNode):
                cid = (getattr(n, "condition_id", "") or "").strip()
                if cid:
                    used_cond_ids.add(cid)

    for t in preset.global_tracks or []:
        scan_track_for_conditions(t)

    for m in preset.modes or []:
        for t in m.tracks or []:
            scan_track_for_conditions(t)

    if not used_cond_ids:
        return by_mon

    cond_by_id = {c.id: c for c in preset.conditions or [] if getattr(c, "id", "")}

    # 2) 扫描 groups atoms
    for cid in used_cond_ids:
        c = cond_by_id.get(cid)
        if c is None:
            continue
        if (c.kind or "").strip().lower() != "groups":
            continue
        expr = c.expr or {}
        if not isinstance(expr, dict):
            continue
        groups = expr.get("groups", [])
        if not isinstance(groups, list):
            continue

        for g in groups:
            if not isinstance(g, dict):
                continue
            atoms = g.get("atoms", [])
            if not isinstance(atoms, list):
                continue

            for a in atoms:
                if not isinstance(a, dict):
                    continue
                t = (a.get("type") or "").strip().lower()

                if t == "pixel_point":
                    pid = (a.get("point_id") or "").strip()
                    p = points_by_id.get(pid)
                    if p is not None:
                        mon = p.monitor or "primary"
                        vx = int(getattr(p, "vx", 0))
                        vy = int(getattr(p, "vy", 0))
                        rad = int(getattr(getattr(p, "sample", None), "radius", 0) or 0)
                        _add(mon, vx, vy, rad)

                elif t == "pixel_skill":
                    sid = (a.get("skill_id") or "").strip()
                    s = skills_by_id.get(sid)
                    if s is not None:
                        pix = getattr(s, "pixel", None)
                        if pix is not None:
                            mon = pix.monitor or "primary"
                            vx = int(getattr(pix, "vx", 0))
                            vy = int(getattr(pix, "vy", 0))
                            rad = int(getattr(getattr(pix, "sample", None), "radius", 0) or 0)
                            _add(mon, vx, vy, rad)

                # skill_cast_ge 不采样像素

    return by_mon


def build_capture_plan(
    ctx: ProfileContext,
    preset: RotationPreset,
    *,
    capture: Optional[ScreenCapture] = None,
    roi_ratio_threshold: float = 0.4,
) -> CapturePlan:
    """
    基于 ProfileContext + RotationPreset 构建 CapturePlan。

    关键：允许传入 capture 实例，避免在引擎循环中反复 new ScreenCapture。
    """
    sc = capture or ScreenCapture()
    probes_by_mon = collect_probes(ctx, preset)

    plans: Dict[str, MonitorCapturePlan] = {}

    for mk, metas in probes_by_mon.items():
        rect = sc.get_monitor_rect(mk)
        W = int(rect.width)
        H = int(rect.height)

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

        roi_left = max(int(rect.left), min(xs))
        roi_top = max(int(rect.top), min(ys))
        roi_right = min(int(rect.right), max(xs) + 1)
        roi_bottom = min(int(rect.bottom), max(ys) + 1)

        roi_w = roi_right - roi_left
        roi_h = roi_bottom - roi_top
        if roi_w <= 0 or roi_h <= 0:
            continue

        ratio = (roi_w * roi_h) / float(max(1, W * H))
        if ratio < float(roi_ratio_threshold):
            mode = "roi"
        else:
            mode = "full"
            roi_left = int(rect.left)
            roi_top = int(rect.top)
            roi_w = int(rect.width)
            roi_h = int(rect.height)

        plans[mk] = MonitorCapturePlan(
            monitor=mk,
            mode=mode,
            roi_left=roi_left,
            roi_top=roi_top,
            roi_width=roi_w,
            roi_height=roi_h,
        )

    return CapturePlan(plans=plans)