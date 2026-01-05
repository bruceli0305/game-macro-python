from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Any

from core.profiles import ProfileContext
from rotation_editor.core.models import (
    RotationPreset,
    Track,
    Mode,
    SkillNode,
    GatewayNode,
    Condition,
)


@dataclass
class RefUsage:
    ref_id: str
    locations: List[str]


@dataclass
class ReferenceReport:
    preset_id: str
    preset_name: str
    missing_skills: List[RefUsage]
    missing_points: List[RefUsage]


def analyze_preset_references(
    *,
    ctx: ProfileContext,
    preset: RotationPreset,
) -> ReferenceReport:
    """
    Groups-only 引用检查：

    扫描来源：
    - SkillNode.skill_id
    - Condition(kind="groups") expr.groups[].atoms[]:
        * pixel_point.point_id
        * pixel_skill.skill_id
        * skill_cast_ge.skill_id
    """
    skill_ids_existing = set(s.id for s in (ctx.skills.skills or []) if s.id)
    point_ids_existing = set(p.id for p in (ctx.points.points or []) if p.id)

    skill_usages: Dict[str, List[str]] = {}
    point_usages: Dict[str, List[str]] = {}

    def _mark_skill_ref(sid: str, loc: str) -> None:
        sid = (sid or "").strip()
        if not sid:
            return
        skill_usages.setdefault(sid, []).append(loc)

    def _mark_point_ref(pid: str, loc: str) -> None:
        pid = (pid or "").strip()
        if not pid:
            return
        point_usages.setdefault(pid, []).append(loc)

    # ---------- 扫描轨道节点 ----------
    def scan_track(track: Track, mode_label: str) -> None:
        tname = track.name or "(未命名轨道)"
        track_loc = f"轨道『{tname}』({mode_label})"

        for n in track.nodes or []:
            if isinstance(n, SkillNode):
                sid = (n.skill_id or "").strip()
                if sid:
                    loc = f"{track_loc} 中的技能节点『{n.label or '(未命名)'}』"
                    _mark_skill_ref(sid, loc)

    for t in preset.global_tracks or []:
        scan_track(t, mode_label="全局")

    for m in preset.modes or []:
        mlabel = f"模式『{m.name or '(未命名模式)'}』"
        for t in m.tracks or []:
            scan_track(t, mode_label=mlabel)

    # ---------- 扫描条件（groups） ----------
    for c in preset.conditions or []:
        if (c.kind or "").strip().lower() != "groups":
            continue
        expr = c.expr or {}
        if not isinstance(expr, dict):
            continue
        groups = expr.get("groups", [])
        if not isinstance(groups, list):
            continue

        cname = c.name or "(未命名条件)"
        for gi, g in enumerate(groups):
            if not isinstance(g, dict):
                continue
            atoms = g.get("atoms", [])
            if not isinstance(atoms, list):
                continue

            for ai, a in enumerate(atoms):
                if not isinstance(a, dict):
                    continue
                t = (a.get("type") or "").strip().lower()
                loc_prefix = f"条件『{cname}』/组合{gi+1}/原子{ai+1}"

                if t == "pixel_point":
                    pid = (a.get("point_id") or "").strip()
                    if pid:
                        _mark_point_ref(pid, f"{loc_prefix} (pixel_point:{pid[-6:]})")

                elif t == "pixel_skill":
                    sid = (a.get("skill_id") or "").strip()
                    if sid:
                        _mark_skill_ref(sid, f"{loc_prefix} (pixel_skill:{sid[-6:]})")

                elif t == "skill_cast_ge":
                    sid = (a.get("skill_id") or "").strip()
                    if sid:
                        _mark_skill_ref(sid, f"{loc_prefix} (skill_cast_ge:{sid[-6:]})")

    # ---------- 计算缺失 ----------
    missing_skills: List[RefUsage] = []
    for sid, locs in skill_usages.items():
        if sid not in skill_ids_existing:
            missing_skills.append(RefUsage(ref_id=sid, locations=locs))

    missing_points: List[RefUsage] = []
    for pid, locs in point_usages.items():
        if pid not in point_ids_existing:
            missing_points.append(RefUsage(ref_id=pid, locations=locs))

    return ReferenceReport(
        preset_id=preset.id or "",
        preset_name=preset.name or "",
        missing_skills=missing_skills,
        missing_points=missing_points,
    )