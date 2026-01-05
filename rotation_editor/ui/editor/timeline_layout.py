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
    - duration_ms: 真实持续时间（仅用于 tooltip/信息展示；不再决定宽度）
    - start_ms/end_ms: 显示用时间轴位置（以 STEP_MS 为粒度）
    - width: 绘制宽度（固定为一个 STEP 的宽度）
    - has_condition/condition_name: 网关条件信息
    """
    node_id: str
    label: str
    kind: str
    duration_ms: int
    start_ms: int
    end_ms: int
    width: float
    has_condition: bool = False
    condition_name: str = ""


@dataclass
class TrackVisualSpec:
    mode_id: str
    track_id: str
    title: str
    nodes: List[NodeVisualSpec]
    total_duration_ms: int


def _collect_skills_by_id(ctx: ProfileContext) -> Dict[str, Skill]:
    skills_by_id: Dict[str, Skill] = {}
    try:
        for s in getattr(ctx.skills, "skills", []) or []:
            if s.id:
                skills_by_id[s.id] = s
    except Exception:
        pass
    return skills_by_id


def _skill_real_duration_ms(n: SkillNode, skills_by_id: Dict[str, Skill]) -> int:
    """
    真实读条时间（仅用于显示/tooltip，不用于宽度）。
    """
    try:
        if n.override_cast_ms is not None and int(n.override_cast_ms) > 0:
            return int(n.override_cast_ms)
        s = skills_by_id.get(n.skill_id or "", None)
        if s is not None:
            v = int(getattr(getattr(s, "cast", None), "readbar_ms", 0) or 0)
            if v > 0:
                return v
        return 1000
    except Exception:
        return 1000


def build_timeline_layout(
    ctx: Optional[ProfileContext],
    preset: Optional[RotationPreset],
    current_mode_id: Optional[str],
    *,
    time_scale_px_per_ms: float,
    min_node_px: float = 16.0,
    max_node_px: float = 800.0,
) -> List[TrackVisualSpec]:
    """
    构建时间轴布局数据（技能/网关宽度均固定为步长）。

    固定宽度规则：
    - 所有节点（SkillNode/GatewayNode/其他）绘制宽度 = STEP_MS * time_scale_px_per_ms（并 clamp）
    - start_ms/end_ms 均以 STEP_MS 为粒度计算

    布局规则：
    - 若该轨道存在任一节点 step_index > 0：启用 step 轴布局
        start_ms = step_index * STEP_MS
    - 否则：按节点顺序均匀排布
        start_ms = index * STEP_MS
    """
    if ctx is None or preset is None:
        return []

    skills_by_id = _collect_skills_by_id(ctx)

    cond_name_by_id: Dict[str, str] = {
        c.id: (c.name or "(未命名条件)") for c in (preset.conditions or [])
    }

    # 步长（必须与 TimelineCanvas._step_ms 一致）
    STEP_MS = 1000

    def step_width_px() -> float:
        w = float(STEP_MS) * float(time_scale_px_per_ms)
        if w < float(min_node_px):
            w = float(min_node_px)
        if w > float(max_node_px):
            w = float(max_node_px)
        return w

    FIXED_W = step_width_px()

    def build_row(track: Track, title_prefix: str, mode_id_for_track: str) -> TrackVisualSpec:
        title = f"{title_prefix}{track.name or '(未命名)'}"

        if not track.nodes:
            return TrackVisualSpec(
                mode_id=mode_id_for_track,
                track_id=track.id or "",
                title=title,
                nodes=[],
                total_duration_ms=0,
            )

        # 判断是否启用 step 轴（只要存在 >0 就启用）
        max_step = 0
        for n in track.nodes:
            try:
                s = int(getattr(n, "step_index", 0) or 0)
            except Exception:
                s = 0
            if s < 0:
                s = 0
            if s > max_step:
                max_step = s
        use_step_axis = max_step > 0

        nodes_vs: List[NodeVisualSpec] = []
        max_end = 0

        for idx, n in enumerate(track.nodes):
            # start_ms/end_ms：显示用（固定步长）
            if use_step_axis:
                try:
                    s = int(getattr(n, "step_index", 0) or 0)
                except Exception:
                    s = 0
                if s < 0:
                    s = 0
                start = s * STEP_MS
            else:
                start = idx * STEP_MS

            end = start + STEP_MS
            if end > max_end:
                max_end = end

            # duration_ms：真实信息（仅 tooltip）
            if isinstance(n, SkillNode):
                real_d = _skill_real_duration_ms(n, skills_by_id)
            elif isinstance(n, GatewayNode):
                real_d = 0
            else:
                real_d = 0

            label = getattr(n, "label", "") or ""
            if not label:
                if isinstance(n, SkillNode):
                    label = "Skill"
                elif isinstance(n, GatewayNode):
                    label = "GW"
                else:
                    label = getattr(n, "kind", "") or f"N{idx}"

            kind = (getattr(n, "kind", "") or "").strip().lower() or "node"

            cond_name = ""
            if isinstance(n, GatewayNode):
                cid = getattr(n, "condition_id", None)
                if cid:
                    cond_name = cond_name_by_id.get(cid, "")

            nodes_vs.append(
                NodeVisualSpec(
                    node_id=getattr(n, "id", ""),
                    label=label,
                    kind=kind,
                    duration_ms=int(real_d),
                    start_ms=int(start),
                    end_ms=int(end),
                    width=float(FIXED_W),
                    has_condition=bool(cond_name),
                    condition_name=cond_name or "",
                )
            )

        return TrackVisualSpec(
            mode_id=mode_id_for_track,
            track_id=track.id or "",
            title=title,
            nodes=nodes_vs,
            total_duration_ms=int(max_end),
        )

    rows: List[TrackVisualSpec] = []

    # 全局轨道
    for gtrack in preset.global_tracks or []:
        rows.append(build_row(gtrack, "[全局] ", ""))

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
                rows.append(build_row(t, f"[模式:{mode.name}] ", mode.id or ""))

    return rows