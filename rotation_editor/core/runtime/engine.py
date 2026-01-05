from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Callable, Optional, Protocol, List, Tuple, Dict, Any

from core.profiles import ProfileContext
from core.pick.capture import ScreenCapture
from core.pick.scanner import PixelScanner

from rotation_editor.core.models import RotationPreset, SkillNode, GatewayNode

from rotation_editor.core.runtime.keyboard import KeySender, PynputKeySender
from rotation_editor.core.runtime.capture_plan import build_capture_plan
from rotation_editor.core.runtime.cast_strategies import make_cast_strategy

from rotation_editor.core.runtime.clock import mono_ms
from rotation_editor.core.runtime.state import GlobalRuntime, ModeRuntime
from rotation_editor.core.runtime.executor import NodeExecutor, SimpleSkillState
from rotation_editor.core.runtime.gateway_actions import apply_gateway_global, apply_gateway_mode
from rotation_editor.core.runtime.validation import PresetValidator

log = logging.getLogger(__name__)


class Scheduler(Protocol):
    def call_soon(self, fn: Callable[[], None]) -> None: ...


class EngineCallbacks(Protocol):
    def on_started(self, preset_id: str) -> None: ...
    def on_stopped(self, reason: str) -> None: ...
    def on_node_executed(self, cursor, node) -> None: ...
    def on_error(self, msg: str, detail: str) -> None: ...


@dataclass
class EngineConfig:
    poll_interval_ms: int = 20
    default_skill_gap_ms: int = 50

    poll_not_ready_ms: int = 50

    start_signal_mode: str = "pixel"  # pixel / cast_bar / none
    start_timeout_ms: int = 20
    start_poll_ms: int = 10
    max_retries: int = 3
    retry_gap_ms: int = 30

    stop_on_error: bool = True


@dataclass
class ExecutionCursor:
    preset_id: str
    mode_id: Optional[str]
    track_id: str
    node_index: int


