from __future__ import annotations

import unittest
import threading

from rotation_editor.core.models import Track, SkillNode, GatewayNode, Mode, RotationPreset, Condition
from rotation_editor.core.runtime.state import ModeRuntime
from rotation_editor.core.runtime.gateway_actions import apply_gateway_mode
from rotation_editor.core.runtime.clock import mono_ms


class TestModeRuntimeStepCycle(unittest.TestCase):
    def test_step_progress_and_cycle_reset(self) -> None:
        # 武器轨道：step0 -> step2
        t_weapon = Track(
            id="t_weapon",
            name="weapon",
            nodes=[
                SkillNode(id="n_w1", kind="skill", label="w1", skill_id="s1", step_index=0, order_in_step=0),
                SkillNode(id="n_w2", kind="skill", label="w2", skill_id="s2", step_index=2, order_in_step=0),
            ],
        )
        # 右边技能：step1（只有一个节点）
        t_elite = Track(
            id="t_elite",
            name="elite",
            nodes=[
                SkillNode(id="n_e", kind="skill", label="e", skill_id="s3", step_index=1, order_in_step=0),
            ],
        )

        rt = ModeRuntime(mode_id="m1", tracks=[t_weapon, t_elite], now_ms=mono_ms())
        rt.ensure_step_runnable()
        self.assertEqual(rt.current_step, 0)

        # 执行 step0：weapon 的当前节点应为 w1
        stw = rt.states["t_weapon"]
        self.assertEqual(stw.current_node_index(), 0)
        stw.advance()

        rt.ensure_step_runnable()
        self.assertEqual(rt.current_step, 1)

        # step1：elite 执行一次后 done
        ste = rt.states["t_elite"]
        self.assertEqual(ste.current_node_index(), 0)
        ste.advance()

        rt.ensure_step_runnable()
        self.assertEqual(rt.current_step, 2)

        # step2：weapon 当前应为 w2
        self.assertEqual(stw.current_node_index(), 1)
        stw.advance()

        # 所有轨道 done -> ensure_step_runnable 会 reset cycle
        rt.ensure_step_runnable()
        self.assertEqual(rt.current_step, 0)
        self.assertEqual(stw.current_node_index(), 0)
        self.assertEqual(ste.current_node_index(), 0)


class TestGatewayActionsMode(unittest.TestCase):
    def test_jump_track_moves_target_and_consumes_self(self) -> None:
        # 轨道 A：网关（step0）后面跟一个技能
        t_a = Track(
            id="t_a",
            name="A",
            nodes=[
                GatewayNode(
                    id="gw",
                    kind="gateway",
                    label="gw",
                    step_index=0,
                    order_in_step=0,
                    condition_id=None,
                    action="jump_track",
                    target_mode_id=None,
                    target_track_id="t_b",
                    target_node_index=1,
                ),
                SkillNode(id="a2", kind="skill", label="a2", skill_id="s1", step_index=0, order_in_step=0),
            ],
        )
        # 轨道 B：两个技能（step0）
        t_b = Track(
            id="t_b",
            name="B",
            nodes=[
                SkillNode(id="b1", kind="skill", label="b1", skill_id="s2", step_index=0, order_in_step=0),
                SkillNode(id="b2", kind="skill", label="b2", skill_id="s3", step_index=0, order_in_step=1),
            ],
        )

        rt = ModeRuntime(mode_id="m1", tracks=[t_a, t_b], now_ms=mono_ms())
        rt.ensure_step_runnable()

        st_a = rt.states["t_a"]
        st_b = rt.states["t_b"]

        # 初始：A 当前应指向网关节点（索引 0）
        self.assertEqual(st_a.current_node_index(), 0)
        # 初始：B 当前应指向 b1（索引 0）
        self.assertEqual(st_b.current_node_index(), 0)

        stop_evt = threading.Event()

        def build_mode_rt(_mid: str):
            return None

        def set_stop_reason(_r: str):
            return

        # 执行动作：jump_track -> 目标轨道 B 跳到 node_index=1（b2）
        new_rt = apply_gateway_mode(
            node=t_a.nodes[0],  # type: ignore[arg-type]
            current_track_id="t_a",
            mode_rt=rt,
            build_mode_rt=build_mode_rt,
            stop_evt=stop_evt,
            set_stop_reason=set_stop_reason,
        )
        self.assertIs(new_rt, rt)

        # B 被跳到 b2
        self.assertEqual(st_b.current_node_index(), 1)
        # A 网关被消费：advance 了一步，指向 a2
        self.assertEqual(st_a.current_node_index(), 1)


if __name__ == "__main__":
    unittest.main()