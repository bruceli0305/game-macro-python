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


# -----------------------------
# 状态机：Attempt 明细（终态记录）
# -----------------------------

@dataclass
class AttemptLogEntry:
    attempt_id: str
    node_id: str
    start_mode: str
    started_ms: int
    casting_ms: Optional[int]
    ended_ms: int
    retries: int
    readbar_ms: int
    result: str               # "success" | "failed" | "stopped"
    fail_reason: str = ""     # timeout/no_cast_start/send_key_error/...


@dataclass
class AttemptRuntime:
    attempt_id: str = ""
    node_id: str = ""
    start_mode: str = ""
    state: str = "IDLE"       # READY_CHECK / PREPARING / CASTING / SUCCESS / FAILED / STOPPED / IDLE
    state_since_ms: int = 0

    started_ms: int = 0
    casting_ms: Optional[int] = None
    retries: int = 0
    readbar_ms: int = 0
    fail_reason: str = ""


@dataclass
class SkillStats:
    # 轮询层
    node_execution_count: int = 0
    ready_false_count: int = 0
    skipped_lock_busy: int = 0
    skipped_disabled: int = 0

    # Attempt 层（按键才算 attempt）
    attempt_count: int = 0
    retry_count_total: int = 0
    cast_start_count: int = 0
    success_count: int = 0
    fail_count: int = 0
    fail_by_reason: Dict[str, int] = field(default_factory=dict)

    last_result: str = ""
    last_attempt_id: str = ""

    # 当前 attempt（用于实时展示状态）
    current: AttemptRuntime = field(default_factory=AttemptRuntime)

    # 最近 attempt 日志（ring buffer）
    recent: List[AttemptLogEntry] = field(default_factory=list)


