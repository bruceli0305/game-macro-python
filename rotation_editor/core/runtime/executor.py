from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Callable, Optional, Dict, Tuple, List
import threading

from core.profiles import ProfileContext
from core.pick.scanner import PixelScanner
from core.pick.capture import ScreenCapture, SampleSpec

from rotation_editor.core.models import RotationPreset, SkillNode, GatewayNode, Condition
from rotation_editor.core.runtime.context import RuntimeContext
from rotation_editor.core.runtime.cast_strategies import CastCompletionStrategy
from rotation_editor.core.runtime.keyboard import KeySender
from rotation_editor.core.runtime.condition_eval import eval_condition
from rotation_editor.core.runtime.clock import mono_ms, wait_ms

log = logging.getLogger(__name__)


class SnapshotCapture(ScreenCapture):
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
class SkillStats:
    node_execution_count: int = 0
    ready_false_count: int = 0

    attempt_count: int = 0          # 每次 send_key 计一次（重试也计）
    retry_count_total: int = 0

    cast_start_count: int = 0
    success_count: int = 0
    fail_count: int = 0
    fail_by_reason: Dict[str, int] = field(default_factory=dict)

    last_result: str = ""           # success / failed:<reason> / skipped_*
    last_attempt_id: str = ""


class SimpleSkillState:
    """
    线程安全的统计存储：
    - get_cast_count() 默认返回 success_count（用于 skill_cast_ge）
    - snapshot_for_ui() 提供调试面板快照
    """
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_skill: Dict[str, SkillStats] = {}

    def _ensure(self, skill_id: str) -> SkillStats:
        sid = (skill_id or "").strip()
        if sid not in self._by_skill:
            self._by_skill[sid] = SkillStats()
        return self._by_skill[sid]

    # --- 条件接口：默认成功次数 ---
    def get_cast_count(self, skill_id: str) -> int:
        sid = (skill_id or "").strip()
        with self._lock:
            return int(self._ensure(sid).success_count)

    # --- 统计更新 API ---
    def inc_node_exec(self, skill_id: str) -> None:
        sid = (skill_id or "").strip()
        with self._lock:
            self._ensure(sid).node_execution_count += 1

    def inc_ready_false(self, skill_id: str, *, reason: str = "") -> None:
        sid = (skill_id or "").strip()
        with self._lock:
            st = self._ensure(sid)
            st.ready_false_count += 1
            st.last_result = f"skipped_not_ready{(':' + reason) if reason else ''}"

    def set_last_result(self, skill_id: str, value: str) -> None:
        sid = (skill_id or "").strip()
        with self._lock:
            self._ensure(sid).last_result = value or ""

    def new_attempt_id(self, skill_id: str) -> str:
        sid = (skill_id or "").strip()
        aid = uuid.uuid4().hex
        with self._lock:
            self._ensure(sid).last_attempt_id = aid
        return aid

    def inc_attempt(self, skill_id: str) -> None:
        sid = (skill_id or "").strip()
        with self._lock:
            self._ensure(sid).attempt_count += 1

    def inc_retry(self, skill_id: str) -> None:
        sid = (skill_id or "").strip()
        with self._lock:
            self._ensure(sid).retry_count_total += 1

    def inc_cast_start(self, skill_id: str) -> None:
        sid = (skill_id or "").strip()
        with self._lock:
            self._ensure(sid).cast_start_count += 1

    def mark_success(self, skill_id: str) -> None:
        sid = (skill_id or "").strip()
        with self._lock:
            st = self._ensure(sid)
            st.success_count += 1
            st.last_result = "success"

    def mark_fail(self, skill_id: str, reason: str) -> None:
        sid = (skill_id or "").strip()
        r = (reason or "unknown").strip() or "unknown"
        with self._lock:
            st = self._ensure(sid)
            st.fail_count += 1
            st.fail_by_reason[r] = st.fail_by_reason.get(r, 0) + 1
            st.last_result = f"failed:{r}"

    # --- UI 快照 ---
    def snapshot_for_ui(self, ctx: ProfileContext) -> List[Dict[str, object]]:
        skills_by_id = {s.id: s for s in (getattr(ctx.skills, "skills", []) or []) if getattr(s, "id", "")}
        with self._lock:
            out: List[Dict[str, object]] = []
            for sid, st in self._by_skill.items():
                s = skills_by_id.get(sid)
                out.append(
                    {
                        "skill_id": sid,
                        "skill_name": (getattr(s, "name", "") or "") if s is not None else "",
                        "node_exec": int(st.node_execution_count),
                        "ready_false": int(st.ready_false_count),
                        "attempt": int(st.attempt_count),
                        "retry": int(st.retry_count_total),
                        "cast_start": int(st.cast_start_count),
                        "success": int(st.success_count),
                        "fail": int(st.fail_count),
                        "last_result": st.last_result or "",
                        "last_attempt_id": st.last_attempt_id or "",
                        "fail_by_reason": dict(st.fail_by_reason or {}),
                    }
                )
        # 排序：有名字优先，按名字/ID
        out.sort(key=lambda d: ((d.get("skill_name") or ""), (d.get("skill_id") or "")))
        return out


