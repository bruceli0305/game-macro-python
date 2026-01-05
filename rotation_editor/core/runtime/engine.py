from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional, Protocol, Dict, List, Tuple

from core.profiles import ProfileContext
from core.pick.capture import ScreenCapture
from core.pick.scanner import PixelScanner

from rotation_editor.core.models import RotationPreset, Track, SkillNode, GatewayNode, Condition
from rotation_editor.core.runtime.context import RuntimeContext
from rotation_editor.core.runtime.skill_state import SkillState as SkillStateProto
from rotation_editor.core.runtime.cast_strategies import CastCompletionStrategy, make_cast_strategy
from rotation_editor.core.runtime.keyboard import KeySender, PynputKeySender
from rotation_editor.core.runtime.capture_plan import build_capture_plan
from rotation_editor.core.runtime.condition_eval import eval_condition

log = logging.getLogger(__name__)


def mono_ms() -> int:
    return int(time.monotonic() * 1000)


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
    stop_on_error: bool = True


@dataclass
class ExecutionCursor:
    preset_id: str
    mode_id: Optional[str]
    track_id: str
    node_index: int


class SimpleSkillState(SkillStateProto):
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
    将 PixelScanner 的 snapshot 伪装成 get_rgb_scoped_abs 接口，供条件评估与施法条策略复用。
    注意：不依赖 ScreenCapture 的 mss（不会创建新 mss 实例）。
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


# -----------------------------
# 全局轨道状态（环形，忽略 step）
# -----------------------------

@dataclass
class GlobalTrackState:
    track_id: str
    next_time_ms: int
    node_index: int = 0

    def advance(self, track: Track) -> None:
        if not track.nodes:
            self.node_index = 0
            return
        self.node_index += 1
        if self.node_index >= len(track.nodes):
            self.node_index = 0

    def jump_to(self, track: Track, node_index: int) -> None:
        if not track.nodes:
            self.node_index = 0
            return
        try:
            idx = int(node_index)
        except Exception:
            idx = 0
        if idx < 0 or idx >= len(track.nodes):
            idx = 0
        self.node_index = idx


# -----------------------------
# 模式轨道状态（线性，cycle 结束后 reset）
# -----------------------------

@dataclass
class ModeTrackState:
    track_order: int
    track_id: str
    order: List[int]
    pos: int
    next_time_ms: int

    def done(self) -> bool:
        return (not self.order) or self.pos >= len(self.order)

    def current_node_index(self) -> int:
        if self.done():
            return -1
        if self.pos < 0:
            self.pos = 0
        if self.pos >= len(self.order):
            self.pos = len(self.order)
            return -1
        return int(self.order[self.pos])

    def advance(self) -> None:
        if self.done():
            self.pos = len(self.order)
            return
        self.pos += 1
        if self.pos > len(self.order):
            self.pos = len(self.order)

    def reset(self) -> None:
        self.pos = 0

    def jump_to_node_index(self, node_index: int) -> None:
        if not self.order:
            self.pos = 0
            return
        try:
            idx = int(node_index)
        except Exception:
            idx = 0
        try:
            self.pos = self.order.index(idx)
        except ValueError:
            self.pos = 0


@dataclass
class ModeRuntimeState:
    mode_id: str
    current_step: int
    tracks: Dict[str, ModeTrackState]

    def has_tracks(self) -> bool:
        return bool(self.tracks)

    def all_done(self) -> bool:
        if not self.tracks:
            return True
        return all(st.done() for st in self.tracks.values())