class MacroEngine:
    def __init__(
        self,
        *,
        ctx: ProfileContext,
        scheduler: Scheduler,
        callbacks: EngineCallbacks,
        key_sender: Optional[KeySender] = None,
        config: Optional[EngineConfig] = None,
    ) -> None:
        self._ctx = ctx
        self._sch = scheduler
        self._cb = callbacks
        self._cfg = config or EngineConfig()
        self._key_sender = key_sender or PynputKeySender()

        self._thread: Optional[threading.Thread] = None
        self._stop_evt = threading.Event()
        self._running = False

        self._paused: bool = False
        self._step_once: bool = False
        self._stop_reason: str = "finished"

        self._capture_plan_dirty: bool = False

        # 调试面板数据源
        self._cast_lock = threading.Lock()
        self._skill_state: Optional[SimpleSkillState] = None

    # ---- debug API ----
    def get_skill_stats_snapshot(self) -> List[Dict[str, Any]]:
        ss = self._skill_state
        if ss is None:
            return []
        try:
            return ss.snapshot_for_ui(self._ctx)
        except Exception:
            return []

    def is_cast_locked(self) -> bool:
        try:
            return bool(self._cast_lock.locked())
        except Exception:
            return False

    # ---------- 生命周期 ----------
    def is_running(self) -> bool:
        return self._running

    def start(self, preset: RotationPreset) -> None:
        if self._running:
            return

        issues = PresetValidator().validate(preset, ctx=self._ctx)
        if issues:
            lines = []
            for it in issues[:40]:
                lines.append(f"- [{it.code}] {it.location}: {it.message}" + (f" ({it.detail})" if it.detail else ""))
            if len(issues) > 40:
                lines.append(f"... 还有 {len(issues) - 40} 条错误")
            detail = "\n".join(lines)
            self._sch.call_soon(lambda d=detail: self._cb.on_error("循环方案校验失败，已拒绝启动", d))
            return

        self._stop_evt.clear()
        self._stop_reason = "finished"
        self._thread = threading.Thread(target=self._run_loop, args=(preset,), daemon=True)
        self._running = True
        self._thread.start()
        self._sch.call_soon(lambda: self._cb.on_started(preset.id or ""))

    def stop(self, reason: str = "user_stop") -> None:
        if not self._running:
            return
        self._stop_reason = reason
        self._stop_evt.set()
        th = self._thread
        self._thread = None
        if th is not None:
            try:
                th.join(timeout=0.5)
            except Exception:
                log.exception("MacroEngine thread join failed")

    def pause(self) -> None:
        if not self._running:
            return
        self._paused = True
        self._step_once = False

    def resume(self) -> None:
        if not self._running:
            return
        self._paused = False
        self._step_once = False

    def step(self) -> None:
        if not self._running:
            return
        self._step_once = True

    def invalidate_capture_plan(self) -> None:
        self._capture_plan_dirty = True

    # ---------- 内部：模式入口 ----------
    def _select_entry_mode_id(self, preset: RotationPreset) -> Optional[str]:
        em = (preset.entry_mode_id or "").strip()
        if em:
            for m in preset.modes or []:
                if (m.id or "").strip() == em and (m.tracks or []):
                    return em
        for m in preset.modes or []:
            if (m.id or "").strip() and (m.tracks or []):
                return (m.id or "").strip()
        return None

    def _build_mode_rt(self, preset: RotationPreset, mode_id: str, now: int) -> Optional[ModeRuntime]:
        mid = (mode_id or "").strip()
        if not mid:
            return None
        mode = next((m for m in (preset.modes or []) if (m.id or "").strip() == mid), None)
        if mode is None:
            return None
        return ModeRuntime(mode_id=mid, tracks=list(mode.tracks or []), now_ms=int(now))

    # ---------- 主循环 ----------
    def _run_loop(self, preset: RotationPreset) -> None:
        cap = ScreenCapture()
        scanner = PixelScanner(cap)

        plan = None

        def set_stop_reason(r: str) -> None:
            self._stop_reason = r

        try:
            plan = build_capture_plan(self._ctx, preset, capture=cap)
            self._capture_plan_dirty = False

            cast_strategy = make_cast_strategy(self._ctx, default_gap_ms=self._cfg.default_skill_gap_ms)
            skill_state = SimpleSkillState()
            self._skill_state = skill_state  # 供 UI 读取

            def get_plan():
                return plan

            executor = NodeExecutor(
                ctx=self._ctx,
                key_sender=self._key_sender,
                cast_strategy=cast_strategy,
                skill_state=skill_state,
                scanner=scanner,
                plan_getter=get_plan,
                stop_evt=self._stop_evt,
                cast_lock=self._cast_lock,
                default_skill_gap_ms=int(self._cfg.default_skill_gap_ms),
                poll_not_ready_ms=int(self._cfg.poll_not_ready_ms),
                start_signal_mode=str(self._cfg.start_signal_mode or "pixel"),
                start_timeout_ms=int(self._cfg.start_timeout_ms),
                start_poll_ms=int(self._cfg.start_poll_ms),
                max_retries=int(self._cfg.max_retries),
                retry_gap_ms=int(self._cfg.retry_gap_ms),
            )

            global_rt = GlobalRuntime(list(preset.global_tracks or []), now_ms=mono_ms())

            mode_rt: Optional[ModeRuntime] = None
            entry_mode_id = self._select_entry_mode_id(preset)
            if entry_mode_id:
                mode_rt = self._build_mode_rt(preset, entry_mode_id, mono_ms())

            if not global_rt.has_tracks() and mode_rt is None:
                self._emit_error("没有可用轨道", "Preset 下没有任何可执行的全局轨道或模式轨道")
                return

            start_ms = mono_ms()
            exec_nodes = 0

            while not self._stop_evt.is_set():
                if self._paused and not self._step_once:
                    self._stop_evt.wait(self._cfg.poll_interval_ms / 1000.0)
                    continue

                now = mono_ms()

                if getattr(preset, "max_run_seconds", 0) > 0:
                    if now - start_ms >= int(preset.max_run_seconds) * 1000:
                        self._stop_reason = "max_run_seconds"
                        self._stop_evt.set()
                        break

                if getattr(preset, "max_exec_nodes", 0) > 0 and exec_nodes >= int(preset.max_exec_nodes):
                    self._stop_reason = "max_exec_nodes"
                    self._stop_evt.set()
                    break

                if self._capture_plan_dirty:
                    try:
                        plan = build_capture_plan(self._ctx, preset, capture=cap)
                    except Exception:
                        log.exception("rebuild capture_plan failed")
                    self._capture_plan_dirty = False

                if mode_rt is not None:
                    mode_rt.ensure_step_runnable()
                    if not mode_rt.has_tracks():
                        mode_rt = None

                next_times: List[int] = []
                next_times.extend(global_rt.all_next_times())
                if mode_rt is not None:
                    next_times.extend(mode_rt.eligible_next_times())

                if not next_times:
                    break

                min_next = min(next_times)
                if now < min_next:
                    sleep_ms = min(self._cfg.poll_interval_ms, min_next - now)
                    self._stop_evt.wait(sleep_ms / 1000.0)
                    continue

                candidates: List[Tuple[str, int, str]] = []
                for nt, tid in global_rt.ready_candidates(now):
                    candidates.append(("global", nt, tid))
                if mode_rt is not None:
                    for nt, tid in mode_rt.ready_candidates(now):
                        candidates.append(("mode", nt, tid))

                if not candidates:
                    self._stop_evt.wait(self._cfg.poll_interval_ms / 1000.0)
                    continue

                candidates.sort(key=lambda x: (x[1], 0 if x[0] == "global" else 1))
                kind, _nt, tid = candidates[0]

                if self._stop_evt.is_set():
                    break

                if kind == "global":
                    tr = global_rt.get_track(tid)
                    st = global_rt.get_state(tid)
                    if tr is None or st is None or not tr.nodes:
                        global_rt.remove_track(tid)
                        continue

                    idx = int(st.node_index)
                    if idx < 0 or idx >= len(tr.nodes):
                        idx = 0
                        st.node_index = 0

                    node = tr.nodes[idx]
                    cursor = ExecutionCursor(preset_id=preset.id or "", mode_id=None, track_id=tid, node_index=idx)

                    try:
                        if isinstance(node, SkillNode):
                            st.next_time_ms = executor.exec_skill_node(node)
                            st.advance(tr)  # ready=False 也推进（符合需求）
                        elif isinstance(node, GatewayNode):
                            ok = executor.gateway_condition_ok(preset, node)
                            if not ok:
                                st.advance(tr)
                                st.next_time_ms = mono_ms() + 10
                            else:
                                mode_rt = apply_gateway_global(
                                    node=node,
                                    current_track_id=tid,
                                    global_rt=global_rt,
                                    mode_rt=mode_rt,
                                    build_mode_rt=lambda mid: self._build_mode_rt(preset, mid, mono_ms()),
                                    stop_evt=self._stop_evt,
                                    set_stop_reason=set_stop_reason,
                                )
                        else:
                            st.advance(tr)
                            st.next_time_ms = mono_ms() + 10

                    except Exception as e:
                        log.exception("global node execution failed")
                        self._emit_error("节点执行失败", str(e))
                        if self._cfg.stop_on_error:
                            raise
                        st.next_time_ms = mono_ms() + 200

                    self._emit_node_executed(cursor, node)
                    exec_nodes += 1

                else:
                    if mode_rt is None:
                        continue
                    st = mode_rt.states.get(tid)
                    tr = mode_rt.tracks_by_id.get(tid)
                    if st is None or tr is None or not tr.nodes:
                        mode_rt.states.pop(tid, None)
                        mode_rt.tracks_by_id.pop(tid, None)
                        continue
                    if st.done():
                        continue

                    idx = st.current_node_index()
                    if idx < 0 or idx >= len(tr.nodes):
                        st.advance()
                        continue

                    node = tr.nodes[idx]
                    cursor = ExecutionCursor(preset_id=preset.id or "", mode_id=mode_rt.mode_id, track_id=tid, node_index=idx)

                    try:
                        if isinstance(node, SkillNode):
                            st.next_time_ms = executor.exec_skill_node(node)
                            st.advance()  # ready=False 也推进（符合需求）
                        elif isinstance(node, GatewayNode):
                            ok = executor.gateway_condition_ok(preset, node)
                            if not ok:
                                st.advance()
                                st.next_time_ms = mono_ms() + 10
                            else:
                                mode_rt = apply_gateway_mode(
                                    node=node,
                                    current_track_id=tid,
                                    mode_rt=mode_rt,
                                    build_mode_rt=lambda mid: self._build_mode_rt(preset, mid, mono_ms()),
                                    stop_evt=self._stop_evt,
                                    set_stop_reason=set_stop_reason,
                                )
                        else:
                            st.advance()
                            st.next_time_ms = mono_ms() + 10

                    except Exception as e:
                        log.exception("mode node execution failed")
                        self._emit_error("节点执行失败", str(e))
                        if self._cfg.stop_on_error:
                            raise
                        st.next_time_ms = mono_ms() + 200

                    self._emit_node_executed(cursor, node)
                    exec_nodes += 1

                if self._step_once:
                    self._paused = True
                    self._step_once = False

        finally:
            try:
                cap.close_current_thread()
            except Exception:
                pass

            self._running = False
            self._paused = False
            self._step_once = False

            reason = self._stop_reason or "finished"
            self._sch.call_soon(lambda r=reason: self._cb.on_stopped(r))

    def _emit_error(self, msg: str, detail: str) -> None:
        self._sch.call_soon(lambda: self._cb.on_error(msg, detail))

    def _emit_node_executed(self, cursor: ExecutionCursor, node) -> None:
        self._sch.call_soon(lambda: self._cb.on_node_executed(cursor, node))