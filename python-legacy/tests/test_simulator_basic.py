from __future__ import annotations

from dataclasses import dataclass
from typing import List

from rotation_editor.sim import RotationSimulator, SimConfig
from rotation_editor.core.models import (
    RotationPreset,
    EntryPoint,
    Track,
    SkillNode,
    GatewayNode,
)
from core.models.skill import Skill, SkillsFile


# ---------- Dummy Context，用于模拟 ProfileContext ----------

@dataclass
class DummyExec:
    default_skill_gap_ms: int = 500  # 节点间默认间隔(ms)


@dataclass
class DummyBase:
    exec: DummyExec


class DummyCtx:
    """
    只提供 RotationSimulator 需要的最小属性：
    - skills: SkillsFile(skills=[Skill...])
    - base.exec.default_skill_gap_ms
    """
    def __init__(self, skills: List[Skill], gap_ms: int = 500) -> None:
        self.skills = SkillsFile(skills=skills)
        self.base = DummyBase(exec=DummyExec(default_skill_gap_ms=gap_ms))


# ---------- 帮助函数：构造简单的 preset ----------

def make_simple_preset() -> RotationPreset:
    """
    构造一个只有 1 条全局轨道、3 个技能节点的 RotationPreset：

    轨道 t1:
      n1 -> skill A
      n2 -> skill B
      n3 -> skill C

    入口 entry 指向 global/t1/n1。
    """
    # 三个 SkillNode，step_index 全为 0（按顺序轮询）
    n1 = SkillNode(id="n1", kind="skill", label="S1", skill_id="A")
    n2 = SkillNode(id="n2", kind="skill", label="S2", skill_id="B")
    n3 = SkillNode(id="n3", kind="skill", label="S3", skill_id="C")

    track = Track(
        id="t1",
        name="G1",
        nodes=[n1, n2, n3],
    )

    preset = RotationPreset(
        id="p1",
        name="P1",
        description="",
    )
    preset.global_tracks.append(track)

    # 入口：global -> t1.n1
    preset.entry = EntryPoint(
        scope="global",
        mode_id="",
        track_id="t1",
        node_id="n1",
    )
    return preset


# ---------- 测试 1：顺序与时间 ----------

def test_simulator_single_track_three_skills_order_and_time() -> None:
    """
    场景：
    - 3 个技能，读条时间均为 1000ms，冷却时间为 0；
    - default_skill_gap_ms = 500ms；
    - max_exec_nodes = 3，仅推演前三个节点。

    期望：
    - 事件顺序：S1, S2, S3；
    - 事件时间：0ms, 1500ms, 3000ms；
    - 最终时间：4500ms（最后一次 delay = 1000 + 500）。
    """
    # 三个技能：A/B/C，cast.readbar_ms = 1000，cooldown_ms = 0
    sA = Skill(id="A", name="A", enabled=True)
    sB = Skill(id="B", name="B", enabled=True)
    sC = Skill(id="C", name="C", enabled=True)
    sA.cast.readbar_ms = 1000
    sB.cast.readbar_ms = 1000
    sC.cast.readbar_ms = 1000
    sA.cooldown_ms = 0
    sB.cooldown_ms = 0
    sC.cooldown_ms = 0

    ctx = DummyCtx(skills=[sA, sB, sC], gap_ms=500)
    preset = make_simple_preset()

    sim = RotationSimulator(
        ctx=ctx,
        preset=preset,
        cfg=SimConfig(max_run_ms=60_000, max_exec_nodes=3),
    )
    result = sim.run()

    # 3 个事件
    assert len(result.events) == 3

    labels = [e.label for e in result.events]
    times = [e.t_ms for e in result.events]
    outcomes = [e.outcome for e in result.events]

    assert labels == ["S1", "S2", "S3"]
    assert times == [0, 1500, 3000]  # 0, +1500, +1500
    assert all(o == "SUCCESS" for o in outcomes)

    # 最终时间应为 4500ms（最后一次 delay=1000+500）
    assert result.final_time_ms == 4500

    # 技能指标：每个 skill 执行 1 次 success
    assert result.final_metrics["A"].metrics["success"] == 1
    assert result.final_metrics["B"].metrics["success"] == 1
    assert result.final_metrics["C"].metrics["success"] == 1

    # 冷却：next_available_ms = now_ms + cast_ms + cd_ms
    # A 在 t=0 施放：next_available = 0 + 1000 + 0 = 1000
    # B 在 t=1500 施放 -> 2500，C 在 t=3000 -> 4000
    assert result.final_metrics["A"].next_available_ms == 1000
    assert result.final_metrics["B"].next_available_ms == 2500
    assert result.final_metrics["C"].next_available_ms == 4000


