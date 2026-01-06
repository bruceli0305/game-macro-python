from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable, Optional, Protocol, Any, Dict

from core.profiles import ProfileContext

from rotation_editor.core.models import RotationPreset, SkillNode, GatewayNode, Condition
from rotation_editor.core.runtime.keyboard import KeySender, PynputKeySender

from rotation_editor.core.runtime.state import StateStore
from rotation_editor.core.runtime.capture import CaptureManager, StateStoreCaptureSink
from rotation_editor.core.runtime.executor.skill_attempt import SkillAttemptExecutor, SkillAttemptConfig

from rotation_editor.ast.codec import decode_expr
from rotation_editor.ast import collect_probes_from_expr
from rotation_editor.ast.nodes import And, Or, Not, Const, SkillMetricGE
from rotation_editor.core.runtime.capture.eval_bridge import eval_expr_with_capture, ensure_plan_for_probes

from rotation_editor.core.services.validation_service import ValidationService

from .runtime_state import (
    build_global_runtime,
    build_mode_runtime,
    find_track_in_preset,
    track_has_node,
    GlobalRuntimeState,
    ModeRuntimeState,
)
from .scheduler import Scheduler
from .executor.types import ExecutionResult


class SchedulerLike(Protocol):
    def call_soon(self, fn: Callable[[], None]) -> None: ...


class EngineCallbacks(Protocol):
    def on_started(self, preset_id: str) -> None: ...
    def on_stopped(self, reason: str) -> None: ...
    def on_error(self, msg: str, detail: str) -> None: ...
    def on_node_executed(self, cursor, node) -> None: ...


@dataclass(frozen=True)
class ExecutionCursor:
    preset_id: str
    mode_id: Optional[str]
    track_id: str
    node_index: int


@dataclass
class EngineConfig:
    poll_interval_ms: int = 20
    stop_on_error: bool = True
    gateway_poll_delay_ms: int = 10


