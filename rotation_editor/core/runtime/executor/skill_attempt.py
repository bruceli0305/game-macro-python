from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Optional, Dict, Set, Literal, Tuple, Any

from core.profiles import ProfileContext
from core.pick.capture import SampleSpec

from rotation_editor.core.runtime.keyboard import KeySender

from rotation_editor.ast import (
    Expr,
    Const,
    Not,
    PixelMatchSkill,
    PixelMatchPoint,
    CastBarChanged,
    DictBaselineProvider,
    TriBool,
    collect_probes_from_expr,
)
from rotation_editor.ast.codec import decode_expr

from rotation_editor.core.runtime.capture import CaptureManager
from rotation_editor.core.runtime.capture.eval_bridge import eval_expr_with_capture, ensure_plan_for_probes
from rotation_editor.core.runtime.state import StateStore
from rotation_editor.core.runtime.state.store import mono_ms

from .types import ExecutionResult
from .lock_policy import LockPolicyConfig, decide_on_lock_busy


StartSignalMode = Literal["pixel", "cast_bar", "none"]
CompletionPolicy = Literal["ASSUME_SUCCESS", "REQUIRE_SIGNAL", "HYBRID_ASSUME", "HYBRID_FAIL"]


@dataclass(frozen=True)
class StartSignalConfig:
    mode: StartSignalMode = "pixel"
    timeout_ms: int = 20
    poll_ms: int = 10
    max_retries: int = 3
    retry_gap_ms: int = 30

    cast_bar_point_id: str = ""
    cast_bar_tolerance: int = 15


@dataclass(frozen=True)
class CompleteSignalConfig:
    policy: CompletionPolicy = "ASSUME_SUCCESS"
    poll_ms: int = 30
    max_wait_factor: float = 1.5

    cast_bar_point_id: str = ""
    cast_bar_tolerance: int = 15


@dataclass(frozen=True)
class SkillAttemptConfig:
    default_gap_ms: int = 50
    poll_not_ready_ms: int = 50

    lock: LockPolicyConfig = LockPolicyConfig()

    start: StartSignalConfig = StartSignalConfig()
    complete: CompleteSignalConfig = CompleteSignalConfig()

    # 事件节流：start/complete 检测每隔多少 ms 记录一次
    sample_log_throttle_ms: int = 80


def _wait_ms(stop_evt: Optional[threading.Event], ms: int) -> bool:
    ms = int(ms)
    if ms <= 0:
        return bool(stop_evt and stop_evt.is_set())
    if stop_evt is None:
        import time
        time.sleep(ms / 1000.0)
        return False
    return bool(stop_evt.wait(ms / 1000.0))


def _clamp_int(v: int, lo: int, hi: int) -> int:
    x = int(v)
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


def _float_clamp(v: float, lo: float, hi: float) -> float:
    try:
        x = float(v)
    except Exception:
        x = float(lo)
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