# ---------- 测试 2：冷却不足时的 SKIPPED_CD ----------

def test_simulator_respects_cooldown_and_skips_when_not_ready() -> None:
    """
    场景：
    - 与上例相同的 3 节点轨道；
    - 但技能 A 的冷却时间很长（5000ms），B/C 冷却为 0；
    - default_skill_gap_ms = 500ms；
    - max_exec_nodes = 4（让轨道循环回到第 1 个节点一次）。

    时间线：
    - event0: t=0   -> S1(A) 成功，A next_available=0+1000+5000=6000
    - event1: t=1500-> S2(B) 成功
    - event2: t=3000-> S3(C) 成功
    - event3: t=4500-> S1(A) 再次轮到，但 now=4500 < 6000 -> SKIPPED_CD

    期望：
    - 第 4 个事件 outcome="SKIPPED_CD"，reason="cd_not_ready"。
    """
    sA = Skill(id="A", name="A", enabled=True)
    sB = Skill(id="B", name="B", enabled=True)
    sC = Skill(id="C", name="C", enabled=True)
    sA.cast.readbar_ms = 1000
    sB.cast.readbar_ms = 1000
    sC.cast.readbar_ms = 1000

    # 冷却：A 很长，B/C 为 0
    sA.cooldown_ms = 5000
    sB.cooldown_ms = 0
    sC.cooldown_ms = 0

    ctx = DummyCtx(skills=[sA, sB, sC], gap_ms=500)
    preset = make_simple_preset()

    sim = RotationSimulator(
        ctx=ctx,
        preset=preset,
        cfg=SimConfig(max_run_ms=60_000, max_exec_nodes=4),
    )
    result = sim.run()

    assert len(result.events) == 4

    labels = [e.label for e in result.events]
    times = [e.t_ms for e in result.events]
    outcomes = [e.outcome for e in result.events]
    reasons = [e.reason for e in result.events]

    # 前三次仍然是 S1, S2, S3
    assert labels[:3] == ["S1", "S2", "S3"]
    assert times[:3] == [0, 1500, 3000]
    assert all(o == "SUCCESS" for o in outcomes[:3])

    # 第 4 次再轮到 S1（技能 A），但处于冷却中
    assert labels[3] == "S1"
    assert outcomes[3] == "SKIPPED_CD"
    assert reasons[3] == "cd_not_ready"

    # A 的 next_available 应为 6000
    assert result.final_metrics["A"].next_available_ms == 6000


# ---------- 测试 3：Gateway + SkillMetricGE 条件触发 end ----------