class SimpleSkillState:
    """
    线程安全的统计 + 状态机快照：
    - get_cast_count() 默认返回 success_count（用于 skill_cast_ge）
    - snapshot_for_ui(): 调试面板显示（含当前状态 + 最近 attempt）
    """
    def __init__(self, *, max_recent: int = 120) -> None:
        self._lock = threading.Lock()
        self._by_skill: Dict[str, SkillStats] = {}
        self._max_recent = int(max(10, max_recent))

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

    # --- 状态/计数更新 ---
    def inc_node_exec(self, skill_id: str) -> None:
        sid = (skill_id or "").strip()
        with self._lock:
            self._ensure(sid).node_execution_count += 1

    def mark_skipped_not_ready(self, skill_id: str, reason: str = "") -> None:
        sid = (skill_id or "").strip()
        with self._lock:
            st = self._ensure(sid)
            st.ready_false_count += 1
            st.last_result = f"skipped_not_ready{(':' + reason) if reason else ''}"
            # 当前状态也更新一下（方便面板看到）
            st.current.state = "READY_CHECK"
            st.current.state_since_ms = mono_ms()

    def mark_skipped_lock_busy(self, skill_id: str) -> None:
        sid = (skill_id or "").strip()
        with self._lock:
            st = self._ensure(sid)
            st.skipped_lock_busy += 1
            st.last_result = "skipped_lock_busy"
            st.current.state = "READY_CHECK"
            st.current.state_since_ms = mono_ms()

    def mark_skipped_disabled(self, skill_id: str) -> None:
        sid = (skill_id or "").strip()
        with self._lock:
            st = self._ensure(sid)
            st.skipped_disabled += 1
            st.last_result = "skipped_disabled"
            st.current.state = "READY_CHECK"
            st.current.state_since_ms = mono_ms()

    def begin_attempt(self, skill_id: str, *, node_id: str, start_mode: str, readbar_ms: int) -> str:
        sid = (skill_id or "").strip()
        aid = uuid.uuid4().hex
        now = mono_ms()
        with self._lock:
            st = self._ensure(sid)
            st.last_attempt_id = aid
            st.current = AttemptRuntime(
                attempt_id=aid,
                node_id=(node_id or ""),
                start_mode=(start_mode or ""),
                state="PREPARING",
                state_since_ms=now,
                started_ms=now,
                casting_ms=None,
                retries=0,
                readbar_ms=int(readbar_ms),
                fail_reason="",
            )
            st.last_result = "preparing"
        return aid

    def inc_attempt_send_key(self, skill_id: str) -> None:
        sid = (skill_id or "").strip()
        with self._lock:
            self._ensure(sid).attempt_count += 1

    def inc_retry(self, skill_id: str) -> None:
        sid = (skill_id or "").strip()
        with self._lock:
            st = self._ensure(sid)
            st.retry_count_total += 1
            st.current.retries += 1

    def set_state(self, skill_id: str, state: str) -> None:
        sid = (skill_id or "").strip()
        now = mono_ms()
        with self._lock:
            st = self._ensure(sid)
            st.current.state = state
            st.current.state_since_ms = now
            # 同步 last_result 更易读
            if state == "CASTING":
                st.last_result = "casting"
            elif state == "SUCCESS":
                st.last_result = "success"
            elif state == "FAILED":
                st.last_result = f"failed:{st.current.fail_reason or 'unknown'}"
            elif state == "STOPPED":
                st.last_result = "stopped"

    def mark_cast_started(self, skill_id: str) -> None:
        sid = (skill_id or "").strip()
        now = mono_ms()
        with self._lock:
            st = self._ensure(sid)
            st.cast_start_count += 1
            st.current.casting_ms = now
            st.current.state = "CASTING"
            st.current.state_since_ms = now
            st.last_result = "casting"

    def mark_success(self, skill_id: str) -> None:
        sid = (skill_id or "").strip()
        now = mono_ms()
        with self._lock:
            st = self._ensure(sid)
            st.success_count += 1
            st.current.state = "SUCCESS"
            st.current.state_since_ms = now
            st.last_result = "success"
            self._append_recent_locked(st, result="success", fail_reason="", ended_ms=now)

    def mark_fail(self, skill_id: str, reason: str) -> None:
        sid = (skill_id or "").strip()
        r = (reason or "unknown").strip() or "unknown"
        now = mono_ms()
        with self._lock:
            st = self._ensure(sid)
            st.fail_count += 1
            st.fail_by_reason[r] = st.fail_by_reason.get(r, 0) + 1
            st.current.fail_reason = r
            st.current.state = "FAILED"
            st.current.state_since_ms = now
            st.last_result = f"failed:{r}"
            self._append_recent_locked(st, result="failed", fail_reason=r, ended_ms=now)

    def mark_stopped(self, skill_id: str) -> None:
        sid = (skill_id or "").strip()
        now = mono_ms()
        with self._lock:
            st = self._ensure(sid)
            st.current.state = "STOPPED"
            st.current.state_since_ms = now
            st.last_result = "stopped"
            self._append_recent_locked(st, result="stopped", fail_reason="stopped", ended_ms=now)

    def _append_recent_locked(self, st: SkillStats, *, result: str, fail_reason: str, ended_ms: int) -> None:
        cur = st.current
        entry = AttemptLogEntry(
            attempt_id=cur.attempt_id or "",
            node_id=cur.node_id or "",
            start_mode=cur.start_mode or "",
            started_ms=int(cur.started_ms or 0),
            casting_ms=cur.casting_ms,
            ended_ms=int(ended_ms),
            retries=int(cur.retries or 0),
            readbar_ms=int(cur.readbar_ms or 0),
            result=result,
            fail_reason=fail_reason or "",
        )
        st.recent.insert(0, entry)
        if len(st.recent) > self._max_recent:
            del st.recent[self._max_recent :]

    # --- UI 快照 ---
    def snapshot_for_ui(self, ctx: ProfileContext, *, recent_limit: int = 25) -> List[Dict[str, object]]:
        skills_by_id = {s.id: s for s in (getattr(ctx.skills, "skills", []) or []) if getattr(s, "id", "")}
        now = mono_ms()

        with self._lock:
            out: List[Dict[str, object]] = []
            for sid, st in self._by_skill.items():
                s = skills_by_id.get(sid)
                name = (getattr(s, "name", "") or "") if s is not None else ""

                cur = st.current
                state = cur.state or "IDLE"
                state_age = int(now - int(cur.state_since_ms or now)) if int(cur.state_since_ms or 0) > 0 else 0

                recent = st.recent[: max(0, int(recent_limit))]
                recent_rows: List[Dict[str, object]] = []
                for e in recent:
                    dur = int(e.ended_ms - e.started_ms) if e.started_ms and e.ended_ms else 0
                    age = int(now - e.ended_ms) if e.ended_ms else 0
                    recent_rows.append(
                        {
                            "attempt_id": e.attempt_id,
                            "node_id": e.node_id,
                            "mode": e.start_mode,
                            "result": e.result,
                            "reason": e.fail_reason,
                            "retries": int(e.retries),
                            "readbar_ms": int(e.readbar_ms),
                            "duration_ms": dur,
                            "age_ms": age,
                        }
                    )

                out.append(
                    {
                        "skill_id": sid,
                        "skill_name": name,
                        "state": state,
                        "state_age_ms": state_age,
                        "node_exec": int(st.node_execution_count),
                        "ready_false": int(st.ready_false_count),
                        "skipped_lock": int(st.skipped_lock_busy),
                        "attempt": int(st.attempt_count),
                        "retry": int(st.retry_count_total),
                        "cast_start": int(st.cast_start_count),
                        "success": int(st.success_count),
                        "fail": int(st.fail_count),
                        "last_result": st.last_result or "",
                        "last_attempt_id": st.last_attempt_id or "",
                        "fail_by_reason": dict(st.fail_by_reason or {}),
                        "recent_attempts": recent_rows,
                    }
                )

        out.sort(key=lambda d: ((d.get("skill_name") or ""), (d.get("skill_id") or "")))
        return out


