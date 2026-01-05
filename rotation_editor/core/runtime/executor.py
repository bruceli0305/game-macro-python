from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Optional
import threading

from core.profiles import ProfileContext
from core.pick.scanner import PixelScanner
from core.pick.capture import ScreenCapture

from rotation_editor.core.models import RotationPreset, SkillNode, GatewayNode, Condition
from rotation_editor.core.runtime.context import RuntimeContext
from rotation_editor.core.runtime.cast_strategies import CastCompletionStrategy
from rotation_editor.core.runtime.keyboard import KeySender

from rotation_editor.core.runtime.condition_eval import eval_condition
from rotation_editor.core.runtime.clock import mono_ms

log = logging.getLogger(__name__)


class SimpleSkillState:
    """
    最简技能状态机实现：只记录施放次数（供 skill_cast_ge 使用）
    """
    def __init__(self) -> None:
        self._counts: dict[str, int] = {}

    def record_cast(self, skill_id: str) -> None:
        sid = (skill_id or "").strip()
        if not sid:
            return
        self._counts[sid] = self._counts.get(sid, 0) + 1

    def get_cast_count(self, skill_id: str) -> int:
        return self._counts.get((skill_id or "").strip(), 0)


class SnapshotCapture(ScreenCapture):
    """
    用 PixelScanner + FrameSnapshot 实现 get_rgb_scoped_abs，
    以便复用 eval_condition / BarCastStrategy。
    """
    def __init__(self, scanner: PixelScanner, snapshot) -> None:
        super().__init__()
        self._scanner = scanner
        self._snapshot = snapshot

    def get_rgb_scoped_abs(self, x_abs, y_abs, sample, monitor_key, *, require_inside=True):
        from core.pick.scanner import PixelProbe
        probe = PixelProbe(
            monitor=str(monitor_key or "primary"),
            vx=int(x_abs),
            vy=int(y_abs),
            sample=sample,
        )
        return self._scanner.sample_rgb(self._snapshot, probe)


@dataclass
class NodeExecutor:
    """
    执行器：集中处理 skill/gateway 的“节点级逻辑”，引擎只负责调度与状态机。
    """
    ctx: ProfileContext
    key_sender: KeySender
    cast_strategy: CastCompletionStrategy
    skill_state: SimpleSkillState
    scanner: PixelScanner
    plan_getter: Callable[[], object]
    stop_evt: threading.Event
    default_skill_gap_ms: int

    def mk_rt_ctx(self) -> RuntimeContext:
        plan = self.plan_getter()
        snap = self.scanner.capture_with_plan(plan)
        sc = SnapshotCapture(scanner=self.scanner, snapshot=snap)
        return RuntimeContext(profile=self.ctx, capture=sc, skill_state=self.skill_state)

    def exec_skill_node(self, node: SkillNode) -> int:
        skills = getattr(self.ctx.skills, "skills", []) or []
        skill = next((s for s in skills if s.id == node.skill_id), None)
        if skill is None:
            return mono_ms() + 50

        if self.stop_evt.is_set():
            return mono_ms()

        key = (skill.trigger.key or "").strip()
        if key:
            try:
                self.key_sender.send_key(key)
            except Exception:
                log.exception("send_key failed")

        self.skill_state.record_cast(skill.id)

        readbar_ms = int(node.override_cast_ms or skill.cast.readbar_ms or 0)

        self.cast_strategy.wait_for_complete(
            skill_id=skill.id,
            node_readbar_ms=readbar_ms,
            rt_ctx_factory=self.mk_rt_ctx,
            stop_evt=self.stop_evt,
        )

        return mono_ms() + int(self.default_skill_gap_ms)

    def find_condition(self, preset: RotationPreset, cond_id: str) -> Optional[Condition]:
        cid = (cond_id or "").strip()
        if not cid:
            return None
        for c in preset.conditions or []:
            if (c.id or "").strip() == cid:
                return c
        return None

    def gateway_condition_ok(self, preset: RotationPreset, node: GatewayNode) -> bool:
        cid = (node.condition_id or "").strip()
        if not cid:
            return True
        cond = self.find_condition(preset, cid)
        if cond is None:
            return False
        try:
            rt_ctx = self.mk_rt_ctx()
            return bool(eval_condition(cond, rt_ctx))
        except Exception:
            log.exception("eval_condition failed (condition_id=%s)", cid)
            return False