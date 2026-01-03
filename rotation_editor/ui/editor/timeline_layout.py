from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Dict

from core.profiles import ProfileContext
from core.models.skill import Skill
from rotation_editor.core.models import (
    RotationPreset,
    Mode,
    Track,
    Node,
    SkillNode,
    GatewayNode,
)


@dataclass
class NodeVisualSpec:
    """
    单个节点在时间轴上的可视化规格：
    - node_id: 节点 ID
    - label: 显示文字
    - kind: "skill" / "gateway" / 其它
    - duration_ms: 持续时间（用于调试或将来展示）
    - width: 在时间轴上绘制的宽度（像素）
    """
    node_id: str
    label: str
    kind: str
    duration_ms: int
    width: float


@dataclass
class TrackVisualSpec:
    """
    单条轨道在时间轴上的可视化规格：
    - mode_id: 所属模式 ID（空字符串表示全局轨道）
    - track_id: 轨道 ID
    - title: 左侧显示的轨道标题（包含前缀，如 "[全局] xxx" 或 "[模式:Foo] xxx"）
    - nodes: 本轨道上所有节点的可视化规格（可以为空列表）
    """
    mode_id: str
    track_id: str
    title: str
    nodes: List[NodeVisualSpec]


def _collect_skills_by_id(ctx: ProfileContext) -> Dict[str, Skill]:
    skills_by_id: Dict[str, Skill] = {}
    try:
        for s in getattr(ctx.skills, "skills", []) or []:
            if s.id:
                skills_by_id[s.id] = s
    except Exception:
        pass
    return skills_by_id


def _node_duration_ms(n: Node, skills_by_id: Dict[str, Skill]) -> int:
    """
    计算单个节点的大致“持续时间”，用于宽度缩放。
    """
    try:
        if isinstance(n, SkillNode):
            if n.override_cast_ms is not None and n.override_cast_ms > 0:
                return int(n.override_cast_ms)
            s = skills_by_id.get(n.skill_id or "", None)
            if s is not None and getattr(s.cast, "readbar_ms", 0) > 0:
                return int(s.cast.readbar_ms)
            return 1000  # 默认 1 秒
        if isinstance(n, GatewayNode):
            return 500  # 网关节点统一较短
        return 800
    except Exception:
        return 1000


def build_timeline_layout(
    ctx: Optional[ProfileContext],
    preset: Optional[RotationPreset],
    current_mode_id: Optional[str],
    *,
    base_width: float = 90.0,
) -> List[TrackVisualSpec]:
    """
    构建时间轴布局数据：

    - ctx: 用于查技能读条时间
    - preset: 当前 RotationPreset
    - current_mode_id:
        * None / "" => 仅显示全局轨道
        * 非空 => 显示全局轨道 + 对应模式下所有轨道
    - base_width: 基准宽度，用于根据 duration 比例缩放

    返回：
    - 若 ctx 或 preset 为 None，则返回空列表
    - 否则返回若干 TrackVisualSpec，顺序为：
        1) 所有全局轨道
        2) 若 current_mode_id 非空，则该模式下所有轨道
    """
    if ctx is None or preset is None:
        return []

    skills_by_id = _collect_skills_by_id(ctx)

    rows: List[TrackVisualSpec] = []

    def build_row(
        track: Track,
        title_prefix: str,
        mode_id_for_track: str,
    ) -> TrackVisualSpec:
        """
        为单条轨道构建 TrackVisualSpec。
        即使该轨道没有任何节点，也会返回 nodes=[] 的 TrackVisualSpec，
        以便 UI 仍然能显示轨道名称和“新增轨道/新增节点”等入口。
        """
        title = f"{title_prefix}{track.name or '(未命名)'}"

        if not track.nodes:
            return TrackVisualSpec(
                mode_id=mode_id_for_track,
                track_id=track.id or "",
                title=title,
                nodes=[],
            )

        durations: List[int] = []
        nodes_vs: List[NodeVisualSpec] = []

        for n in track.nodes:
            d = _node_duration_ms(n, skills_by_id)
            durations.append(d)

        max_d = max(durations) if durations else 1
        if max_d <= 0:
            max_d = 1

        for n, d in zip(track.nodes, durations):
            ratio = d / max_d if max_d > 0 else 1.0
            # 缩放到 [0.6 * base, 1.6 * base]
            scale = 0.5 + 0.5 * ratio
            w = base_width * scale
            if w < base_width * 0.6:
                w = base_width * 0.6
            if w > base_width * 1.6:
                w = base_width * 1.6

            label = getattr(n, "label", "") or ""
            if not label:
                if isinstance(n, SkillNode):
                    label = "Skill"
                elif isinstance(n, GatewayNode):
                    label = "GW"
                else:
                    label = getattr(n, "kind", "") or "N"

            kind = (getattr(n, "kind", "") or "").strip().lower() or "node"

            nodes_vs.append(
                NodeVisualSpec(
                    node_id=getattr(n, "id", ""),
                    label=label,
                    kind=kind,
                    duration_ms=int(d),
                    width=float(w),
                )
            )

        return TrackVisualSpec(
            mode_id=mode_id_for_track,
            track_id=track.id or "",
            title=title,
            nodes=nodes_vs,
        )

    # 全局轨道
    for gtrack in preset.global_tracks or []:
        row = build_row(gtrack, "[全局] ", "")
        rows.append(row)

    # 当前模式轨道
    mid = (current_mode_id or "").strip()
    if mid:
        mode: Optional[Mode] = None
        for m in preset.modes or []:
            if m.id == mid:
                mode = m
                break
        if mode is not None:
            for t in mode.tracks or []:
                row = build_row(t, f"[模式:{mode.name}] ", mode.id or "")
                rows.append(row)

    return rows