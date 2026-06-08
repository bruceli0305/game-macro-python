"""
rotation_editor.core.templates — 循环方案预设模板。

提供常用循环模式的工厂函数，帮助用户快速创建可运行的方案骨架，
而不是从空白方案开始手动添加 Mode/Track/Node。

每个模板函数返回一个完整的 RotationPreset，包含：
- 已创建的 Mode / Track / Node 结构
- 已设置的 EntryPoint（指向第一个节点）
- description 中包含使用说明

用户创建模板后，只需：
1. 将 SkillNode 的 skill_id 替换为自己的技能 ID
2. 根据需要调整节点顺序和条件
3. 点击"开始"即可运行
"""

from __future__ import annotations

import uuid
from typing import List

from rotation_editor.core.models import (
    RotationPreset,
    EntryPoint,
    Mode,
    Track,
    SkillNode,
    GatewayNode,
    Condition,
    CycleConfig,
    CyclePhase,
    SkillSlot,
)


def _nid() -> str:
    """生成节点/轨道/模式 ID。"""
    return uuid.uuid4().hex


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  模板注册表
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TEMPLATE_REGISTRY = {
    "sequential": {
        "name": "顺序循环",
        "desc": "最简单的循环：技能1 → 技能2 → 技能3 → 回到技能1",
        "icon": "1→2→3",
    },
    "priority": {
        "name": "优先级循环",
        "desc": "按优先级检测：条件A成立发技能A，否则发技能B，循环执行",
        "icon": "A?A:B",
    },
    "mode_switch": {
        "name": "双模式切换",
        "desc": "两种战斗模式（如武器A/B），通过网关条件自动切换",
        "icon": "A⇌B",
    },
    "cycle_priority": {
        "name": "优先级阶段循环（推荐）",
        "desc": "按阶段+优先级调度：先打A/B，满足条件后放D，最后放C，自动循环",
        "icon": "A→B→D→C",
    },
    "blank": {
        "name": "空白方案",
        "desc": "从零开始，手动添加所有内容",
        "icon": "空",
    },
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  模板工厂函数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def create_sequential(name: str, skill_count: int = 3) -> RotationPreset:
    """
    顺序循环模板：
    Mode("主循环") → Track("主轨道")
      → SkillNode("技能1") → SkillNode("技能2") → SkillNode("技能3")
      → 自动回到起点（全局轨道无限循环语义）

    用户只需替换 skill_id 即可使用。
    """
    pid = _nid()
    track_id = _nid()
    node_ids = [_nid() for _ in range(skill_count)]

    nodes: List[SkillNode] = []
    for i in range(skill_count):
        nodes.append(SkillNode(
            id=node_ids[i],
            kind="skill",
            label=f"技能{i + 1}",
            skill_id="",  # 用户需替换
        ))

    track = Track(id=track_id, name="主轨道", nodes=nodes)
    mode = Mode(id=_nid(), name="主循环", tracks=[track])

    preset = RotationPreset(
        id=pid,
        name=name,
        description=(
            "【顺序循环模板】\n"
            f"按顺序执行 {skill_count} 个技能，循环往复。\n\n"
            "使用方法：\n"
            "1. 在编辑器中点击每个技能节点\n"
            "2. 在右侧属性面板中选择对应的技能\n"
            "3. 点击「开始」运行\n\n"
            "提示：可以在轨道末尾添加「网关节点」来实现条件退出。"
        ),
        entry=EntryPoint(
            scope="mode",
            mode_id=mode.id,
            track_id=track_id,
            node_id=node_ids[0],
        ),
        modes=[mode],
    )
    return preset


def create_priority(name: str) -> RotationPreset:
    """
    优先级循环模板：
    Mode("主循环") → Track("优先级轨道")
      → Gateway("检测A", condition=skill_metric_ge, action=jump_node → 技能A)
      → SkillNode("技能B", 低优先级)
      → SkillNode("技能A", 高优先级)
      → 回到 Gateway

    逻辑：每次循环先检查条件A，成立则跳到技能A，否则执行技能B。
    """
    pid = _nid()
    track_id = _nid()

    gw_id = _nid()
    skill_a_id = _nid()
    skill_b_id = _nid()

    # 条件：技能A 的 attempt_started 指标 ≥ 1（即技能A可用）
    # 用户需替换 skill_id 为实际技能 ID
    cond_expr = {
        "type": "skill_metric_ge",
        "skill_id": "",  # 用户需替换为技能A的ID
        "metric": "success",
        "count": 1,
    }

    gw = GatewayNode(
        id=gw_id,
        kind="gateway",
        label="检测条件A",
        action="jump_node",
        target_node_id=skill_a_id,
        condition_expr=cond_expr,
    )

    skill_b = SkillNode(
        id=skill_b_id,
        kind="skill",
        label="技能B(默认)",
        skill_id="",  # 用户需替换
    )

    skill_a = SkillNode(
        id=skill_a_id,
        kind="skill",
        label="技能A(优先)",
        skill_id="",  # 用户需替换
    )

    track = Track(id=track_id, name="优先级轨道", nodes=[gw, skill_b, skill_a])
    mode = Mode(id=_nid(), name="主循环", tracks=[track])

    preset = RotationPreset(
        id=pid,
        name=name,
        description=(
            "【优先级循环模板】\n"
            "每次循环先检测条件A：\n"
            "  - 条件成立 → 跳到技能A（优先执行）\n"
            "  - 条件不成立 → 执行技能B（默认执行）\n\n"
            "使用方法：\n"
            "1. 编辑网关节点「检测条件A」，设置条件（如像素匹配/技能指标）\n"
            "2. 将技能A和技能B的 skill_id 替换为你的实际技能\n"
            "3. 点击「开始」运行\n\n"
            "典型场景：\n"
            "- 检测某个技能可用时优先释放\n"
            "- 检测Buff存在时切换输出手法"
        ),
        entry=EntryPoint(
            scope="mode",
            mode_id=mode.id,
            track_id=track_id,
            node_id=gw_id,
        ),
        modes=[mode],
    )
    return preset


def create_mode_switch(name: str) -> RotationPreset:
    """
    双模式切换模板：
    Mode("武器A") → Track → SkillNode×2 + Gateway(切换到B)
    Mode("武器B") → Track → SkillNode×2 + Gateway(切换到A)

    逻辑：在武器A循环中检测条件，成立则切换到武器B；武器B同理。
    """
    pid = _nid()

    # --- 武器A ---
    mode_a_id = _nid()
    track_a_id = _nid()
    gw_a_id = _nid()
    s_a1_id = _nid()
    s_a2_id = _nid()

    gw_a = GatewayNode(
        id=gw_a_id,
        kind="gateway",
        label="切换到武器B",
        action="switch_mode",
        target_mode_id="",  # 下面填充
        target_track_id="",  # 下面填充
        target_node_id=s_a1_id,  # 暂时指向自己，后面修正
        condition_expr={
            "type": "skill_metric_ge",
            "skill_id": "",
            "metric": "success",
            "count": 2,
        },
    )

    track_a = Track(id=track_a_id, name="武器A轨道", nodes=[
        SkillNode(id=s_a1_id, kind="skill", label="A-技能1", skill_id=""),
        SkillNode(id=s_a2_id, kind="skill", label="A-技能2", skill_id=""),
        gw_a,
    ])
    mode_a = Mode(id=mode_a_id, name="武器A", tracks=[track_a])

    # --- 武器B ---
    mode_b_id = _nid()
    track_b_id = _nid()
    gw_b_id = _nid()
    s_b1_id = _nid()
    s_b2_id = _nid()

    gw_b = GatewayNode(
        id=gw_b_id,
        kind="gateway",
        label="切换到武器A",
        action="switch_mode",
        target_mode_id=mode_a_id,
        target_track_id=track_a_id,
        target_node_id=s_a1_id,
        condition_expr={
            "type": "skill_metric_ge",
            "skill_id": "",
            "metric": "success",
            "count": 2,
        },
    )

    track_b = Track(id=track_b_id, name="武器B轨道", nodes=[
        SkillNode(id=s_b1_id, kind="skill", label="B-技能1", skill_id=""),
        SkillNode(id=s_b2_id, kind="skill", label="B-技能2", skill_id=""),
        gw_b,
    ])
    mode_b = Mode(id=mode_b_id, name="武器B", tracks=[track_b])

    # 修正武器A网关的目标
    gw_a.target_mode_id = mode_b_id
    gw_a.target_track_id = track_b_id
    gw_a.target_node_id = s_b1_id

    preset = RotationPreset(
        id=pid,
        name=name,
        description=(
            "【双模式切换模板】\n"
            "武器A循环 → 检测条件 → 切换到武器B循环 → 检测条件 → 切换回武器A\n\n"
            "使用方法：\n"
            "1. 将每个技能节点的 skill_id 替换为你的实际技能\n"
            "2. 编辑两个网关节点的切换条件（如技能次数/像素匹配）\n"
            "3. 点击「开始」运行\n\n"
            "典型场景：\n"
            "- 武器A打完一轮切武器B\n"
            "- 检测CD好了切换武器\n"
            "- 双持武器交替输出"
        ),
        entry=EntryPoint(
            scope="mode",
            mode_id=mode_a_id,
            track_id=track_a_id,
            node_id=s_a1_id,
        ),
        modes=[mode_a, mode_b],
    )
    return preset


def create_blank(name: str) -> RotationPreset:
    """
    空白模板：只创建一个空的 Mode + Track，用户从零开始。
    """
    pid = _nid()
    mode_id = _nid()
    track_id = _nid()

    track = Track(id=track_id, name="主轨道", nodes=[])
    mode = Mode(id=mode_id, name="主循环", tracks=[track])

    preset = RotationPreset(
        id=pid,
        name=name,
        description="空白方案，请在编辑器中添加技能节点和网关节点。",
        entry=EntryPoint(
            scope="mode",
            mode_id=mode_id,
            track_id=track_id,
            node_id="",
        ),
        modes=[mode],
    )
    return preset


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  循环阶段模板（CycleConfig）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def create_cycle_priority(name: str) -> CycleConfig:
    """
    优先级阶段循环模板 — 用户描述的精确场景：

    Phase 1: 先打A和B（A优先，A没好就打B）
    Phase 2: AB都放过且C没放过 → 放D
    Phase 3: ABD都放过 → 放C
    → 循环重置

    返回 CycleConfig（不是 RotationPreset），用于循环阶段执行器。
    """
    return CycleConfig(
        name=name,
        phases=[
            CyclePhase(
                name="先打A和B",
                skills=[
                    SkillSlot(skill_id="", priority=1, label="技能A（优先）"),
                    SkillSlot(skill_id="", priority=2, label="技能B（次优先）"),
                ],
                complete_when="all_fired",
            ),
            CyclePhase(
                name="放D（AB都放过且C没放过）",
                skills=[
                    SkillSlot(skill_id="", priority=1, label="技能D"),
                ],
                complete_when="all_fired",
            ),
            CyclePhase(
                name="放C（ABD都放过）",
                skills=[
                    SkillSlot(skill_id="", priority=1, label="技能C"),
                ],
                complete_when="all_fired",
            ),
        ],
        poll_interval_ms=50,
        max_cycles=0,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  统一入口
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def create_from_template(template_key: str, name: str):
    """
    根据模板 key 创建预设方案。

    Args:
        template_key: "sequential" / "priority" / "mode_switch" / "cycle_priority" / "blank"
        name: 方案名称

    Returns:
        RotationPreset 或 CycleConfig（cycle_priority 返回 CycleConfig）
    """
    if template_key == "cycle_priority":
        return create_cycle_priority(name)

    factories = {
        "sequential": create_sequential,
        "priority": create_priority,
        "mode_switch": create_mode_switch,
        "blank": create_blank,
    }
    factory = factories.get(template_key)
    if factory is None:
        return create_blank(name)
    return factory(name)
