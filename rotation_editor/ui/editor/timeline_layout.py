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
    - duration_ms: 持续时间（毫秒）
    - start_ms: 轨道内的起始时间（毫秒）
    - end_ms: 轨道内的结束时间（毫秒）
    - width: 在时间轴上绘制的宽度（像素）
    - has_condition: 是否绑定了条件（仅对 gateway 有意义）
    - condition_name: 条件名（若有）
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
    """
    单条轨道在时间轴上的可视化规格：
    - mode_id: 所属模式 ID（空字符串表示全局轨道）
    - track_id: 轨道 ID
    - title: 左侧显示的轨道标题（包含前缀，如 "[全局] xxx" 或 "[模式:Foo] xxx"）
    - nodes: 本轨道上所有节点的可视化规格（可以为空列表）
    - total_duration_ms: 该轨道顺序累加的总时长（毫秒）
    """
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
    time_scale_px_per_ms: float,
    min_node_px: float = 16.0,
    max_node_px: float = 800.0,
) -> List[TrackVisualSpec]:
    """
    构建时间轴布局数据：

    - ctx: 用于查技能读条时间
    - preset: 当前 RotationPreset
    - current_mode_id:
        * None / "" => 仅显示全局轨道
        * 非空 => 显示全局轨道 + 对应模式下所有轨道
    - time_scale_px_per_ms: 时间缩放比例（像素/毫秒），例如 0.06 表示 1s = 60px

    时间轴语义（升级版）：

    - 对每条轨道 Track：
        * 若该轨道上至少有一个节点的 step_index > 0，则启用“步骤轴布局”：
            - start_ms = step_index * STEP_MS（STEP_MS 为一个显示用的常数）
            - end_ms   = start_ms + duration_ms
        * 若所有节点的 step_index 都为 0（默认情况），退回到旧有逻辑：
            - 该轨道内部按节点顺序，从 0 累加 duration_ms 作为 start_ms/end_ms。
      注意：步轴布局仅影响“显示位置”，实际执行顺序由运行时引擎决定。

    返回：
    - 若 ctx 或 preset 为 None，则返回空列表
    - 否则返回若干 TrackVisualSpec，顺序为：
        1) 所有全局轨道
        2) 若 current_mode_id 非空，则该模式下所有轨道
    """
    if ctx is None or preset is None:
        return []

    skills_by_id = _collect_skills_by_id(ctx)
    # 条件名映射：供 GatewayNode 标记
    cond_name_by_id: Dict[str, str] = {
        c.id: (c.name or "(未命名条件)") for c in (preset.conditions or [])
    }

    rows: List[TrackVisualSpec] = []

    # 显示用步骤宽度（毫秒）：仅用于布局，不是实际读条时间
    STEP_MS = 1000

    def build_row(
        track: Track,
        title_prefix: str,
        mode_id_for_track: str,
    ) -> TrackVisualSpec:
        """
        为单条轨道构建 TrackVisualSpec。

        - 若轨道没有任何节点，仍然返回 nodes=[] 的 TrackVisualSpec，
          以便 UI 仍然能显示轨道名称和“新增轨道/新增节点”等入口。
        - 若该轨道上有节点且存在 step_index>0，则按 step_index*STEP_MS
          决定 start_ms；否则退回旧行为：按顺序累加 duration。
        """
        title = f"{title_prefix}{track.name or '(未命名)'}"

        if not track.nodes:
            return TrackVisualSpec(
                mode_id=mode_id_for_track,
                track_id=track.id or "",
                title=title,
                nodes=[],
                total_duration_ms=0,
            )

        nodes_vs: List[NodeVisualSpec] = []

        # 先收集所有节点的 step_index，判断是否启用步骤轴
        step_vals: List[int] = []
        for n in track.nodes:
            try:
                s = int(getattr(n, "step_index", 0) or 0)
            except Exception:
                s = 0
            if s < 0:
                s = 0
            step_vals.append(s)
        use_step_axis = bool(step_vals and max(step_vals) > 0)

        cur_t = 0
        max_end = 0

        for n in track.nodes:
            d = _node_duration_ms(n, skills_by_id)
            if d < 0:
                d = 0

            # 决定 start_ms / end_ms
            if use_step_axis:
                try:
                    s = int(getattr(n, "step_index", 0) or 0)
                except Exception:
                    s = 0
                if s < 0:
                    s = 0
                start = s * STEP_MS
            else:
                start = cur_t
                cur_t += d

            end = start + d
            if end > max_end:
                max_end = end

            # 像素宽度：duration * scale，限制在 [min_node_px, max_node_px]
            w = float(d) * float(time_scale_px_per_ms)
            if w < float(min_node_px):
                w = float(min_node_px)
            if w > float(max_node_px):
                w = float(max_node_px)

            label = getattr(n, "label", "") or ""
            if not label:
                if isinstance(n, SkillNode):
                    label = "Skill"
                elif isinstance(n, GatewayNode):
                    label = "GW"
                else:
                    label = getattr(n, "kind", "") or "N"

            kind = (getattr(n, "kind", "") or "").strip().lower() or "node"

            # 条件信息（仅 GatewayNode 有）
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
                    duration_ms=int(d),
                    start_ms=int(start),
                    end_ms=int(end),
                    width=w,
                    has_condition=bool(cond_name),
                    condition_name=cond_name or "",
                )
            )

        total_duration = int(max_end if use_step_axis else cur_t)
        return TrackVisualSpec(
            mode_id=mode_id_for_track,
            track_id=track.id or "",
            title=title,
            nodes=nodes_vs,
            total_duration_ms=total_duration,
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