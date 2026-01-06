from __future__ import annotations

from dataclasses import dataclass, field
from typing import Set, Optional

from .nodes import (
    Expr,
    And,
    Or,
    Not,
    Const,
    PixelMatchPoint,
    PixelMatchSkill,
    CastBarChanged,
    SkillMetricGE,
)


@dataclass
class ProbeRequirements:
    """
    供 capture plan / 预抓取使用的静态依赖集合。

    - point_ids: 需要采样的点位（PixelMatchPoint / CastBarChanged）
    - skill_pixel_ids: 需要采样 skill.pixel 的技能（PixelMatchSkill）
    - skill_metric_ids: 需要读取技能指标的技能（SkillMetricGE，不需要抓屏）
    """
    point_ids: Set[str] = field(default_factory=set)
    skill_pixel_ids: Set[str] = field(default_factory=set)
    skill_metric_ids: Set[str] = field(default_factory=set)

    def merge(self, other: "ProbeRequirements") -> "ProbeRequirements":
        if other is None:
            return self
        self.point_ids |= set(other.point_ids or set())
        self.skill_pixel_ids |= set(other.skill_pixel_ids or set())
        self.skill_metric_ids |= set(other.skill_metric_ids or set())
        return self


def collect_probes_from_expr(expr: Optional[Expr]) -> ProbeRequirements:
    """
    从已解码/已构造的 Expr 对象提取 probes（避免必须走 compile_expr_json 才能拿 probes）。
    """
    out = ProbeRequirements()
    if expr is None:
        return out

    def walk(e: Expr) -> None:
        if isinstance(e, And) or isinstance(e, Or):
            for c in e.children:
                walk(c)
            return
        if isinstance(e, Not):
            walk(e.child)
            return
        if isinstance(e, Const):
            return

        if isinstance(e, PixelMatchPoint):
            pid = (e.point_id or "").strip()
            if pid:
                out.point_ids.add(pid)
            return

        if isinstance(e, CastBarChanged):
            pid = (e.point_id or "").strip()
            if pid:
                out.point_ids.add(pid)
            return

        if isinstance(e, PixelMatchSkill):
            sid = (e.skill_id or "").strip()
            if sid:
                out.skill_pixel_ids.add(sid)
            return

        if isinstance(e, SkillMetricGE):
            sid = (e.skill_id or "").strip()
            if sid:
                out.skill_metric_ids.add(sid)
            return

    walk(expr)
    return out