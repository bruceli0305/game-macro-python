from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Optional
import threading

from core.profiles import ProfileContext
from core.pick.scanner import PixelScanner
from core.pick.capture import ScreenCapture, SampleSpec

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
    用 PixelScanner + FrameSnapshot 实现 get_rgb_scoped_abs。
    注意：这里不会触发新的 mss 实例（PixelScanner 已经拿到了帧）。
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
    执行器：集中处理 skill/gateway 的节点级逻辑。

    新增：
    - poll_not_ready_ms：技能不可释放时的轮询间隔（越小轮询越快）
    """
    ctx: ProfileContext
    key_sender: KeySender
    cast_strategy: CastCompletionStrategy
    skill_state: SimpleSkillState
    scanner: PixelScanner
    plan_getter: Callable[[], object]
    stop_evt: threading.Event
    default_skill_gap_ms: int
    poll_not_ready_ms: int = 50

    def mk_rt_ctx(self) -> RuntimeContext:
        plan = self.plan_getter()
        snap = self.scanner.capture_with_plan(plan)
        sc = SnapshotCapture(scanner=self.scanner, snapshot=snap)
        return RuntimeContext(profile=self.ctx, capture=sc, skill_state=self.skill_state)

    # -----------------------------
    # 技能可释放判断：用 skill.pixel 取色比对
    # -----------------------------

    def _is_skill_ready_by_pixel(self, skill, rt_ctx: RuntimeContext) -> bool:
        """
        判定 skill 当前是否可释放：
        - 使用 skill.pixel (vx,vy,color,tolerance,sample,monitor)
        - diff = max(|dr|,|dg|,|db|) <= tolerance => 认为“可释放”
        - 若 pixel 缺失/无效：返回 True（不阻塞），但会打印 debug
        """
        pix = getattr(skill, "pixel", None)
        if pix is None:
            return True

        try:
            vx = int(getattr(pix, "vx", 0))
            vy = int(getattr(pix, "vy", 0))
            mon = (getattr(pix, "monitor", "") or "primary").strip() or "primary"
            tol = int(getattr(pix, "tolerance", 0) or 0)
            tol = max(0, min(255, tol))
            color = getattr(pix, "color", None)
            sample_obj = getattr(pix, "sample", None)
        except Exception:
            return True

        if color is None or sample_obj is None:
            return True

        # vx/vy 为 0 且 color 为 0 通常是未取色；不强制阻塞
        try:
            if vx == 0 and vy == 0 and int(color.r) == 0 and int(color.g) == 0 and int(color.b) == 0:
                return True
        except Exception:
            pass

        try:
            sample = SampleSpec(mode=sample_obj.mode, radius=int(getattr(sample_obj, "radius", 0) or 0))
        except Exception:
            sample = SampleSpec(mode="single", radius=0)

        try:
            r, g, b = rt_ctx.capture.get_rgb_scoped_abs(
                x_abs=vx,
                y_abs=vy,
                sample=sample,
                monitor_key=mon,
                require_inside=False,
            )
        except Exception:
            # 取色失败时：保守认为不可释放（避免乱按）
            return False

        try:
            tr = int(color.r)
            tg = int(color.g)
            tb = int(color.b)
        except Exception:
            return True

        dr = abs(int(r) - tr)
        dg = abs(int(g) - tg)
        db = abs(int(b) - tb)
        diff = max(dr, dg, db)

        return diff <= tol

    # -----------------------------
    # 执行 SkillNode：只有可释放才按键
    # -----------------------------

    def exec_skill_node(self, node: SkillNode) -> int:
        skills = getattr(self.ctx.skills, "skills", []) or []
        skill = next((s for s in skills if s.id == node.skill_id), None)
        if skill is None:
            return mono_ms() + 50

        if self.stop_evt.is_set():
            return mono_ms()

        # 禁用技能：视为跳过（不按键）
        if not bool(getattr(skill, "enabled", True)):
            return mono_ms() + int(max(10, self.poll_not_ready_ms))

        # 先抓一帧，用于 ready 检查（也能共享给后续 cast_strategy 内部取色）
        rt_ctx = self.mk_rt_ctx()

        # 核心：可释放才发送
        if not self._is_skill_ready_by_pixel(skill, rt_ctx):
            # 不可释放：不按键，不记录施放次数，快速返回用于轮询
            return mono_ms() + int(max(10, self.poll_not_ready_ms))

        key = (skill.trigger.key or "").strip()
        if key:
            try:
                self.key_sender.send_key(key)
            except Exception:
                log.exception("send_key failed")

        # 只有真正按键才计数
        self.skill_state.record_cast(skill.id)

        readbar_ms = int(node.override_cast_ms or skill.cast.readbar_ms or 0)

        self.cast_strategy.wait_for_complete(
            skill_id=skill.id,
            node_readbar_ms=readbar_ms,
            rt_ctx_factory=self.mk_rt_ctx,
            stop_evt=self.stop_evt,
        )

        return mono_ms() + int(self.default_skill_gap_ms)

    # -----------------------------
    # 条件
    # -----------------------------

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