# -----------------------------
# NodeExecutor（保持原语义：ready=False 推进，下轮再来）
# -----------------------------

@dataclass
class NodeExecutor:
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

    start_signal_mode: str = "pixel"  # pixel/cast_bar/none
    start_timeout_ms: int = 20
    start_poll_ms: int = 10
    max_retries: int = 3
    retry_gap_ms: int = 30

    def mk_rt_ctx(self) -> RuntimeContext:
        plan = self.plan_getter()
        snap = self.scanner.capture_with_plan(plan)
        sc = SnapshotCapture(scanner=self.scanner, snapshot=snap)
        return RuntimeContext(profile=self.ctx, capture=sc, skill_state=self.skill_state)

    # ---------- cast_bar ----------
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

    # ---------- skill.pixel ready ----------
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

        # 严格：未取色视为不可判定
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
            self.skill_state.mark_stopped(sid)
            return mono_ms()

        if not bool(getattr(skill, "enabled", True)):
            self.skill_state.mark_skipped_disabled(sid)
            return mono_ms() + int(max(10, self.poll_not_ready_ms))

        # READY_CHECK：ready=False => 跳过并推进（下轮再来）
        rt_ctx = self.mk_rt_ctx()
        ready = self._is_skill_ready(skill, rt_ctx)

        if ready is None:
            self.skill_state.mark_skipped_not_ready(sid, "pixel_missing_or_unreadable")
            return mono_ms() + int(max(10, self.poll_not_ready_ms))

        if ready is False:
            self.skill_state.mark_skipped_not_ready(sid)
            return mono_ms() + int(max(10, self.poll_not_ready_ms))

        # 锁忙：跳过推进
        if not self.cast_lock.acquire(timeout=0):
            self.skill_state.mark_skipped_lock_busy(sid)
            return mono_ms() + int(max(10, self.poll_not_ready_ms))

        start_mode = (self.start_signal_mode or "pixel").strip().lower()
        readbar_ms = int(node.override_cast_ms or skill.cast.readbar_ms or 0)
        self.skill_state.begin_attempt(sid, node_id=(node.id or ""), start_mode=start_mode, readbar_ms=readbar_ms)

        try:
            retries_left = int(max(0, self.max_retries))

            def send_key_once() -> bool:
                key = (skill.trigger.key or "").strip()
                self.skill_state.inc_attempt_send_key(sid)
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
                if start_mode != "cast_bar":
                    return None
                pt = self._get_cast_bar_point()
                if pt is None:
                    return None
                base_ctx = self.mk_rt_ctx()
                return self._sample_point_rgb(base_ctx, pt)

            baseline = cast_bar_baseline_if_needed()
            if start_mode == "cast_bar" and baseline is None:
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
                if start_mode == "cast_bar" and baseline is None:
                    self.skill_state.mark_fail(sid, "cast_bar_unavailable")
                    return mono_ms() + int(max(10, self.poll_not_ready_ms))

                if not send_key_once():
                    return mono_ms() + int(max(10, self.poll_not_ready_ms))

                started = self._wait_cast_start(skill=skill, baseline_cast_bar=baseline)

            if self.stop_evt.is_set():
                self.skill_state.mark_stopped(sid)
                return mono_ms()

            if not started:
                self.skill_state.mark_fail(sid, "no_cast_start")
                return mono_ms() + int(max(10, self.poll_not_ready_ms))

            self.skill_state.mark_cast_started(sid)

            ok = self.cast_strategy.wait_for_complete(
                skill_id=sid,
                node_readbar_ms=readbar_ms,
                rt_ctx_factory=self.mk_rt_ctx,
                stop_evt=self.stop_evt,
            )

            if self.stop_evt.is_set():
                self.skill_state.mark_stopped(sid)
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