class MacroEngineNew:
    def __init__(
        self,
        *,
        ctx: ProfileContext,
        scheduler: SchedulerLike,
        callbacks: EngineCallbacks,
        store: Optional[StateStore] = None,
        key_sender: Optional[KeySender] = None,
        config: Optional[EngineConfig] = None,
        attempt_cfg: Optional[SkillAttemptConfig] = None,
    ) -> None:
        self._ctx = ctx
        self._sch = scheduler
        self._cb = callbacks
        self._cfg = config or EngineConfig()

        self._store = store or StateStore()
        self._key_sender = key_sender or PynputKeySender()

        self._stop_evt = threading.Event()
        self._paused = False
        self._step_once = False
        self._stop_reason = "finished"

        self._thread: Optional[threading.Thread] = None

        self._cast_lock = threading.Lock()
        self._capman = CaptureManager(ctx=self._ctx, sink=StateStoreCaptureSink(store=self._store))
        self._attempt_exec = SkillAttemptExecutor(
            ctx=self._ctx,
            store=self._store,
            key_sender=self._key_sender,
            cast_lock=self._cast_lock,
            capman=self._capman,
            cfg=attempt_cfg or SkillAttemptConfig(),
            stop_evt=self._stop_evt,
        )

        self._scheduler = Scheduler()

        self._global_rt: Optional[GlobalRuntimeState] = None
        self._active_mode_id: Optional[str] = None
        self._mode_rt: Optional[ModeRuntimeState] = None

        self._validator = ValidationService()

    @property
    def store(self) -> StateStore:
        return self._store

    def is_running(self) -> bool:
        th = self._thread
        return bool(th is not None and th.is_alive())

    def start(self, preset: RotationPreset) -> None:
        if self.is_running():
            return

        report = self._validator.validate_preset(preset, ctx=self._ctx)
        if report.has_errors():
            detail = report.format_text(max_lines=80)
            self._sch.call_soon(lambda d=detail: self._cb.on_error("循环方案校验失败，已拒绝启动", d))
            return

        # 预热 capture plan（减少启动后第一帧延迟；并让 capture 错误尽早出现在事件流）
        try:
            ensure_plan_for_probes(capman=self._capman, probes=report.probes)
        except Exception:
            pass

        self._stop_evt.clear()
        self._paused = False
        self._step_once = False
        self._stop_reason = "finished"

        self._thread = threading.Thread(target=self._run_loop, args=(preset,), daemon=True)
        self._thread.start()

    def stop(self, reason: str = "user_stop") -> None:
        if not self.is_running():
            return
        self._stop_reason = reason
        self._store.engine_stopping(reason)
        self._stop_evt.set()
        th = self._thread
        if th is not None:
            try:
                th.join(timeout=0.2)
            except Exception:
                pass

    def pause(self) -> None:
        if not self.is_running():
            return
        self._paused = True
        self._step_once = False
        self._store.engine_paused()

    def resume(self) -> None:
        if not self.is_running():
            return
        self._paused = False
        self._step_once = False
        self._store.engine_resumed()

    def step(self) -> None:
        if not self.is_running():
            return
        self._paused = True
        self._step_once = True
        self._store.engine_paused()

    # ---------------- internal ----------------

    def _emit_started(self, preset_id: str) -> None:
        self._sch.call_soon(lambda: self._cb.on_started(preset_id))

    def _emit_stopped(self, reason: str) -> None:
        self._sch.call_soon(lambda: self._cb.on_stopped(reason))

    def _emit_error(self, msg: str, detail: str) -> None:
        self._sch.call_soon(lambda: self._cb.on_error(msg, detail))

    def _emit_node(self, cursor: ExecutionCursor, node: Any) -> None:
        self._sch.call_soon(lambda: self._cb.on_node_executed(cursor, node))

    def _now(self) -> int:
        from rotation_editor.core.runtime.state.store import mono_ms as _mono
        return int(_mono())

    def _ensure_mode_runtime(self, preset: RotationPreset, mode_id: str, *, now_ms: int) -> Optional[ModeRuntimeState]:
        mid = (mode_id or "").strip()
        if not mid:
            return None
        if self._mode_rt is not None and (self._mode_rt.mode_id or "").strip() == mid:
            return self._mode_rt
        self._mode_rt = build_mode_runtime(preset, mid, now_ms=now_ms)
        self._active_mode_id = mid if self._mode_rt is not None else None
        return self._mode_rt

    def _apply_entry(self, preset: RotationPreset, *, now_ms: int) -> None:
        self._global_rt = build_global_runtime(preset, now_ms=now_ms)

        entry = preset.entry
        scope = (entry.scope or "global").strip().lower()
        mode_id = (entry.mode_id or "").strip()
        track_id = (entry.track_id or "").strip()
        node_id = (entry.node_id or "").strip()

        if scope == "global":
            self._active_mode_id = None
            self._mode_rt = None
            rt = self._global_rt.get(track_id) if self._global_rt is not None else None
            if rt is not None:
                rt.jump_to_node_id(node_id)
                rt.next_time_ms = int(now_ms)
            return

        self._ensure_mode_runtime(preset, mode_id, now_ms=now_ms)
        if self._mode_rt is None:
            return
        rt2 = self._mode_rt.tracks.get(track_id)
        if rt2 is not None:
            rt2.jump_to_node_id(node_id)
            rt2.next_time_ms = int(now_ms)
            self._mode_rt.maybe_backstep(track_id)

    # ---------------- Gateway condition (AST) ----------------

    def _load_gateway_condition_expr(self, preset: RotationPreset, gw: GatewayNode) -> Optional[dict]:
        try:
            ce = getattr(gw, "condition_expr", None)
        except Exception:
            ce = None
        if isinstance(ce, dict) and ce:
            return ce

        cid = (getattr(gw, "condition_id", "") or "").strip()
        if not cid:
            return None
        c = next((x for x in (preset.conditions or []) if (getattr(x, "id", "") or "").strip() == cid), None)
        if c is None:
            return None
        expr = getattr(c, "expr", None)
        if isinstance(expr, dict) and expr:
            return expr
        return None

    def _gateway_condition_ok(self, preset: RotationPreset, gw: GatewayNode) -> bool:
        has_inline = False
        try:
            has_inline = isinstance(getattr(gw, "condition_expr", None), dict)
        except Exception:
            has_inline = False
        cid = (getattr(gw, "condition_id", "") or "").strip()
        if not cid and not has_inline:
            return True

        expr_json = self._load_gateway_condition_expr(preset, gw)
        if not isinstance(expr_json, dict) or not expr_json:
            return False

        expr, _diags = decode_expr(expr_json, path="$")
        if expr is None:
            return False

        probes = collect_probes_from_expr(expr)
        ensure_plan_for_probes(capman=self._capman, probes=probes)

        out = eval_expr_with_capture(expr, profile=self._ctx, capman=self._capman, metrics=self._store, baseline=None)
        return out.tri.value is True

    # ---------------- Engine loop ----------------

    def _run_loop(self, preset: RotationPreset) -> None:
        preset_id = (preset.id or "").strip()
        self._store.engine_started(preset_id)
        self._emit_started(preset_id)

        try:
            now = self._now()
            self._apply_entry(preset, now_ms=now)

            global_rt = self._global_rt
            if global_rt is None:
                self._emit_error("引擎内部错误", "global_rt is None")
                self._stop_reason = "internal_error"
                return

            if not global_rt.tracks and (self._mode_rt is None or not self._mode_rt.has_tracks()):
                self._emit_error("没有可执行轨道", "global_tracks 为空，且入口模式也没有可执行轨道")
                self._stop_reason = "no_tracks"
                return

            start_ms = self._now()
            exec_nodes = 0

            while not self._stop_evt.is_set():
                if self._paused and not self._step_once:
                    self._stop_evt.wait(self._cfg.poll_interval_ms / 1000.0)
                    continue

                now = self._now()

                if getattr(preset, "max_run_seconds", 0) > 0:
                    if now - start_ms >= int(preset.max_run_seconds) * 1000:
                        self._stop_reason = "max_run_seconds"
                        self._stop_evt.set()
                        break

                if getattr(preset, "max_exec_nodes", 0) > 0 and exec_nodes >= int(preset.max_exec_nodes):
                    self._stop_reason = "max_exec_nodes"
                    self._stop_evt.set()
                    break

                item = self._scheduler.choose_next(now_ms=now, global_rt=global_rt, mode_rt=self._mode_rt)
                if item is None:
                    wake = self._scheduler.next_wakeup_ms(global_rt=global_rt, mode_rt=self._mode_rt)
                    if wake is None:
                        break
                    if now < wake:
                        sleep_ms = min(int(self._cfg.poll_interval_ms), int(wake - now))
                        self._stop_evt.wait(sleep_ms / 1000.0)
                    else:
                        self._stop_evt.wait(self._cfg.poll_interval_ms / 1000.0)
                    continue

                if item.scope == "global":
                    rt = global_rt.get(item.track_id)
                    if rt is None or not rt.track.nodes:
                        global_rt.remove(item.track_id)
                        continue
                    node = rt.current_node()
                    idx = rt.current_node_index()
                    if node is None or idx < 0:
                        global_rt.remove(item.track_id)
                        continue

                    cursor = ExecutionCursor(preset_id=preset_id, mode_id=None, track_id=item.track_id, node_index=idx)
                    self._exec_one_node(preset=preset, scope="global", track_id=item.track_id, node=node, node_index=idx, now_ms=now)
                    self._emit_node(cursor, node)
                    exec_nodes += 1

                else:
                    if self._mode_rt is None:
                        continue
                    self._mode_rt.ensure_step_runnable()
                    rt = self._mode_rt.tracks.get(item.track_id)
                    if rt is None or not rt.track.nodes:
                        self._mode_rt.tracks.pop(item.track_id, None)
                        continue
                    if rt.done():
                        continue
                    node = rt.current_node()
                    idx = rt.current_node_index()
                    if node is None or idx < 0:
                        rt.advance()
                        continue

                    cursor = ExecutionCursor(preset_id=preset_id, mode_id=self._mode_rt.mode_id, track_id=item.track_id, node_index=idx)
                    self._exec_one_node(preset=preset, scope="mode", track_id=item.track_id, node=node, node_index=idx, now_ms=now)
                    self._emit_node(cursor, node)
                    exec_nodes += 1

                if self._step_once:
                    self._paused = True
                    self._step_once = False

        except Exception as e:
            self._store.engine_error("engine_crash", str(e))
            self._emit_error("引擎异常退出", str(e))
            if self._cfg.stop_on_error:
                self._stop_reason = "error"
                self._stop_evt.set()
        finally:
            try:
                self._capman.close_current_thread()
            except Exception:
                pass

            reason = self._stop_reason or "finished"
            self._store.engine_stopped(reason)
            self._emit_stopped(reason)

    # ---------------- Execute one node ----------------

    def _exec_one_node(
        self,
        *,
        preset: RotationPreset,
        scope: str,
        track_id: str,
        node: Any,
        node_index: int,
        now_ms: int,
    ) -> None:
        if isinstance(node, SkillNode):
            res: ExecutionResult = self._attempt_exec.exec_skill_node(
                skill_id=(node.skill_id or "").strip(),
                node_id=(node.id or "").strip(),
                override_cast_ms=node.override_cast_ms,
                node_start_expr_json=getattr(node, "start_expr", None),
                node_complete_expr_json=getattr(node, "complete_expr", None),
            )
            self._apply_exec_result(scope=scope, track_id=track_id, res=res, now_ms=now_ms)
            return

        if isinstance(node, GatewayNode):
            self._exec_gateway(preset=preset, scope=scope, track_id=track_id, gw=node, now_ms=now_ms)
            return

        self._apply_exec_result(
            scope=scope,
            track_id=track_id,
            res=ExecutionResult(outcome="ERROR", advance="ADVANCE", next_delay_ms=int(self._cfg.gateway_poll_delay_ms), reason="unknown_node"),
            now_ms=now_ms,
        )

    def _apply_exec_result(
        self,
        *,
        scope: str,
        track_id: str,
        res: ExecutionResult,
        now_ms: int,
    ) -> None:
        global_rt = self._global_rt
        if global_rt is None:
            return

        if res.outcome == "STOPPED":
            self._stop_reason = "stopped"
            self._stop_evt.set()
            return

        delay = int(max(0, res.next_delay_ms))

        if scope == "global":
            rt = global_rt.get(track_id)
            if rt is None:
                return
            rt.next_time_ms = int(now_ms + delay)
            if res.advance == "ADVANCE":
                rt.advance()
            return

        if self._mode_rt is None:
            return
        rt2 = self._mode_rt.tracks.get(track_id)
        if rt2 is None:
            return
        rt2.next_time_ms = int(now_ms + delay)
        if res.advance == "ADVANCE":
            rt2.advance()
            self._mode_rt.ensure_step_runnable()

    # ---------------- Gateway actions ----------------

    def _exec_gateway(
        self,
        *,
        preset: RotationPreset,
        scope: str,
        track_id: str,
        gw: GatewayNode,
        now_ms: int,
    ) -> None:
        if not self._gateway_condition_ok(preset, gw):
            self._apply_exec_result(
                scope=scope,
                track_id=track_id,
                res=ExecutionResult(outcome="ERROR", advance="ADVANCE", next_delay_ms=int(self._cfg.gateway_poll_delay_ms), reason="gw_cond_false"),
                now_ms=now_ms,
            )
            return

        # 条件已成立：若配置了 reset_metrics_on_fire，则重置条件中涉及的所有 skill_metric 计数
        self._reset_metrics_for_gateway(preset, gw)

        act = (getattr(gw, "action", "") or "switch_mode").strip().lower() or "switch_mode"

        if act == "end":
            self._stop_reason = "gateway_end"
            self._stop_evt.set()
            return

        if act == "switch_mode":
            target_mode = (getattr(gw, "target_mode_id", "") or "").strip()
            if not target_mode:
                self._apply_exec_result(
                    scope=scope,
                    track_id=track_id,
                    res=ExecutionResult(outcome="ERROR", advance="ADVANCE", next_delay_ms=int(self._cfg.gateway_poll_delay_ms), reason="gw_switch_mode_missing"),
                    now_ms=now_ms,
                )
                return

            new_rt = self._ensure_mode_runtime(preset, target_mode, now_ms=now_ms)
            if new_rt is None or not new_rt.has_tracks():
                self._apply_exec_result(
                    scope=scope,
                    track_id=track_id,
                    res=ExecutionResult(outcome="ERROR", advance="ADVANCE", next_delay_ms=int(self._cfg.gateway_poll_delay_ms), reason="gw_switch_mode_failed"),
                    now_ms=now_ms,
                )
                return

            tgt_track = (getattr(gw, "target_track_id", "") or "").strip()
            tgt_node = (getattr(gw, "target_node_id", "") or "").strip()
            if tgt_track and tgt_node:
                rt = new_rt.tracks.get(tgt_track)
                if rt is not None:
                    rt.jump_to_node_id(tgt_node)
                    rt.next_time_ms = int(now_ms + int(self._cfg.gateway_poll_delay_ms))
                    new_rt.maybe_backstep(tgt_track)

            self._apply_exec_result(
                scope=scope,
                track_id=track_id,
                res=ExecutionResult(outcome="ERROR", advance="ADVANCE", next_delay_ms=int(self._cfg.gateway_poll_delay_ms), reason="gw_switch_mode_consume"),
                now_ms=now_ms,
            )
            return

        if act == "jump_node":
            target_node_id = (getattr(gw, "target_node_id", "") or "").strip()
            if not target_node_id:
                self._apply_exec_result(
                    scope=scope,
                    track_id=track_id,
                    res=ExecutionResult(outcome="ERROR", advance="ADVANCE", next_delay_ms=int(self._cfg.gateway_poll_delay_ms), reason="gw_jump_node_no_target"),
                    now_ms=now_ms,
                )
                return

            self._jump_same_scope(scope=scope, track_id=track_id, node_id=target_node_id)
            self._set_next_time(scope=scope, track_id=track_id, next_time_ms=now_ms + int(self._cfg.gateway_poll_delay_ms))
            return

        if act == "jump_track":
            target_mode = (getattr(gw, "target_mode_id", "") or "").strip()
            target_track = (getattr(gw, "target_track_id", "") or "").strip()
            target_node = (getattr(gw, "target_node_id", "") or "").strip()

            if not target_track or not target_node:
                self._apply_exec_result(
                    scope=scope,
                    track_id=track_id,
                    res=ExecutionResult(outcome="ERROR", advance="ADVANCE", next_delay_ms=int(self._cfg.gateway_poll_delay_ms), reason="gw_jump_track_missing_target"),
                    now_ms=now_ms,
                )
                return

            if target_mode:
                mrt = self._ensure_mode_runtime(preset, target_mode, now_ms=now_ms)
                if mrt is None:
                    self._apply_exec_result(
                        scope=scope,
                        track_id=track_id,
                        res=ExecutionResult(outcome="ERROR", advance="ADVANCE", next_delay_ms=int(self._cfg.gateway_poll_delay_ms), reason="gw_jump_track_bad_mode"),
                        now_ms=now_ms,
                    )
                    return

                self_mode = self._mode_rt.mode_id if self._mode_rt is not None else ""
                if scope == "mode" and self._mode_rt is not None and self_mode == target_mode and (track_id or "") == target_track:
                    self._jump_mode_track(target_track, target_node)
                    self._set_next_time(scope="mode", track_id=target_track, next_time_ms=now_ms + int(self._cfg.gateway_poll_delay_ms))
                    return

                self._jump_mode_track(target_track, target_node)
                self._set_next_time(scope="mode", track_id=target_track, next_time_ms=now_ms + int(self._cfg.gateway_poll_delay_ms))

                self._apply_exec_result(
                    scope=scope,
                    track_id=track_id,
                    res=ExecutionResult(outcome="ERROR", advance="ADVANCE", next_delay_ms=int(self._cfg.gateway_poll_delay_ms), reason="gw_jump_track_consume"),
                    now_ms=now_ms,
                )
                return

            if (target_track or "") == (track_id or ""):
                self._jump_same_scope(scope=scope, track_id=track_id, node_id=target_node)
                self._set_next_time(scope=scope, track_id=track_id, next_time_ms=now_ms + int(self._cfg.gateway_poll_delay_ms))
                return

            self._jump_same_scope(scope=scope, track_id=target_track, node_id=target_node)
            self._set_next_time(scope=scope, track_id=target_track, next_time_ms=now_ms + int(self._cfg.gateway_poll_delay_ms))

            self._apply_exec_result(
                scope=scope,
                track_id=track_id,
                res=ExecutionResult(outcome="ERROR", advance="ADVANCE", next_delay_ms=int(self._cfg.gateway_poll_delay_ms), reason="gw_jump_track_consume"),
                now_ms=now_ms,
            )
            return

        if act == "exec_skill":
            # 条件已成立，尝试执行指定技能（不做模式跳转）
            exec_sid = (getattr(gw, "exec_skill_id", "") or "").strip()
            if not exec_sid:
                # 理论上 ValidationService 应已阻止；这里防御性处理
                self._apply_exec_result(
                    scope=scope,
                    track_id=track_id,
                    res=ExecutionResult(
                        outcome="ERROR",
                        advance="ADVANCE",
                        next_delay_ms=int(self._cfg.gateway_poll_delay_ms),
                        reason="gw_exec_skill_no_id",
                    ),
                    now_ms=now_ms,
                )
                return

            # 使用 SkillAttemptExecutor 执行该技能：
            # - skill_id 按 exec_skill_id
            # - node_id 用网关自身 id，便于在调试里区分这是“网关触发”的技能
            res = self._attempt_exec.exec_skill_node(
                skill_id=exec_sid,
                node_id=(getattr(gw, "id", "") or "").strip(),
                override_cast_ms=None,
                node_start_expr_json=None,
                node_complete_expr_json=None,
            )
            self._apply_exec_result(
                scope=scope,
                track_id=track_id,
                res=res,
                now_ms=now_ms,
            )
            return

        self._apply_exec_result(
            scope=scope,
            track_id=track_id,
            res=ExecutionResult(outcome="ERROR", advance="ADVANCE", next_delay_ms=int(self._cfg.gateway_poll_delay_ms), reason=f"gw_unknown_action:{act}"),
            now_ms=now_ms,
        )

    def _jump_same_scope(self, *, scope: str, track_id: str, node_id: str) -> None:
        tid = (track_id or "").strip()
        nid = (node_id or "").strip()
        if not tid or not nid:
            return

        if scope == "global":
            rt = self._global_rt.get(tid) if self._global_rt is not None else None
            if rt is not None:
                rt.jump_to_node_id(nid)
            return

        if self._mode_rt is None:
            return
        rt2 = self._mode_rt.tracks.get(tid)
        if rt2 is None:
            return
        if rt2.jump_to_node_id(nid):
            self._mode_rt.maybe_backstep(tid)

    def _jump_mode_track(self, track_id: str, node_id: str) -> None:
        if self._mode_rt is None:
            return
        tid = (track_id or "").strip()
        nid = (node_id or "").strip()
        if not tid or not nid:
            return
        rt = self._mode_rt.tracks.get(tid)
        if rt is None:
            return
        if rt.jump_to_node_id(nid):
            self._mode_rt.maybe_backstep(tid)

    def _set_next_time(self, *, scope: str, track_id: str, next_time_ms: int) -> None:
        tid = (track_id or "").strip()
        if not tid:
            return
        if scope == "global":
            rt = self._global_rt.get(tid) if self._global_rt is not None else None
            if rt is not None:
                rt.next_time_ms = int(next_time_ms)
            return
        if self._mode_rt is None:
            return
        rt2 = self._mode_rt.tracks.get(tid)
        if rt2 is not None:
            rt2.next_time_ms = int(next_time_ms)
            
    def get_skill_stats_snapshot(self):
        """
        给 UI 调试面板使用：返回 StateStore 的技能快照。
        """
        try:
            return self._store.snapshot_skills(ctx=self._ctx)
        except Exception:
            return []


    def is_cast_locked(self) -> bool:
        """
        给 UI 调试面板显示施法锁状态。
        """
        try:
            return bool(self._cast_lock.locked())
        except Exception:
            return False
            
    def invalidate_capture_plan(self) -> None:
        """
        供 UI 在 points/skills/rotations 变更时显式刷新 capture plan。
        - 调用 CaptureManager.invalidate_plan()
        - 若失败仅记录日志，不抛到 UI
        """
        import logging

        try:
            self._capman.invalidate_plan()
        except Exception:
            logging.getLogger(__name__).exception("invalidate_capture_plan failed")

    def get_engine_state_snapshot(self) -> Dict[str, Any]:
        """
        给 UI 调试面板使用：返回 StateStore 的引擎状态快照。
        字段包括：
            running / paused / preset_id / started_ms / stop_reason /
            last_error / last_error_detail
        """
        try:
            return self._store.get_engine_state()
        except Exception:
            return {}

    def _reset_metrics_for_gateway(self, preset: RotationPreset, gw: GatewayNode) -> None:
        """
        若 gw.reset_metrics_on_fire=True，则解析其条件 AST，
        找出其中所有 SkillMetricGE(skill_id, metric)，并重置对应计数。

        - 使用 condition_expr（内联）优先；
        - 若无内联，则使用 condition_id 引用的 Condition.expr。
        """
        if not getattr(gw, "reset_metrics_on_fire", False):
            return

        expr_json = self._load_gateway_condition_expr(preset, gw)
        if not isinstance(expr_json, dict) or not expr_json:
            return

        expr, _diags = decode_expr(expr_json, path="$.gateway.condition")
        if expr is None:
            return

        pairs: set[tuple[str, str]] = set()

        def walk(e) -> None:
            if isinstance(e, (And, Or)):
                for c in e.children:
                    walk(c)
                return
            if isinstance(e, Not):
                walk(e.child)
                return
            if isinstance(e, SkillMetricGE):
                sid = (e.skill_id or "").strip()
                metric = str(e.metric or "").strip().lower()
                if sid and metric:
                    pairs.add((sid, metric))
                return
            # 其它节点（Const, PixelMatchPoint, PixelMatchSkill, CastBarChanged 等）忽略

        walk(expr)

        for sid, metric in pairs:
            try:
                # 类型上 metric 是 str，但 SkillMetric 是 Literal[str]，这里忽略类型检查
                self._store.reset_metric(sid, metric)  # type: ignore[arg-type]
            except Exception:
                # 重置失败不应该中断引擎流程，最多记个日志（按需）
                pass

MacroEngine = MacroEngineNew