class MacroEngine:
    """
    第五步：ScreenCapture 统一化 + 动作语义对齐完整实现版

    - 全局：并行、环形、忽略 step
    - 模式：并行、线性、按 step 同步推进，cycle 结束 reset
    - stop 可中断：sleep / pause / cast_strategy 等待
    - capture 统一：引擎内只创建一个 ScreenCapture，plan/scanner 共用
    - Gateway 动作：end / switch_mode / jump_track / jump_node（与 UI 对齐）
    """

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

    # ---------- 生命周期 ----------

    def is_running(self) -> bool:
        return self._running

    def start(self, preset: RotationPreset) -> None:
        if self._running:
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

    # ---------- 暂停 / 单步 ----------

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

    # ---------- 查找 ----------

    def _find_global_track(self, preset: RotationPreset, track_id: str) -> Optional[Track]:
        tid = (track_id or "").strip()
        if not tid:
            return None
        for t in preset.global_tracks or []:
            if (t.id or "").strip() == tid:
                return t
        return None

    def _find_mode(self, preset: RotationPreset, mode_id: str):
        mid = (mode_id or "").strip()
        if not mid:
            return None
        for m in preset.modes or []:
            if (m.id or "").strip() == mid:
                return m
        return None

    def _find_mode_track(self, preset: RotationPreset, mode_id: str, track_id: str) -> Optional[Track]:
        mode = self._find_mode(preset, mode_id)
        if mode is None:
            return None
        tid = (track_id or "").strip()
        if not tid:
            return None
        for t in mode.tracks or []:
            if (t.id or "").strip() == tid:
                return t
        return None

    def _select_entry_mode_id(self, preset: RotationPreset) -> Optional[str]:
        em = (preset.entry_mode_id or "").strip()
        if em and self._find_mode(preset, em) is not None:
            return em

        for m in preset.modes or []:
            if (m.id or "").strip() and (m.tracks or []):
                return (m.id or "").strip()
        return None

    # ---------- step/order ----------

    @staticmethod
    def _node_step(n) -> int:
        try:
            s = int(getattr(n, "step_index", 0) or 0)
        except Exception:
            s = 0
        return max(0, s)

    @staticmethod
    def _node_order_in_step(n) -> int:
        try:
            o = int(getattr(n, "order_in_step", 0) or 0)
        except Exception:
            o = 0
        return max(0, o)

    # ---------- 构建 mode state ----------

    def _build_mode_state(self, preset: RotationPreset, mode_id: str) -> Optional[ModeRuntimeState]:
        mode = self._find_mode(preset, mode_id)
        if mode is None:
            return None

        now = mono_ms()
        tracks_state: Dict[str, ModeTrackState] = {}

        for t_order, t in enumerate(mode.tracks or []):
            tid = (t.id or "").strip()
            if not tid:
                continue
            if not t.nodes:
                continue

            idxs = list(range(len(t.nodes)))
            idxs.sort(key=lambda i: (self._node_step(t.nodes[i]), self._node_order_in_step(t.nodes[i]), i))

            tracks_state[tid] = ModeTrackState(
                track_order=int(t_order),
                track_id=tid,
                order=idxs,
                pos=0,
                next_time_ms=now,
            )

        if not tracks_state:
            return None

        min_step = None
        for tid, st in tracks_state.items():
            tr = self._find_mode_track(preset, mode_id, tid)
            if tr is None or not tr.nodes:
                continue
            ni = st.current_node_index()
            if ni < 0 or ni >= len(tr.nodes):
                continue
            s = self._node_step(tr.nodes[ni])
            min_step = s if min_step is None else min(min_step, s)

        return ModeRuntimeState(mode_id=(mode.id or "").strip(), current_step=int(min_step or 0), tracks=tracks_state)

    def _reset_mode_cycle(self, preset: RotationPreset, ms: ModeRuntimeState) -> None:
        for st in ms.tracks.values():
            st.reset()

        min_step = None
        for tid, st in ms.tracks.items():
            tr = self._find_mode_track(preset, ms.mode_id, tid)
            if tr is None or not tr.nodes:
                continue
            ni = st.current_node_index()
            if ni < 0 or ni >= len(tr.nodes):
                continue
            s = self._node_step(tr.nodes[ni])
            min_step = s if min_step is None else min(min_step, s)

        ms.current_step = int(min_step if min_step is not None else 0)

    def _ensure_mode_step_runnable(self, preset: RotationPreset, ms: ModeRuntimeState) -> None:
        if not ms.tracks:
            return

        if ms.all_done():
            self._reset_mode_cycle(preset, ms)
            return

        while True:
            any_in_step = False
            min_next: Optional[int] = None

            for tid, st in ms.tracks.items():
                if st.done():
                    continue
                tr = self._find_mode_track(preset, ms.mode_id, tid)
                if tr is None or not tr.nodes:
                    continue
                ni = st.current_node_index()
                if ni < 0 or ni >= len(tr.nodes):
                    continue
                s = self._node_step(tr.nodes[ni])

                if s == ms.current_step:
                    any_in_step = True
                min_next = s if min_next is None else min(min_next, s)

            if any_in_step:
                return

            if min_next is None or min_next == ms.current_step:
                return

            ms.current_step = int(min_next)

    def _maybe_backstep(self, preset: RotationPreset, ms: ModeRuntimeState, track_id: str, st: ModeTrackState) -> None:
        """
        若某次 jump 使某轨道的当前节点 step 更小，则允许回退 current_step。
        """
        tr = self._find_mode_track(preset, ms.mode_id, track_id)
        if tr is None or not tr.nodes:
            return
        ni = st.current_node_index()
        if ni < 0 or ni >= len(tr.nodes):
            return
        s = self._node_step(tr.nodes[ni])
        if s < ms.current_step:
            ms.current_step = int(s)

    # ---------- 执行：技能 ----------

    def _exec_skill_node(
        self,
        *,
        node: SkillNode,
        cursor: ExecutionCursor,
        cast_strategy: CastCompletionStrategy,
        rt_ctx_factory: Callable[[], RuntimeContext],
        skill_state: SimpleSkillState,
    ) -> int:
        skills = getattr(self._ctx.skills, "skills", []) or []
        skill = next((s for s in skills if s.id == node.skill_id), None)
        if skill is None:
            return mono_ms() + 50

        key = (skill.trigger.key or "").strip()
        if key:
            try:
                self._key_sender.send_key(key)
            except Exception:
                log.exception("send_key failed")

        skill_state.record_cast(skill.id)

        readbar_ms = int(node.override_cast_ms or skill.cast.readbar_ms or 0)

        cast_strategy.wait_for_complete(
            skill_id=skill.id,
            node_readbar_ms=readbar_ms,
            rt_ctx_factory=rt_ctx_factory,
            stop_evt=self._stop_evt,
        )

        return mono_ms() + int(self._cfg.default_skill_gap_ms)

    # ---------- 条件 ----------

    def _find_condition_in_preset(self, preset: RotationPreset, cond_id: str) -> Optional[Condition]:
        cid = (cond_id or "").strip()
        if not cid:
            return None
        for c in preset.conditions or []:
            if (c.id or "").strip() == cid:
                return c
        return None

    def _gateway_condition_ok(
        self,
        *,
        preset: RotationPreset,
        node: GatewayNode,
        rt_ctx_factory: Callable[[], RuntimeContext],
    ) -> bool:
        cond_id = (node.condition_id or "").strip()
        if not cond_id:
            return True
        cond = self._find_condition_in_preset(preset, cond_id)
        if cond is None:
            return False
        try:
            rt_ctx = rt_ctx_factory()
            return bool(eval_condition(cond, rt_ctx))
        except Exception:
            log.exception("eval_condition failed (condition_id=%s)", cond_id)
            return False

    # ---------- 主循环 ----------

    def _run_loop(self, preset: RotationPreset) -> None:
        cap = ScreenCapture()          # 统一 capture 实例
        scanner = PixelScanner(cap)    # scanner 复用 capture

        try:
            plan = build_capture_plan(self._ctx, preset, capture=cap)
            self._capture_plan_dirty = False

            cast_strategy = make_cast_strategy(self._ctx, default_gap_ms=self._cfg.default_skill_gap_ms)
            skill_state = SimpleSkillState()

            # 全局轨道：并行、环形
            global_states: Dict[str, GlobalTrackState] = {}
            now = mono_ms()
            for t in preset.global_tracks or []:
                tid = (t.id or "").strip()
                if not tid or not t.nodes:
                    continue
                global_states[tid] = GlobalTrackState(track_id=tid, next_time_ms=now, node_index=0)

            # 模式轨道：并行、线性、按 step
            mode_state: Optional[ModeRuntimeState] = None
            entry_mode_id = self._select_entry_mode_id(preset)
            if entry_mode_id:
                mode_state = self._build_mode_state(preset, entry_mode_id)

            if not global_states and mode_state is None:
                self._emit_error("没有可用轨道", "Preset 下没有任何可执行的全局轨道或模式轨道")
                return

            start_ms_all = mono_ms()
            exec_nodes = 0

            while not self._stop_evt.is_set():
                if self._paused and not self._step_once:
                    self._stop_evt.wait(self._cfg.poll_interval_ms / 1000.0)
                    continue

                now = mono_ms()

                # 安全限制
                if getattr(preset, "max_run_seconds", 0) > 0:
                    if now - start_ms_all >= int(preset.max_run_seconds) * 1000:
                        self._stop_reason = "max_run_seconds"
                        self._stop_evt.set()
                        break

                if getattr(preset, "max_exec_nodes", 0) > 0 and exec_nodes >= int(preset.max_exec_nodes):
                    self._stop_reason = "max_exec_nodes"
                    self._stop_evt.set()
                    break

                # 重建 CapturePlan（复用 cap）
                if self._capture_plan_dirty:
                    try:
                        plan = build_capture_plan(self._ctx, preset, capture=cap)
                    except Exception:
                        log.exception("rebuild capture_plan failed")
                    self._capture_plan_dirty = False

                def mk_rt_ctx() -> RuntimeContext:
                    snap = scanner.capture_with_plan(plan)
                    sc = SnapshotCapture(scanner=scanner, snapshot=snap)
                    return RuntimeContext(profile=self._ctx, capture=sc, skill_state=skill_state)

                if mode_state is not None:
                    self._ensure_mode_step_runnable(preset, mode_state)
                    if not mode_state.has_tracks():
                        mode_state = None

                # 计算下一次可执行时间
                next_times: List[int] = []
                for st in global_states.values():
                    next_times.append(int(st.next_time_ms))

                if mode_state is not None:
                    for tid, st in mode_state.tracks.items():
                        if st.done():
                            continue
                        tr = self._find_mode_track(preset, mode_state.mode_id, tid)
                        if tr is None or not tr.nodes:
                            continue
                        ni = st.current_node_index()
                        if ni < 0 or ni >= len(tr.nodes):
                            continue
                        if self._node_step(tr.nodes[ni]) == mode_state.current_step:
                            next_times.append(int(st.next_time_ms))

                if not next_times:
                    break

                min_next = min(next_times)
                if now < min_next:
                    sleep_ms = min(self._cfg.poll_interval_ms, min_next - now)
                    self._stop_evt.wait(sleep_ms / 1000.0)
                    continue

                # 候选：global 优先
                candidates: List[Tuple[str, int, str]] = []
                for tid, st in global_states.items():
                    if now >= int(st.next_time_ms):
                        candidates.append(("global", int(st.next_time_ms), tid))

                if mode_state is not None:
                    for tid, st in mode_state.tracks.items():
                        if st.done():
                            continue
                        tr = self._find_mode_track(preset, mode_state.mode_id, tid)
                        if tr is None or not tr.nodes:
                            continue
                        ni = st.current_node_index()
                        if ni < 0 or ni >= len(tr.nodes):
                            continue
                        if self._node_step(tr.nodes[ni]) != mode_state.current_step:
                            continue
                        if now >= int(st.next_time_ms):
                            candidates.append(("mode", int(st.next_time_ms), tid))

                if not candidates:
                    self._stop_evt.wait(self._cfg.poll_interval_ms / 1000.0)
                    continue

                candidates.sort(key=lambda x: (x[1], 0 if x[0] == "global" else 1))
                kind, _t, tid = candidates[0]

                if self._stop_evt.is_set():
                    break

                # -----------------------------
                # 执行：全局
                # -----------------------------
                if kind == "global":
                    tr = self._find_global_track(preset, tid)
                    st = global_states.get(tid)
                    if tr is None or st is None or not tr.nodes:
                        global_states.pop(tid, None)
                        continue

                    idx = int(st.node_index)
                    if idx < 0 or idx >= len(tr.nodes):
                        idx = 0
                        st.node_index = 0

                    node = tr.nodes[idx]
                    cursor_before = ExecutionCursor(preset_id=preset.id or "", mode_id=None, track_id=tid, node_index=idx)

                    try:
                        if isinstance(node, SkillNode):
                            st.next_time_ms = self._exec_skill_node(
                                node=node,
                                cursor=cursor_before,
                                cast_strategy=cast_strategy,
                                rt_ctx_factory=mk_rt_ctx,
                                skill_state=skill_state,
                            )
                            st.advance(tr)

                        elif isinstance(node, GatewayNode):
                            ok = self._gateway_condition_ok(preset=preset, node=node, rt_ctx_factory=mk_rt_ctx)
                            if not ok:
                                st.advance(tr)
                                st.next_time_ms = mono_ms() + 10
                            else:
                                action = (node.action or "switch_mode").strip().lower() or "switch_mode"

                                if action == "end":
                                    self._stop_reason = "gateway_end"
                                    self._stop_evt.set()
                                    st.next_time_ms = mono_ms() + 10

                                elif action == "jump_node":
                                    tgt = node.target_node_index if node.target_node_index is not None else 0
                                    st.jump_to(tr, int(tgt))
                                    st.next_time_ms = mono_ms() + 10

                                elif action == "switch_mode":
                                    target_mode = (node.target_mode_id or "").strip()
                                    if target_mode:
                                        ms2 = self._build_mode_state(preset, target_mode)
                                        if ms2 is not None:
                                            mode_state = ms2
                                    # 消费网关，避免反复触发
                                    st.advance(tr)
                                    st.next_time_ms = mono_ms() + 10

                                elif action == "jump_track":
                                    # 全局域 jump_track：只允许控制全局轨道（不跨模式）
                                    if (node.target_mode_id or "").strip():
                                        # 语义清晰：从全局去模式请用 switch_mode
                                        st.advance(tr)
                                        st.next_time_ms = mono_ms() + 10
                                    else:
                                        target_track = (node.target_track_id or "").strip()
                                        if target_track and target_track in global_states:
                                            tr2 = self._find_global_track(preset, target_track)
                                            st2 = global_states.get(target_track)
                                            if tr2 is not None and st2 is not None and tr2.nodes:
                                                tgt_idx = node.target_node_index if node.target_node_index is not None else 0
                                                st2.jump_to(tr2, int(tgt_idx))
                                                st2.next_time_ms = mono_ms() + 10
                                        # 当前网关也消费
                                        st.advance(tr)
                                        st.next_time_ms = mono_ms() + 10

                                else:
                                    st.advance(tr)
                                    st.next_time_ms = mono_ms() + 10

                        else:
                            st.advance(tr)
                            st.next_time_ms = mono_ms() + 10

                    except Exception as e:
                        log.exception("global node execution failed")
                        self._emit_error("节点执行失败", str(e))
                        if self._cfg.stop_on_error:
                            raise
                        st.next_time_ms = mono_ms() + 200

                    self._emit_node_executed(cursor_before, node)
                    exec_nodes += 1

                # -----------------------------
                # 执行：模式
                # -----------------------------
                else:
                    if mode_state is None:
                        continue

                    st = mode_state.tracks.get(tid)
                    tr = self._find_mode_track(preset, mode_state.mode_id, tid)
                    if st is None or tr is None or not tr.nodes:
                        mode_state.tracks.pop(tid, None)
                        continue
                    if st.done():
                        continue

                    idx = st.current_node_index()
                    if idx < 0 or idx >= len(tr.nodes):
                        st.advance()
                        continue

                    node = tr.nodes[idx]
                    cursor_before = ExecutionCursor(
                        preset_id=preset.id or "",
                        mode_id=mode_state.mode_id,
                        track_id=tid,
                        node_index=int(idx),
                    )

                    try:
                        if isinstance(node, SkillNode):
                            st.next_time_ms = self._exec_skill_node(
                                node=node,
                                cursor=cursor_before,
                                cast_strategy=cast_strategy,
                                rt_ctx_factory=mk_rt_ctx,
                                skill_state=skill_state,
                            )
                            st.advance()

                        elif isinstance(node, GatewayNode):
                            ok = self._gateway_condition_ok(preset=preset, node=node, rt_ctx_factory=mk_rt_ctx)
                            if not ok:
                                # 条件不满足：网关视为被消费，顺序前进
                                st.advance()
                                st.next_time_ms = mono_ms() + 10
                            else:
                                action = (node.action or "switch_mode").strip().lower() or "switch_mode"

                                if action == "end":
                                    self._stop_reason = "gateway_end"
                                    self._stop_evt.set()
                                    st.next_time_ms = mono_ms() + 10

                                elif action == "jump_node":
                                    tgt = node.target_node_index if node.target_node_index is not None else 0
                                    st.jump_to_node_index(int(tgt))
                                    self._maybe_backstep(preset, mode_state, tid, st)
                                    st.next_time_ms = mono_ms() + 10

                                elif action == "switch_mode":
                                    target_mode = (node.target_mode_id or "").strip()
                                    if target_mode:
                                        ms2 = self._build_mode_state(preset, target_mode)
                                        if ms2 is not None:
                                            mode_state = ms2

                                elif action == "jump_track":
                                    target_mode = (node.target_mode_id or "").strip()
                                    if target_mode and target_mode != mode_state.mode_id:
                                        # 跨模式：语义清晰用 switch_mode
                                        ms2 = self._build_mode_state(preset, target_mode)
                                        if ms2 is not None:
                                            mode_state = ms2
                                    else:
                                        target_track = (node.target_track_id or "").strip()
                                        if target_track and target_track in mode_state.tracks:
                                            st2 = mode_state.tracks.get(target_track)
                                            tr2 = self._find_mode_track(preset, mode_state.mode_id, target_track)
                                            if st2 is not None and tr2 is not None and tr2.nodes:
                                                tgt_idx = node.target_node_index if node.target_node_index is not None else 0
                                                st2.jump_to_node_index(int(tgt_idx))
                                                st2.next_time_ms = mono_ms() + 10
                                                self._maybe_backstep(preset, mode_state, target_track, st2)

                                        # 当前网关消费一次，避免反复触发
                                        st.advance()
                                        st.next_time_ms = mono_ms() + 10

                                else:
                                    st.advance()
                                    st.next_time_ms = mono_ms() + 10

                        else:
                            st.advance()
                            st.next_time_ms = mono_ms() + 10

                    except Exception as e:
                        log.exception("mode node execution failed")
                        self._emit_error("节点执行失败", str(e))
                        if self._cfg.stop_on_error:
                            raise
                        st.next_time_ms = mono_ms() + 200

                    self._emit_node_executed(cursor_before, node)
                    exec_nodes += 1

                # 单步：执行一次后回到暂停
                if self._step_once:
                    self._paused = True
                    self._step_once = False

        finally:
            # 尝试关闭当前线程 mss 句柄（可选但建议）
            try:
                cap.close_current_thread()
            except Exception:
                pass

            self._running = False
            self._paused = False
            self._step_once = False

            try:
                reason = self._stop_reason
            except Exception:
                reason = "finished"

            self._sch.call_soon(lambda r=reason: self._cb.on_stopped(r))

    # ---------- 回调封装 ----------

    def _emit_error(self, msg: str, detail: str) -> None:
        self._sch.call_soon(lambda: self._cb.on_error(msg, detail))

    def _emit_node_executed(self, cursor: ExecutionCursor, node) -> None:
        self._sch.call_soon(lambda: self._cb.on_node_executed(cursor, node))