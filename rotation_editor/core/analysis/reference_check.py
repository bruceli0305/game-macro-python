from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Any

from core.profiles import ProfileContext
from rotation_editor.core.models import (
    RotationPreset,
    Track,
    Mode,
    Node,
    SkillNode,
    GatewayNode,
    Condition,
)


@dataclass
class RefUsage:
    """
    某个引用（技能ID/点位ID）的使用情况：
    - ref_id: 被引用的 ID
    - locations: 该 ID 出现的位置描述（用于提示）
    """
    ref_id: str
    locations: List[str]


@dataclass
class ReferenceReport:
    """
    单个 RotationPreset 的引用检查结果：
    - preset_id / preset_name
    - missing_skills: 引用了不存在的技能ID
    - missing_points: 引用了不存在的点位ID
    """
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
    检查给定 preset 中对 skills / points 的引用是否缺失：

    - 节点：
        * SkillNode.skill_id
        * GatewayNode.condition_id (间接：Condition.expr 内的 pixel_point / pixel_skill)
    - 条件：
        * Condition.kind == "expr_tree_v1" 时，递归 AST 搜索：
            - pixel_point.point_id
            - pixel_skill.skill_id
            - skill_cast_ge.skill_id （技能次数条件，预留）

    返回 ReferenceReport，仅包含“缺失”的引用及其使用位置。
    """
    # 现有技能/点位 ID 集合
    skill_ids_existing = set(s.id for s in (ctx.skills.skills or []) if s.id)
    point_ids_existing = set(p.id for p in (ctx.points.points or []) if p.id)

    # 使用位置映射：id -> [位置描述...]
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
            elif isinstance(n, GatewayNode):
                # 网关只记录 condition_id，具体条件里的引用在扫描条件时处理
                pass
            else:
                # 其他类型节点目前不包含外部引用
                pass

    # 全局轨道
    for t in preset.global_tracks or []:
        scan_track(t, mode_label="全局")

    # 模式轨道
    for m in preset.modes or []:
        mlabel = f"模式『{m.name or '(未命名模式)'}』"
        for t in m.tracks or []:
            scan_track(t, mode_label=mlabel)

    # ---------- 扫描条件 AST ----------

    # 建立 condition_id -> Condition 映射，方便错误提示
    cond_by_id: Dict[str, Condition] = {c.id: c for c in preset.conditions or []}

    def scan_expr(node: Any, loc_prefix: str) -> None:
        if not isinstance(node, dict):
            return
        t = (node.get("type") or "").strip().lower()

        if t in ("logic_and", "logic_or"):
            for ch in node.get("children", []) or []:
                scan_expr(ch, loc_prefix)
            return

        if t == "logic_not":
            ch = node.get("child")
            if isinstance(ch, dict):
                scan_expr(ch, loc_prefix)
            return

        if t == "pixel_point":
            pid = (node.get("point_id") or "").strip()
            if pid:
                _mark_point_ref(pid, f"{loc_prefix} 中的点位条件(point_id={pid[-6:]})")
            return

        if t == "pixel_skill":
            sid = (node.get("skill_id") or "").strip()
            if sid:
                _mark_skill_ref(sid, f"{loc_prefix} 中的技能像素条件(skill_id={sid[-6:]})")
            return

        if t == "skill_cast_ge":
            sid = (node.get("skill_id") or "").strip()
            if sid:
                _mark_skill_ref(sid, f"{loc_prefix} 中的技能次数条件(skill_id={sid[-6:]})")
            return

        # 其他类型暂不处理
        return

    # 扫描每个 Condition
    for c in preset.conditions or []:
        loc_prefix = f"条件『{c.name or '(未命名条件)'}』"
        kind = (c.kind or "").strip().lower()
        if kind == "expr_tree_v1" and isinstance(c.expr, dict):
            scan_expr(c.expr, loc_prefix)
        else:
            # 旧格式暂不解析
            pass

    # ---------- 计算缺失引用 ----------

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