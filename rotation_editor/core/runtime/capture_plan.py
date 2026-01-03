from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from core.profiles import ProfileContext
from core.pick.capture import ScreenCapture
from core.pick.scanner import MonitorCapturePlan, CapturePlan

from rotation_editor.core.models import (
    RotationPreset,
    Condition,
    SkillNode,
    GatewayNode,
    SkillNode,
)


@dataclass(frozen=True)
class ProbeMeta:
    """
    静态采样点描述（用于构建 ROI 包围框）：
    - monitor: "primary" / "monitor_2" 等
    - vx/vy:   虚拟屏绝对坐标
    - radius:  采样半径（mean_square 时用，single 为 0）
    """
    monitor: str
    vx: int
    vy: int
    radius: int


def collect_probes(ctx: ProfileContext, preset: RotationPreset) -> Dict[str, List[ProbeMeta]]:
    """
    从 ProfileContext + RotationPreset 中收集所有“可能用到的”采样点，
    按 monitor 分组返回：monitor_key -> List[ProbeMeta]。

    来源：
    - 所有 Points（points.json）
    - 所有 Skills.pixel（skills.json）
    - 所有 Conditions.expr_tree_v1 中的 pixel_point / pixel_skill
      （通过 point_id / skill_id 回溯到上述两类）
    """
    by_mon: Dict[str, List[ProbeMeta]] = {}

    def _add(monitor: str, vx: int, vy: int, radius: int) -> None:
        mk = (monitor or "primary").strip().lower() or "primary"
        pm = ProbeMeta(monitor=mk, vx=int(vx), vy=int(vy), radius=int(max(0, radius)))
        by_mon.setdefault(mk, []).append(pm)

    # ---------- 1) 所有点位 ----------
    try:
        for p in getattr(ctx.points, "points", []) or []:
            mon = p.monitor or "primary"
            vx = int(getattr(p, "vx", 0))
            vy = int(getattr(p, "vy", 0))
            rad = int(getattr(getattr(p, "sample", None), "radius", 0) or 0)
            _add(mon, vx, vy, rad)
    except Exception:
        pass

    # ---------- 2) 所有技能像素 ----------
    try:
        for s in getattr(ctx.skills, "skills", []) or []:
            pix = getattr(s, "pixel", None)
            if pix is None:
                continue
            mon = pix.monitor or "primary"
            vx = int(getattr(pix, "vx", 0))
            vy = int(getattr(pix, "vy", 0))
            rad = int(getattr(getattr(pix, "sample", None), "radius", 0) or 0)
            _add(mon, vx, vy, rad)
    except Exception:
        pass

    # 为 condition 中的 pixel_point / pixel_skill 做一个 id -> 对象 的索引
    points_by_id = {p.id: p for p in getattr(ctx.points, "points", []) or [] if p.id}
    skills_by_id = {s.id: s for s in getattr(ctx.skills, "skills", []) or [] if s.id}

    # ---------- 3) Condition AST ----------
    def _scan_expr(node, *, cond_name: str) -> None:
        if not isinstance(node, dict):
            return
        t = (node.get("type") or "").strip().lower()
        if t in ("logic_and", "logic_or"):
            for ch in node.get("children", []) or []:
                _scan_expr(ch, cond_name=cond_name)
            return
        if t == "logic_not":
            ch = node.get("child")
            if isinstance(ch, dict):
                _scan_expr(ch, cond_name=cond_name)
            return
        if t == "pixel_point":
            pid = (node.get("point_id") or "").strip()
            p = points_by_id.get(pid)
            if p is not None:
                mon = p.monitor or "primary"
                vx = int(getattr(p, "vx", 0))
                vy = int(getattr(p, "vy", 0))
                rad = int(getattr(getattr(p, "sample", None), "radius", 0) or 0)
                _add(mon, vx, vy, rad)
            return
        if t == "pixel_skill":
            sid = (node.get("skill_id") or "").strip()
            s = skills_by_id.get(sid)
            if s is not None:
                pix = getattr(s, "pixel", None)
                if pix is not None:
                    mon = pix.monitor or "primary"
                    vx = int(getattr(pix, "vx", 0))
                    vy = int(getattr(pix, "vy", 0))
                    rad = int(getattr(getattr(pix, "sample", None), "radius", 0) or 0)
                    _add(mon, vx, vy, rad)
            return
        # skill_cast_ge 等与像素无关，这里先忽略
        return

    try:
        for c in preset.conditions or []:
            kind = (c.kind or "").strip().lower()
            if kind == "expr_tree_v1" and isinstance(c.expr, dict):
                _scan_expr(c.expr, cond_name=c.name or "")
    except Exception:
        pass

    return by_mon


def build_capture_plan(
    ctx: ProfileContext,
    preset: RotationPreset,
    *,
    roi_ratio_threshold: float = 0.4,
) -> CapturePlan:
    """
    基于 ProfileContext + RotationPreset 构建 CapturePlan（ROI + 整屏混合）：

    - 先调用 collect_probes 按 monitor 收集所有 ProbeMeta。
    - 对每个 monitor：
        * 根据 ProbeMeta 计算最小包围矩形 ROI（考虑半径）
        * 与物理屏幕矩形求交集
        * 计算 ROI 面积 / 屏幕面积，比值 < roi_ratio_threshold 时使用 ROI，否则使用整屏。
    - 返回的 CapturePlan 只包含“有采样点”的 monitor 计划。
    """
    sc = ScreenCapture()
    probes_by_mon = collect_probes(ctx, preset)

    plans: Dict[str, MonitorCapturePlan] = {}

    for mk, metas in probes_by_mon.items():
        rect = sc.get_monitor_rect(mk)
        W = int(rect.width)
        H = int(rect.height)

        if W <= 0 or H <= 0:
            continue
        if not metas:
            # 没有采样点：当前版本可以选择不截取这个屏幕
            continue

        # 计算最小包围矩形（考虑半径）
        xs: List[int] = []
        ys: List[int] = []
        for m in metas:
            r = max(0, int(m.radius))
            xs.append(int(m.vx) - r)
            xs.append(int(m.vx) + r)
            ys.append(int(m.vy) - r)
            ys.append(int(m.vy) + r)

        if not xs or not ys:
            continue

        roi_left = max(int(rect.left), min(xs))
        roi_top = max(int(rect.top), min(ys))
        roi_right = min(int(rect.right), max(xs) + 1)
        roi_bottom = min(int(rect.bottom), max(ys) + 1)

        roi_w = roi_right - roi_left
        roi_h = roi_bottom - roi_top
        if roi_w <= 0 or roi_h <= 0:
            continue

        # 面积比，决定 ROI vs 整屏
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