def test_gateway_condition_skill_metric_ge_end() -> None:
    """
    场景：
    - 轨道 t1:  S1(A) -> S2(A) -> G1(gateway)
    - G1 的条件：skill_metric_ge(skill_id="A", metric="success", count=2)
      且 action="end"。

    default_skill_gap_ms = 500, A 读条=1000, 冷却=0。

    时间线：
    - event0: t=0    -> S1(A) 成功，A.success=1
    - event1: t=1500 -> S2(A) 成功，A.success=2
    - event2: t=3000 -> G1，条件 true => GW_END，结束推演

    期望：
    - 三个事件：S1, S2, G1
    - 第三个事件 outcome="GW_END"，reason="gw_end"
    - final_time_ms = 3000
    - A.success == 2
    """
    sA = Skill(id="A", name="A", enabled=True)
    sA.cast.readbar_ms = 1000
    sA.cooldown_ms = 0

    ctx = DummyCtx(skills=[sA], gap_ms=500)

    # 构造 preset
    n1 = SkillNode(id="n1", kind="skill", label="S1", skill_id="A")
    n2 = SkillNode(id="n2", kind="skill", label="S2", skill_id="A")

    gw = GatewayNode(
        id="g1",
        kind="gateway",
        label="G1",
        condition_id=None,
        condition_expr={
            "type": "skill_metric_ge",
            "skill_id": "A",
            "metric": "success",
            "count": 2,
        },
        action="end",
        target_mode_id=None,
        target_track_id=None,
        target_node_id=None,
    )

    track = Track(
        id="t1",
        name="G1",
        nodes=[n1, n2, gw],
    )

    preset = RotationPreset(
        id="pgw",
        name="Pgw",
        description="",
    )
    preset.global_tracks.append(track)
    preset.entry = EntryPoint(
        scope="global",
        mode_id="",
        track_id="t1",
        node_id="n1",
    )

    sim = RotationSimulator(
        ctx=ctx,
        preset=preset,
        cfg=SimConfig(max_run_ms=60_000, max_exec_nodes=10),
    )
    result = sim.run()

    assert len(result.events) == 3

    labels = [e.label for e in result.events]
    times = [e.t_ms for e in result.events]
    outcomes = [e.outcome for e in result.events]
    reasons = [e.reason for e in result.events]

    assert labels == ["S1", "S2", "G1"]
    assert times == [0, 1500, 3000]
    assert outcomes == ["SUCCESS", "SUCCESS", "GW_END"]
    assert reasons[2] == "gw_end"

    assert result.final_time_ms == 3000
    assert result.final_metrics["A"].metrics["success"] == 2


# ---------- 测试 4：Gateway jump_node 改变轨迹 ----------

def test_gateway_jump_node_loops_back_to_first_node() -> None:
    """
    场景：
    - 轨道 t1: S1(A) -> G1(gateway with action='jump_node', target_node_id='n1') -> S2(A)
    - 条件恒真（condition_expr=None）。

    default_skill_gap_ms = 500, A 读条=1000, 冷却=0。

    时间线（max_exec_nodes=3）：
    - event0: t=0    -> S1(A) 成功
    - event1: t=1500 -> G1，jump_node 到 n1，advance=False
    - event2: t=2000 -> S1(A) 再次执行（因为轨道指针被跳回 n1）

    期望：
    - 事件标签顺序：S1, G1, S1
    - 第 2 个事件 outcome="GW_JUMP_NODE"
    """
    sA = Skill(id="A", name="A", enabled=True)
    sA.cast.readbar_ms = 1000
    sA.cooldown_ms = 0

    ctx = DummyCtx(skills=[sA], gap_ms=500)

    n1 = SkillNode(id="n1", kind="skill", label="S1", skill_id="A")
    gw = GatewayNode(
        id="g1",
        kind="gateway",
        label="G1",
        condition_id=None,
        condition_expr=None,  # 无条件 => 恒真
        action="jump_node",
        target_mode_id=None,
        target_track_id=None,
        target_node_id="n1",
    )
    n2 = SkillNode(id="n2", kind="skill", label="S2", skill_id="A")

    track = Track(
        id="t1",
        name="G1",
        nodes=[n1, gw, n2],
    )

    preset = RotationPreset(
        id="pjump",
        name="Pjump",
        description="",
    )
    preset.global_tracks.append(track)
    preset.entry = EntryPoint(
        scope="global",
        mode_id="",
        track_id="t1",
        node_id="n1",
    )

    sim = RotationSimulator(
        ctx=ctx,
        preset=preset,
        cfg=SimConfig(max_run_ms=60_000, max_exec_nodes=3),
    )
    result = sim.run()

    assert len(result.events) == 3

    labels = [e.label for e in result.events]
    times = [e.t_ms for e in result.events]
    outcomes = [e.outcome for e in result.events]

    assert labels == ["S1", "G1", "S1"]
    assert outcomes[1] == "GW_JUMP_NODE"

    # 时间：0 -> +1500 -> +500（GW 用 default_gap_ms）= 2000
    assert times == [0, 1500, 2000]