class SkillAttemptExecutor:
    def __init__(
        self,
        *,
        ctx: ProfileContext,
        store: StateStore,
        key_sender: KeySender,
        cast_lock: threading.Lock,
        capman: CaptureManager,
        cfg: SkillAttemptConfig,
        stop_evt: Optional[threading.Event] = None,
    ) -> None:
        self._ctx = ctx
        self._store = store
        self._key_sender = key_sender
        self._lock = cast_lock
        self._capman = capman
        self._cfg = cfg
        self._stop_evt = stop_evt

    def exec_skill_node(
        self,
        *,
        skill_id: str,
        node_id: str,
        override_cast_ms: Optional[int] = None,

        # 节点级 expr JSON（来自 SkillNode.start_expr / complete_expr）
        node_start_expr_json: Any = None,
        node_complete_expr_json: Any = None,

        # 可选：直接传 Expr（用于上层预编译缓存）
        ready_expr: Optional[Expr] = None,
        start_expr: Optional[Expr] = None,
        complete_expr: Optional[Expr] = None,
    ) -> ExecutionResult:
        sid = (skill_id or "").strip()
        nid = (node_id or "").strip()

        self._store.mark_node_exec(sid, node_id=nid)

        if self._stop_evt is not None and self._stop_evt.is_set():
            return ExecutionResult(outcome="STOPPED", advance="HOLD", next_delay_ms=0, reason="stopped")

        skill = self._find_skill(sid)
        if skill is None:
            return ExecutionResult(outcome="ERROR", advance="ADVANCE", next_delay_ms=50, reason="skill_missing")

        if not bool(getattr(skill, "enabled", True)):
            self._store.mark_skipped_disabled(sid, node_id=nid)
            return ExecutionResult(outcome="SKIPPED_DISABLED", advance="ADVANCE", next_delay_ms=max(10, int(self._cfg.poll_not_ready_ms)), reason="disabled")

        # ---- derive default exprs (ready) ----
        ready_e = ready_expr or self._default_ready_expr(skill_id=sid)

        # ---- node-level expr JSON 优先（start/complete）----
        start_e = start_expr
        if start_e is None:
            start_e = self._decode_node_expr(node_start_expr_json, fallback=self._default_start_expr(skill_id=sid))

        complete_e = complete_expr
        if complete_e is None:
            default_ce = self._default_complete_expr()
            complete_e = self._decode_node_expr(node_complete_expr_json, fallback=default_ce)

        # ---- ensure plan ----
        probes = collect_probes_from_expr(ready_e)
        probes.merge(collect_probes_from_expr(start_e))
        probes.merge(collect_probes_from_expr(complete_e))
        ensure_plan_for_probes(capman=self._capman, probes=probes)

        # ---- READY_CHECK ----
        ready_tri = eval_expr_with_capture(ready_e, profile=self._ctx, capman=self._capman, metrics=self._store).tri
        if ready_tri.value is not True:
            reason = "not_ready" if ready_tri.value is False else (ready_tri.reason or "ready_unknown")
            self._store.mark_ready_false(sid, node_id=nid, reason=reason)
            return ExecutionResult(outcome="SKIPPED_NOT_READY", advance="ADVANCE", next_delay_ms=max(10, int(self._cfg.poll_not_ready_ms)), reason=reason)

        # ---- lock ----
        if not self._lock.acquire(timeout=0):
            self._store.mark_skipped_lock_busy(sid, node_id=nid)

            pol = (self._cfg.lock.policy or "SKIP_AND_ADVANCE").strip().upper()
            if pol == "WAIT_LOCK":
                return self._wait_lock_then_attempt(
                    skill=skill,
                    skill_id=sid,
                    node_id=nid,
                    override_cast_ms=override_cast_ms,
                    start_expr=start_e,
                    complete_expr=complete_e,
                )

            return decide_on_lock_busy(self._cfg.lock)

        try:
            return self._run_attempt_under_lock(
                skill=skill,
                skill_id=sid,
                node_id=nid,
                override_cast_ms=override_cast_ms,
                start_expr=start_e,
                complete_expr=complete_e,
            )
        finally:
            try:
                self._lock.release()
            except Exception:
                pass

    # -----------------------
    # Expr decode helper
    # -----------------------

    def _decode_node_expr(self, obj: Any, *, fallback: Optional[Expr]) -> Optional[Expr]:
        if obj is None:
            return fallback
        if not isinstance(obj, dict) or not obj:
            return fallback
        e, diags = decode_expr(obj, path="$")
        if e is None:
            return fallback
        return e

    # -----------------------
    # Helpers
    # -----------------------

    def _find_skill(self, skill_id: str):
        skills = getattr(self._ctx.skills, "skills", []) or []
        return next((s for s in skills if (getattr(s, "id", "") or "") == skill_id), None)

    def _default_ready_expr(self, *, skill_id: str) -> Expr:
        tol = self._tol_from_skill_pixel(skill_id)
        return PixelMatchSkill(skill_id=skill_id, tolerance=tol)

    def _default_start_expr(self, *, skill_id: str) -> Expr:
        mode = (self._cfg.start.mode or "pixel").strip().lower()
        if mode == "none":
            return Const(True)
        if mode == "cast_bar":
            pid, tol = self._get_cast_bar_point_for_start()
            return CastBarChanged(point_id=pid, tolerance=tol)
        tol = self._tol_from_skill_pixel(skill_id)
        return Not(PixelMatchSkill(skill_id=skill_id, tolerance=tol))

    def _default_complete_expr(self) -> Optional[Expr]:
        pol = (self._cfg.complete.policy or "ASSUME_SUCCESS").strip().upper()
        if pol == "ASSUME_SUCCESS":
            return None
        pid, tol = self._get_cast_bar_point_for_complete()
        if pid:
            return PixelMatchPoint(point_id=pid, tolerance=tol)
        return None

    def _tol_from_skill_pixel(self, skill_id: str) -> int:
        s = self._find_skill(skill_id)
        if s is None:
            return 0
        pix = getattr(s, "pixel", None)
        if pix is None:
            return 0
        try:
            tol = int(getattr(pix, "tolerance", 0) or 0)
        except Exception:
            tol = 0
        return _clamp_int(tol, 0, 255)

    def _get_cast_bar_point_for_start(self) -> Tuple[str, int]:
        pid = (self._cfg.start.cast_bar_point_id or "").strip()
        tol = _clamp_int(int(self._cfg.start.cast_bar_tolerance), 0, 255)
        if not pid:
            try:
                cb = getattr(self._ctx.base, "cast_bar", None)
                pid = (getattr(cb, "point_id", "") or "").strip() if cb is not None else ""
            except Exception:
                pid = ""
        try:
            cb = getattr(self._ctx.base, "cast_bar", None)
            if cb is not None:
                tol = _clamp_int(int(getattr(cb, "tolerance", tol) or tol), 0, 255)
        except Exception:
            pass
        return pid, tol

    def _get_cast_bar_point_for_complete(self) -> Tuple[str, int]:
        pid = (self._cfg.complete.cast_bar_point_id or "").strip()
        tol = _clamp_int(int(self._cfg.complete.cast_bar_tolerance), 0, 255)
        if not pid:
            try:
                cb = getattr(self._ctx.base, "cast_bar", None)
                pid = (getattr(cb, "point_id", "") or "").strip() if cb is not None else ""
            except Exception:
                pid = ""
        try:
            cb = getattr(self._ctx.base, "cast_bar", None)
            if cb is not None:
                tol = _clamp_int(int(getattr(cb, "tolerance", tol) or tol), 0, 255)
        except Exception:
            pass
        return pid, tol

    def _readbar_ms(self, skill, override_cast_ms: Optional[int]) -> int:
        if override_cast_ms is not None:
            try:
                v = int(override_cast_ms)
            except Exception:
                v = 0
            if v > 0:
                return v
        try:
            return int(getattr(getattr(skill, "cast", None), "readbar_ms", 0) or 0)
        except Exception:
            return 0

    def _extract_cast_bar_changed_points(self, expr: Expr) -> Set[str]:
        out: Set[str] = set()

        def walk(e: Expr) -> None:
            from rotation_editor.ast.nodes import And, Or, Not, CastBarChanged, Const
            if isinstance(e, And) or isinstance(e, Or):
                for c in e.children:
                    walk(c)
                return
            if isinstance(e, Not):
                walk(e.child)
                return
            if isinstance(e, Const):
                return
            if isinstance(e, CastBarChanged):
                pid = (e.point_id or "").strip()
                if pid:
                    out.add(pid)
                return

        walk(expr)
        return out

    def _sample_point_rgb_from_snapshot(self, point_id: str) -> Optional[Tuple[int, int, int]]:
        pid = (point_id or "").strip()
        if not pid:
            return None

        pts = getattr(self._ctx.points, "points", []) or []
        p = next((x for x in pts if (getattr(x, "id", "") or "") == pid), None)
        if p is None:
            return None

        snap_res = self._capman.get_snapshot()
        from rotation_editor.core.runtime.capture.manager import SnapshotOk
        if not isinstance(snap_res, SnapshotOk) or snap_res.snapshot is None:
            return None

        from rotation_editor.ast import SnapshotPixelSampler
        sampler = SnapshotPixelSampler(scanner=self._capman.get_scanner(), snapshot=snap_res.snapshot)

        try:
            sample = SampleSpec(mode=p.sample.mode, radius=int(p.sample.radius))
        except Exception:
            sample = SampleSpec(mode="single", radius=0)

        rgb = sampler.sample_rgb_abs(
            monitor_key=(getattr(p, "monitor", None) or "primary"),
            x_abs=int(getattr(p, "vx", 0)),
            y_abs=int(getattr(p, "vy", 0)),
            sample=sample,
            require_inside=False,
        )
        return rgb

    def _send_key(self, skill, attempt_id: str) -> bool:
        key = (getattr(getattr(skill, "trigger", None), "key", "") or "").strip()
        if not key:
            self._store.mark_key_sent_fail(attempt_id, "no_key")
            self._store.finish_fail(attempt_id, "no_key")
            return False

        try:
            self._key_sender.send_key(key)
        except Exception:
            self._store.mark_key_sent_fail(attempt_id, "send_key_error")
            self._store.finish_fail(attempt_id, "send_key_error")
            return False

        self._store.mark_key_sent_ok(attempt_id)
        return True

    def _wait_lock_then_attempt(
        self,
        *,
        skill,
        skill_id: str,
        node_id: str,
        override_cast_ms: Optional[int],
        start_expr: Expr,
        complete_expr: Optional[Expr],
    ) -> ExecutionResult:
        timeout = max(1, int(self._cfg.lock.wait_timeout_ms))
        poll = max(1, int(self._cfg.lock.wait_poll_ms))

        start = mono_ms()
        while True:
            if self._stop_evt is not None and self._stop_evt.is_set():
                return ExecutionResult(outcome="STOPPED", advance="HOLD", next_delay_ms=0, reason="stopped")

            if self._lock.acquire(timeout=0):
                try:
                    return self._run_attempt_under_lock(
                        skill=skill,
                        skill_id=skill_id,
                        node_id=node_id,
                        override_cast_ms=override_cast_ms,
                        start_expr=start_expr,
                        complete_expr=complete_expr,
                    )
                finally:
                    try:
                        self._lock.release()
                    except Exception:
                        pass

            now = mono_ms()
            if now - start >= timeout:
                return ExecutionResult(outcome="SKIPPED_LOCK_BUSY", advance="HOLD", next_delay_ms=max(10, int(self._cfg.lock.skip_delay_ms)), reason="wait_lock_timeout")
            _wait_ms(self._stop_evt, poll)

    def _run_attempt_under_lock(
        self,
        *,
        skill,
        skill_id: str,
        node_id: str,
        override_cast_ms: Optional[int],
        start_expr: Expr,
        complete_expr: Optional[Expr],
    ) -> ExecutionResult:
        readbar_ms = self._readbar_ms(skill, override_cast_ms)
        start_mode = (self._cfg.start.mode or "pixel").strip().lower()

        attempt_id = self._store.begin_attempt(skill_id=skill_id, node_id=node_id, start_mode=start_mode, readbar_ms=readbar_ms)
        self._store.set_stage(attempt_id, "PREPARING", message="preparing")

        retries_left = max(0, int(self._cfg.start.max_retries))
        retry_index = 0

        cast_bar_points_need_baseline = self._extract_cast_bar_changed_points(start_expr)

        while True:
            if self._stop_evt is not None and self._stop_evt.is_set():
                self._store.finish_stopped(attempt_id, "stopped")
                return ExecutionResult(outcome="STOPPED", advance="HOLD", next_delay_ms=0, reason="stopped")

            # baseline
            baseline_map: Dict[str, Tuple[int, int, int]] = {}
            baseline_ok: list[str] = []
            baseline_fail: list[str] = []
            if cast_bar_points_need_baseline:
                for pid in cast_bar_points_need_baseline:
                    rgb = self._sample_point_rgb_from_snapshot(pid)
                    if rgb is not None:
                        baseline_map[pid] = rgb
                        baseline_ok.append(pid)
                    else:
                        baseline_fail.append(pid)

                # 记录 baseline 采样事件
                self._store.append_attempt_event(
                    attempt_id,
                    type="BASELINE_SAMPLED",
                    message="baseline_sampled",
                    extra={
                        "ok": baseline_ok,
                        "fail": baseline_fail,
                    },
                )

            baseline_provider = DictBaselineProvider(baseline_map)

            # send key
            ok_key = self._send_key(skill, attempt_id)
            if not ok_key:
                return ExecutionResult(outcome="FAILED", advance="ADVANCE", next_delay_ms=max(10, int(self._cfg.poll_not_ready_ms)), reason="send_key_failed")

            if int(readbar_ms) <= 0:
                self._store.finish_success(attempt_id)
                return ExecutionResult(outcome="SUCCESS", advance="ADVANCE", next_delay_ms=max(0, int(self._cfg.default_gap_ms)), reason="instant")

            self._store.set_stage(attempt_id, "START_WAIT", message="start_wait")

            started = self._wait_start_signal(
                attempt_id=attempt_id,
                start_expr=start_expr,
                baseline=baseline_provider,
            )

            if started:
                self._store.mark_cast_started(attempt_id)
                ok_complete = self._wait_complete(attempt_id=attempt_id, readbar_ms=readbar_ms, complete_expr=complete_expr)
                if ok_complete:
                    self._store.finish_success(attempt_id)
                    return ExecutionResult(outcome="SUCCESS", advance="ADVANCE", next_delay_ms=max(0, int(self._cfg.default_gap_ms)), reason="success")
                return ExecutionResult(outcome="FAILED", advance="ADVANCE", next_delay_ms=max(10, int(self._cfg.poll_not_ready_ms)), reason="complete_failed")

            if retries_left > 0:
                retries_left -= 1
                retry_index += 1
                self._store.schedule_retry(attempt_id, retry_index=retry_index, reason="no_cast_start")
                _wait_ms(self._stop_evt, int(max(0, self._cfg.start.retry_gap_ms)))
                continue

            self._store.finish_fail(attempt_id, "no_cast_start")
            return ExecutionResult(outcome="FAILED", advance="ADVANCE", next_delay_ms=max(10, int(self._cfg.poll_not_ready_ms)), reason="no_cast_start")

    def _should_log(self, last_ms: int) -> bool:
        now = mono_ms()
        return (now - int(last_ms)) >= max(0, int(self._cfg.sample_log_throttle_ms))

    def _wait_start_signal(
        self,
        *,
        attempt_id: str,
        start_expr: Expr,
        baseline: DictBaselineProvider,
    ) -> bool:
        timeout_ms = max(1, int(self._cfg.start.timeout_ms))
        poll = max(5, int(self._cfg.start.poll_ms))
        deadline = mono_ms() + timeout_ms

        last_log_ms = 0

        while mono_ms() < deadline:
            if self._stop_evt is not None and self._stop_evt.is_set():
                self._store.finish_stopped(attempt_id, "stopped")
                return False

            out = eval_expr_with_capture(
                start_expr,
                profile=self._ctx,
                capman=self._capman,
                metrics=self._store,
                baseline=baseline,
            )

            # 节流记录 start_check
            if self._should_log(last_log_ms):
                last_log_ms = mono_ms()
                self._store.append_attempt_event(
                    attempt_id,
                    type="START_CHECK",
                    message="start_check",
                    detail=out.tri.reason or "",
                    extra={
                        "tri": out.tri.value,
                        "snapshot_age_ms": int(out.snapshot_age_ms),
                        "capture_error": out.capture_error,
                        "capture_detail": out.capture_detail,
                    },
                )

            if out.tri.value is True:
                self._store.append_attempt_event(attempt_id, type="START_OBSERVED", message="start_observed")
                return True

            _wait_ms(self._stop_evt, poll)

        return False

    def _wait_complete(
        self,
        *,
        attempt_id: str,
        readbar_ms: int,
        complete_expr: Optional[Expr],
    ) -> bool:
        pol = (self._cfg.complete.policy or "ASSUME_SUCCESS").strip().upper()
        poll = max(10, int(self._cfg.complete.poll_ms))
        factor = _float_clamp(float(self._cfg.complete.max_wait_factor), 0.1, 10.0)

        max_wait_ms = int(max(1, int(readbar_ms) * factor))
        if max_wait_ms <= 0:
            max_wait_ms = max(500, int(readbar_ms))

        if pol == "ASSUME_SUCCESS":
            self._store.set_stage(attempt_id, "COMPLETE_WAIT", message="complete_wait_assume")
            if _wait_ms(self._stop_evt, int(max(0, readbar_ms))):
                self._store.finish_stopped(attempt_id, "stopped")
                return False
            return True

        if complete_expr is None:
            if pol == "HYBRID_ASSUME":
                self._store.set_stage(attempt_id, "COMPLETE_WAIT", message="complete_wait_no_expr_fallback_assume")
                if _wait_ms(self._stop_evt, int(max(0, readbar_ms))):
                    self._store.finish_stopped(attempt_id, "stopped")
                    return False
                return True
            self._store.finish_fail(attempt_id, "complete_signal_missing")
            return False

        self._store.set_stage(attempt_id, "COMPLETE_WAIT", message="complete_wait_signal")

        last_log_ms = 0
        deadline = mono_ms() + max_wait_ms
        while mono_ms() < deadline:
            if self._stop_evt is not None and self._stop_evt.is_set():
                self._store.finish_stopped(attempt_id, "stopped")
                return False

            out = eval_expr_with_capture(
                complete_expr,
                profile=self._ctx,
                capman=self._capman,
                metrics=self._store,
                baseline=None,
            )

            # 节流记录 complete_check
            if self._should_log(last_log_ms):
                last_log_ms = mono_ms()
                self._store.append_attempt_event(
                    attempt_id,
                    type="COMPLETE_CHECK",
                    message="complete_check",
                    detail=out.tri.reason or "",
                    extra={
                        "tri": out.tri.value,
                        "snapshot_age_ms": int(out.snapshot_age_ms),
                        "capture_error": out.capture_error,
                        "capture_detail": out.capture_detail,
                    },
                )

            if out.tri.value is True:
                self._store.append_attempt_event(attempt_id, type="COMPLETE_OBSERVED", message="complete_observed")
                return True

            _wait_ms(self._stop_evt, poll)

        if pol == "HYBRID_ASSUME":
            return True

        self._store.finish_fail(attempt_id, "timeout")
        return False