@dataclass
class NodeExecutor:
    """
    SkillNode 执行 = Attempt FSM（阻塞式）。

    语义：
    - ready=False：不发键，推进节点（本轮跳过），下次 cycle 再判一次
    - 全局施法锁：PREPARING/CASTING 期间持有
    - start_signal_mode：pixel / cast_bar / none
    """
    ctx: ProfileContext
    key_sender: KeySender
    cast_strategy: CastCompletionStrategy
    skill_state: SimpleSkillState
    scanner: PixelScanner
    plan_getter: Callable[[], object]
    stop_evt: threading.Event
    cast_lock: threading.Lock

    default_skill_gap_ms: int
    poll_not_ready_ms: int = 50

    start_signal_mode: str = "pixel"
    start_timeout_ms: int = 20
    start_poll_ms: int = 10
    max_retries: int = 3
    retry_gap_ms: int = 30

    def mk_rt_ctx(self) -> RuntimeContext:
        plan = self.plan_getter()
        snap = self.scanner.capture_with_plan(plan)
        sc = SnapshotCapture(scanner=self.scanner, snapshot=snap)
        return RuntimeContext(profile=self.ctx, capture=sc, skill_state=self.skill_state)

    # ---------- cast_bar baseline / sample ----------
    def _get_cast_bar_point(self):
        cb = getattr(self.ctx.base, "cast_bar", None)
        if cb is None:
            return None
        pid = (getattr(cb, "point_id", "") or "").strip()
        if not pid:
            return None
        pts = getattr(self.ctx.points, "points", []) or []
        return next((p for p in pts if (p.id or "").strip() == pid), None)

    def _sample_point_rgb(self, rt_ctx: RuntimeContext, point) -> Optional[Tuple[int, int, int]]:
        try:
            sample = SampleSpec(mode=point.sample.mode, radius=int(point.sample.radius))
        except Exception:
            sample = SampleSpec(mode="single", radius=0)
        try:
            r, g, b = rt_ctx.capture.get_rgb_scoped_abs(
                x_abs=int(point.vx),
                y_abs=int(point.vy),
                sample=sample,
                monitor_key=point.monitor or "primary",
                require_inside=False,
            )
            return int(r), int(g), int(b)
        except Exception:
            return None

    # ---------- skill.pixel sample / ready ----------
    def _sample_skill_pixel(self, skill, rt_ctx: RuntimeContext) -> Optional[tuple[int, int, int, int, int, int, int]]:
        pix = getattr(skill, "pixel", None)
        if pix is None:
            return None

        try:
            vx = int(getattr(pix, "vx", 0))
            vy = int(getattr(pix, "vy", 0))
            mon = (getattr(pix, "monitor", "") or "primary").strip() or "primary"
            tol = int(getattr(pix, "tolerance", 0) or 0)
            tol = max(0, min(255, tol))
            color = getattr(pix, "color", None)
            sample_obj = getattr(pix, "sample", None)
        except Exception:
            return None

        if color is None or sample_obj is None:
            return None

        # 未取色常见默认值：视为不可判定（严格）
        try:
            if vx == 0 and vy == 0 and int(color.r) == 0 and int(color.g) == 0 and int(color.b) == 0:
                return None
        except Exception:
            return None

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
            return None

        try:
            tr = int(color.r)
            tg = int(color.g)
            tb = int(color.b)
        except Exception:
            return None

        return (int(r), int(g), int(b), int(tol), tr, tg, tb)

    def _is_skill_ready(self, skill, rt_ctx: RuntimeContext) -> Optional[bool]:
        samp = self._sample_skill_pixel(skill, rt_ctx)
        if samp is None:
            return None
        r, g, b, tol, tr, tg, tb = samp
        diff = max(abs(r - tr), abs(g - tg), abs(b - tb))
        return diff <= tol

    # ---------- start signal ----------
    def _wait_cast_start_none(self) -> bool:
        return True

    def _wait_cast_start_by_pixel(self, skill) -> bool:
        deadline = mono_ms() + int(max(1, self.start_timeout_ms))
        poll = int(max(5, self.start_poll_ms))
        while mono_ms() < deadline:
            if self.stop_evt.is_set():
                return False
            rt_ctx = self.mk_rt_ctx()
            ready = self._is_skill_ready(skill, rt_ctx)
            if ready is False:
                return True
            wait_ms(self.stop_evt, poll)
        return False

    def _wait_cast_start_by_cast_bar(self, baseline_rgb: Tuple[int, int, int]) -> bool:
        pt = self._get_cast_bar_point()
        if pt is None:
            return False

        cb = getattr(self.ctx.base, "cast_bar", None)
        tol = 15
        try:
            tol = int(getattr(cb, "tolerance", 15) or 15)
        except Exception:
            tol = 15
        tol = max(0, min(255, tol))

        deadline = mono_ms() + int(max(1, self.start_timeout_ms))
        poll = int(max(5, self.start_poll_ms))

        br0, bg0, bb0 = baseline_rgb
        while mono_ms() < deadline:
            if self.stop_evt.is_set():
                return False
            rt_ctx = self.mk_rt_ctx()
            cur = self._sample_point_rgb(rt_ctx, pt)
            if cur is not None:
                r, g, b = cur
                diff = max(abs(r - br0), abs(g - bg0), abs(b - bb0))
                if diff > tol:
                    return True
            wait_ms(self.stop_evt, poll)

        return False

    def _wait_cast_start(self, *, skill, baseline_cast_bar: Optional[Tuple[int, int, int]]) -> bool:
        m = (self.start_signal_mode or "pixel").strip().lower()
        if m == "none":
            return self._wait_cast_start_none()
        if m == "cast_bar":
            if baseline_cast_bar is None:
                return False
            return self._wait_cast_start_by_cast_bar(baseline_cast_bar)
        return self._wait_cast_start_by_pixel(skill)

    # ---------- SkillNode FSM ----------
    def exec_skill_node(self, node: SkillNode) -> int:
        skills = getattr(self.ctx.skills, "skills", []) or []
        skill = next((s for s in skills if s.id == node.skill_id), None)
        if skill is None:
            return mono_ms() + 50

        sid = (skill.id or "").strip()
        self.skill_state.inc_node_exec(sid)

        if self.stop_evt.is_set():
            self.skill_state.set_last_result(sid, "stopped")
            return mono_ms()

        if not bool(getattr(skill, "enabled", True)):
            self.skill_state.set_last_result(sid, "skipped_disabled")
            return mono_ms() + int(max(10, self.poll_not_ready_ms))

        # READY_CHECK
        rt_ctx = self.mk_rt_ctx()
        ready = self._is_skill_ready(skill, rt_ctx)

        # 严格：像素不可判定视为 not_ready（跳过推进）
        if ready is None:
            self.skill_state.inc_ready_false(sid, reason="pixel_missing_or_unreadable")
            return mono_ms() + int(max(10, self.poll_not_ready_ms))

        if ready is False:
            self.skill_state.inc_ready_false(sid)
            return mono_ms() + int(max(10, self.poll_not_ready_ms))

        # 施法锁：锁忙则跳过推进
        if not self.cast_lock.acquire(timeout=0):
            self.skill_state.set_last_result(sid, "skipped_lock_busy")
            return mono_ms() + int(max(10, self.poll_not_ready_ms))

        self.skill_state.new_attempt_id(sid)

        try:
            readbar_ms = int(node.override_cast_ms or skill.cast.readbar_ms or 0)
            retries_left = int(max(0, self.max_retries))

            def send_key_once() -> bool:
                key = (skill.trigger.key or "").strip()
                # 只要尝试发键就算一次 attempt
                self.skill_state.inc_attempt(sid)

                if not key:
                    self.skill_state.mark_fail(sid, "no_key")
                    return False
                try:
                    self.key_sender.send_key(key)
                    return True
                except Exception:
                    self.skill_state.mark_fail(sid, "send_key_error")
                    return False

            def cast_bar_baseline_if_needed() -> Optional[Tuple[int, int, int]]:
                if (self.start_signal_mode or "pixel").strip().lower() != "cast_bar":
                    return None
                pt = self._get_cast_bar_point()
                if pt is None:
                    return None
                base_ctx = self.mk_rt_ctx()
                return self._sample_point_rgb(base_ctx, pt)

            baseline = cast_bar_baseline_if_needed()
            if (self.start_signal_mode or "").strip().lower() == "cast_bar" and baseline is None:
                self.skill_state.mark_fail(sid, "cast_bar_unavailable")
                return mono_ms() + int(max(10, self.poll_not_ready_ms))

            if not send_key_once():
                return mono_ms() + int(max(10, self.poll_not_ready_ms))

            # readbar==0：默认成功
            if readbar_ms <= 0:
                self.skill_state.mark_success(sid)
                return mono_ms() + int(self.default_skill_gap_ms)

            started = self._wait_cast_start(skill=skill, baseline_cast_bar=baseline)

            while (not started) and (not self.stop_evt.is_set()) and retries_left > 0:
                self.skill_state.inc_retry(sid)
                retries_left -= 1

                wait_ms(self.stop_evt, int(max(0, self.retry_gap_ms)))
                if self.stop_evt.is_set():
                    break

                baseline = cast_bar_baseline_if_needed()
                if (self.start_signal_mode or "").strip().lower() == "cast_bar" and baseline is None:
                    self.skill_state.mark_fail(sid, "cast_bar_unavailable")
                    return mono_ms() + int(max(10, self.poll_not_ready_ms))

                if not send_key_once():
                    return mono_ms() + int(max(10, self.poll_not_ready_ms))

                started = self._wait_cast_start(skill=skill, baseline_cast_bar=baseline)

            if self.stop_evt.is_set():
                self.skill_state.set_last_result(sid, "stopped")
                return mono_ms()

            if not started:
                self.skill_state.mark_fail(sid, "no_cast_start")
                return mono_ms() + int(max(10, self.poll_not_ready_ms))

            self.skill_state.inc_cast_start(sid)

            ok = self.cast_strategy.wait_for_complete(
                skill_id=sid,
                node_readbar_ms=readbar_ms,
                rt_ctx_factory=self.mk_rt_ctx,
                stop_evt=self.stop_evt,
            )

            if self.stop_evt.is_set():
                self.skill_state.set_last_result(sid, "stopped")
                return mono_ms()

            if not ok:
                self.skill_state.mark_fail(sid, "timeout")
                return mono_ms() + int(max(10, self.poll_not_ready_ms))

            self.skill_state.mark_success(sid)
            return mono_ms() + int(self.default_skill_gap_ms)

        finally:
            try:
                self.cast_lock.release()
            except Exception:
                pass

    # ---------- Condition ----------
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