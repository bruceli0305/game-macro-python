from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional, Protocol

from core.profiles import ProfileContext
from core.pick.capture import ScreenCapture
from core.pick.scanner import PixelScanner

from rotation_editor.core.models import RotationPreset, Track, SkillNode, GatewayNode, Condition
from rotation_editor.core.runtime.context import RuntimeContext
from rotation_editor.core.runtime.skill_state import SkillState as SkillStateProto
from rotation_editor.core.runtime.cast_strategies import (
    CastCompletionStrategy,
    make_cast_strategy,
)
from rotation_editor.core.runtime.keyboard import KeySender, PynputKeySender
from rotation_editor.core.runtime.capture_plan import build_capture_plan
from rotation_editor.core.runtime.condition_eval import eval_condition

log = logging.getLogger(__name__)


def now_ms() -> int:
    return int(time.time() * 1000)


class Scheduler(Protocol):
    def call_soon(self, fn: Callable[[], None]) -> None: ...


@dataclass
class ExecutionCursor:
    preset_id: str
    mode_id: Optional[str]
    track_id: str
    node_index: int


@dataclass
class NodeExecResult:
    cursor: ExecutionCursor
    next_time_ms: int


class SimpleSkillState(SkillStateProto):
    """
    最简技能状态机实现：
    - 目前只记录施放次数，用于 future 的 skill_cast_ge 条件
    """

    def __init__(self) -> None:
        self._counts: dict[str, int] = {}

    def record_cast(self, skill_id: str) -> None:
        self._counts[skill_id] = self._counts.get(skill_id, 0) + 1

    def get_cast_count(self, skill_id: str) -> int:
        return self._counts.get(skill_id, 0)


class SnapshotCapture(ScreenCapture):
    """
    用 PixelScanner + FrameSnapshot 实现 get_rgb_scoped_abs 接口，
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


class TrackResolver:
    """
    负责根据 (mode_id, track_id) 从 RotationPreset 中查找 Track，
    以及提供默认入口光标。

    默认入口策略（并行版）：
    - 全局游标(default_global_cursor):
        * 若有全局轨道，则使用第一条全局轨道
    - 模式游标(default_mode_cursor):
        * 若 preset.entry_mode_id/entry_track_id 配置有效，则优先使用
        * 否则使用第一个模式的第一条轨道
    """

    def __init__(self, preset: RotationPreset) -> None:
        self._preset = preset

    def track_for(self, mode_id: Optional[str], track_id: Optional[str]) -> Optional[Track]:
        tid = (track_id or "").strip()
        if not tid:
            return None

        mid = (mode_id or "").strip()
        if mid:
            for m in self._preset.modes or []:
                if m.id == mid:
                    for t in m.tracks or []:
                        if t.id == tid:
                            return t
            return None

        for t in self._preset.global_tracks or []:
            if t.id == tid:
                return t
        return None

    def _track_by_id_global(self, track_id: str) -> Optional[Track]:
        tid = (track_id or "").strip()
        if not tid:
            return None
        for t in self._preset.global_tracks or []:
            if t.id == tid:
                return t
        return None

    def _track_by_mode_and_id(self, mode_id: str, track_id: str) -> Optional[Track]:
        mid = (mode_id or "").strip()
        tid = (track_id or "").strip()
        if not mid or not tid:
            return None
        for m in self._preset.modes or []:
            if m.id == mid:
                for t in m.tracks or []:
                    if t.id == tid:
                        return t
        return None

    def default_global_cursor(self) -> Optional[ExecutionCursor]:
        """
        全局游标入口：
        - 若有全局轨道，返回第一条全局轨道的光标
        - 否则返回 None（表示没有全局轨道）
        """
        pid = self._preset.id or ""
        if self._preset.global_tracks:
            t = self._preset.global_tracks[0]
            return ExecutionCursor(
                preset_id=pid,
                mode_id=None,
                track_id=t.id or "",
                node_index=0,
            )
        return None

    def default_mode_cursor(self) -> Optional[ExecutionCursor]:
        """
        模式游标入口：
        1) 若 preset.entry_mode_id / entry_track_id 配置有效，则优先使用：
           - entry_mode_id 非空 & entry_track_id 非空 => 该模式下指定轨道
           - entry_mode_id 非空 & entry_track_id 为空 => 该模式第一条轨道
        2) 否则使用第一个模式的第一条轨道
        """
        pid = self._preset.id or ""

        em = (self._preset.entry_mode_id or "").strip()
        et = (self._preset.entry_track_id or "").strip()

        if em:
            if et:
                t = self._track_by_mode_and_id(em, et)
                if t is not None:
                    return ExecutionCursor(
                        preset_id=pid,
                        mode_id=em,
                        track_id=t.id or "",
                        node_index=0,
                    )
            else:
                for m in self._preset.modes or []:
                    if m.id == em and m.tracks:
                        t = m.tracks[0]
                        return ExecutionCursor(
                            preset_id=pid,
                            mode_id=em,
                            track_id=t.id or "",
                            node_index=0,
                        )

        # 回退：第一个模式的第一条轨道
        for m in self._preset.modes or []:
            if m.tracks:
                t = m.tracks[0]
                return ExecutionCursor(
                    preset_id=pid,
                    mode_id=m.id or "",
                    track_id=t.id or "",
                    node_index=0,
                )
        return None


class EngineCallbacks(Protocol):
    def on_started(self, preset_id: str) -> None: ...
    def on_stopped(self, reason: str) -> None: ...
    def on_node_executed(self, cursor: ExecutionCursor, node) -> None: ...
    def on_error(self, msg: str, detail: str) -> None: ...


@dataclass
class EngineConfig:
    poll_interval_ms: int = 20
    default_skill_gap_ms: int = 50
    stop_on_error: bool = True


class MacroEngine:
    """
    执行引擎（并行版）：

    - global_cursor：负责执行全局轨道（global_tracks[0]）
    - mode_cursor  ：负责执行当前模式下的轨道（根据 entry_mode_id/track 或首个模式轨道）
    - 两个游标各自维护 next_time_ms，调度时按时间片“伪并行”执行

    暂停 / 单步：
    - pause(): 引擎线程仍在运行，但不再推进节点
    - resume(): 恢复正常执行
    - step(): 执行一次调度迭代（只执行一个节点：全局或模式中最早到期者），
              执行完后自动回到暂停状态
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

        # 暂停 / 单步标记
        self._paused: bool = False
        self._step_once: bool = False
        # 停止原因（由 stop() / Gateway 等设置，_run_loop 最终统一使用）
        self._stop_reason: str = "finished"

    # ---------- 生命周期 ----------

    def is_running(self) -> bool:
        return self._running

    def start(self, preset: RotationPreset) -> None:
        if self._running:
            return
        self._stop_evt.clear()
        self._stop_reason = "finished"  # 新增：每次启动重置默认停止原因
        self._thread = threading.Thread(target=self._run_loop, args=(preset,), daemon=True)
        self._running = True
        self._thread.start()
        self._sch.call_soon(lambda: self._cb.on_started(preset.id or ""))

    def stop(self, reason: str = "user_stop") -> None:
        """
        外部停止请求：
        - 设置停止原因；
        - 触发 _stop_evt；
        - join 工作线程。

        on_stopped 回调统一由 _run_loop 的 finally 调用，避免多处发。
        """
        if not self._running:
            return

        # 记录停止原因
        self._stop_reason = reason

        # 通知工作线程尽快退出主循环
        self._stop_evt.set()

        th = self._thread
        self._thread = None
        if th is not None:
            try:
                th.join(timeout=0.5)
            except Exception:
                log.exception("MacroEngine thread join failed")

    # _running / _paused / _step_once 在 _run_loop 的 finally 里统一重置

    # ---------- 暂停 / 单步 ----------

    def pause(self) -> None:
        """
        暂停执行（不会终止线程，只是不再推进节点）。
        """
        if not self._running:
            return
        self._paused = True
        self._step_once = False

    def resume(self) -> None:
        """
        恢复执行。
        """
        if not self._running:
            return
        self._paused = False
        self._step_once = False

    def step(self) -> None:
        """
        单步执行：
        - 在当前状态基础上执行一轮调度（只执行一个游标上的一个节点）
        - 执行完成后自动回到暂停状态
        """
        if not self._running:
            return
        self._step_once = True
        # _paused 通常由 UI 先设为 True（pause），这里不强制修改

    # ---------- 内部主循环 ----------

    def _run_loop(self, preset: RotationPreset) -> None:
        """
        主循环（更新版）：

        - 全局侧：仍然只执行 global_tracks[0] 一条轨道，顺序执行节点。
        - 模式侧：对“当前模式”下的所有轨道做拍平：
            flat = [ (track1,0), (track1,1), ..., (track2,0), (track2,1), ... ]
          然后按 flat[index] 循环执行，从入口轨道/节点对应的位置开始。

        GatewayNode:
        - 对 SkillNode：忽略其返回的 cursor（仍按 flat 顺序前进）。
        - 对 GatewayNode：
            * 若 switch_mode/jump_track/jump_node 导致返回的 cursor 指向
              另一个模式/轨道/节点：
              - 若切换模式：重建该模式的 flat & 光标，使之从目标节点位置继续。
              - 若同模式内跳转：在当前 flat 中找到对应 (track_id,node_index) 位置，
                将模式侧光标定位到那里。
            * 若只是“顺序前进”（无跳转），则仍按 flat+1 往下走。
        """
        try:
            scanner = PixelScanner(ScreenCapture())
            plan = build_capture_plan(self._ctx, preset)
            cast_strategy = make_cast_strategy(self._ctx, default_gap_ms=self._cfg.default_skill_gap_ms)
            skill_state = SimpleSkillState()
            resolver = TrackResolver(preset)

            # ---------- 全局侧：仍然只跑第一条全局轨道 ----------
            global_cursor = resolver.default_global_cursor()
            now = now_ms()
            global_next = now if global_cursor is not None else 0

            # ---------- 模式侧：拍平当前模式下所有轨道 ----------

            # 先用原有逻辑决定“入口模式/轨道/节点”
            entry_mode_cursor = resolver.default_mode_cursor()
            mode_id: Optional[str] = None
            mode_flat: list[tuple[str, int]] = []
            mode_flat_index: int = 0
            mode_next: int = 0

            if entry_mode_cursor is not None:
                mode_id = entry_mode_cursor.mode_id or ""
                # 构建当前模式的拍平序列 flat: [(track_id, node_index), ...]
                mode_flat = self._build_mode_flat(preset, mode_id)
                if mode_flat:
                    # 在 flat 中找到入口轨道/节点对应的位置；找不到则从 0 开始
                    mode_flat_index = self._find_flat_index(
                        mode_flat,
                        entry_mode_cursor.track_id,
                        entry_mode_cursor.node_index,
                    )
                    mode_next = now
                else:
                    # 当前模式下没有任何节点：视为无模式侧轨道
                    mode_id = None
                    mode_flat = []

            if global_cursor is None and (not mode_id or not mode_flat):
                self._emit_error("没有可用轨道", "Preset 下没有任何全局或模式轨道")
                return

            while not self._stop_evt.is_set():
                # 暂停状态：不执行节点，只睡一会
                if self._paused and not self._step_once:
                    time.sleep(self._cfg.poll_interval_ms / 1000.0)
                    continue

                now = now_ms()

                # 计算下一次需要执行的时间
                times: list[int] = []
                if global_cursor is not None:
                    times.append(global_next)
                if mode_id is not None and mode_flat:
                    times.append(mode_next)

                if not times:
                    break  # 没有任何游标可执行

                # 最近一次调度时间
                min_next = min(times)
                if now < min_next:
                    # 没有到时间，等一会
                    sleep_ms = min(self._cfg.poll_interval_ms, min_next - now)
                    time.sleep(sleep_ms / 1000.0)
                    continue

                # 构造 RuntimeContext 工厂（每次抓一帧）
                def mk_rt_ctx() -> RuntimeContext:
                    snap = scanner.capture_with_plan(plan)
                    sc = SnapshotCapture(scanner=scanner, snapshot=snap)
                    return RuntimeContext(profile=self._ctx, capture=sc, skill_state=skill_state)

                # 选择本轮要执行哪个“侧”（全局 / 模式）：
                # - 候选：所有 now >= next_time 的侧
                # - 若都有资格，优先 next_time 更小的那个（相同则优先 global）
                candidates: list[tuple[str, int]] = []
                if global_cursor is not None and now >= global_next:
                    candidates.append(("global", global_next))
                if mode_id is not None and mode_flat and now >= mode_next:
                    candidates.append(("mode", mode_next))

                if not candidates:
                    # 虽然 now >= min_next，但没有侧满足 >= 对应 next_time，兜底睡一会
                    time.sleep(self._cfg.poll_interval_ms / 1000.0)
                    continue

                candidates.sort(key=lambda x: (x[1], 0 if x[0] == "global" else 1))
                kind = candidates[0][0]

                # ---------- 执行全局侧：保持原有单轨逻辑 ----------
                if kind == "global" and global_cursor is not None:
                    gc, gnext, g_before, g_node = self._run_single(
                        cursor=global_cursor,
                        preset=preset,
                        resolver=resolver,
                        cast_strategy=cast_strategy,
                        skill_state=skill_state,
                        rt_ctx_factory=mk_rt_ctx,
                    )
                    global_cursor = gc
                    global_next = gnext
                    if g_before is not None and g_node is not None:
                        self._emit_node_executed(g_before, g_node)

                # ---------- 执行模式侧：在拍平序列 mode_flat 上循环 ----------
                elif kind == "mode" and mode_id is not None and mode_flat:
                    # 当前要执行的 (track_id, node_index)
                    track_id, node_index = mode_flat[mode_flat_index]
                    cursor = ExecutionCursor(
                        preset_id=preset.id or "",
                        mode_id=mode_id,
                        track_id=track_id,
                        node_index=node_index,
                    )

                    mc, mnext, m_before, m_node = self._run_single(
                        cursor=cursor,
                        preset=preset,
                        resolver=resolver,
                        cast_strategy=cast_strategy,
                        skill_state=skill_state,
                        rt_ctx_factory=mk_rt_ctx,
                    )

                    # 先记录下一次可执行时间
                    mode_next = mnext

                    # 发出回调（高亮当前节点）
                    if m_before is not None and m_node is not None:
                        self._emit_node_executed(m_before, m_node)

                    # 默认：在 flat 中前进一格（循环）
                    new_flat_index = (mode_flat_index + 1) % len(mode_flat) if mode_flat else 0
                    new_mode_id = mode_id

                    # 如果当前是 GatewayNode，可能发生了 switch_mode / jump_track / jump_node
                    if isinstance(m_node, GatewayNode):
                        target_cursor = mc  # _exec_gateway_node 返回的“下一位置”游标

                        # 情况 1：切换到其他模式
                        if (target_cursor.mode_id or "") and (target_cursor.mode_id or "") != mode_id:
                            new_mode_id = target_cursor.mode_id or ""
                            new_flat = self._build_mode_flat(preset, new_mode_id)
                            if new_flat:
                                # 在新模式的 flat 中，定位到目标 (track_id, node_index)
                                new_flat_index = self._find_flat_index(
                                    new_flat,
                                    target_cursor.track_id,
                                    target_cursor.node_index,
                                )
                                mode_flat = new_flat
                            else:
                                # 目标模式下没有轨道：停止模式侧
                                new_mode_id = None
                                mode_flat = []
                                new_flat_index = 0

                        # 情况 2：在同一模式内 jump_track / jump_node
                        elif (target_cursor.mode_id or "") == mode_id:
                            if mode_flat:
                                new_flat_index = self._find_flat_index(
                                    mode_flat,
                                    target_cursor.track_id,
                                    target_cursor.node_index,
                                )

                    # 更新模式侧状态
                    mode_id = new_mode_id
                    if mode_id is not None and mode_flat:
                        mode_flat_index = new_flat_index
                    else:
                        mode_flat_index = 0

                # ---------- 单步模式：只要执行过一次，就回到暂停 ----------
                if self._step_once:
                    self._paused = True
                    self._step_once = False

        finally:
            # 标志位复位
            self._running = False
            self._paused = False
            self._step_once = False

            # 统一通知 UI：执行已停止
            try:
                reason = self._stop_reason
            except Exception:
                reason = "finished"

            # 放到 Qt 主线程执行回调
            self._sch.call_soon(lambda r=reason: self._cb.on_stopped(r))

    # ---------- 单次执行一个游标 ----------

    def _run_single(
        self,
        *,
        cursor: ExecutionCursor,
        preset: RotationPreset,
        resolver: TrackResolver,
        cast_strategy: CastCompletionStrategy,
        skill_state: SimpleSkillState,
        rt_ctx_factory: Callable[[], RuntimeContext],
    ) -> tuple[ExecutionCursor, int, Optional[ExecutionCursor], Optional[object]]:
        """
        执行单个游标上的当前节点，返回：
        - 新游标
        - 下次执行时间 next_time_ms
        - cursor_before: 执行前的光标（供 UI 高亮用，若未执行节点则为 None）
        - node: 刚刚执行的节点对象（未执行则为 None）
        """
        track = resolver.track_for(cursor.mode_id, cursor.track_id)
        if track is None or not track.nodes:
            # 轨道不存在或为空：保持 track 不变，但 node_index 归零，短暂等待
            new_cursor = ExecutionCursor(
                preset_id=cursor.preset_id,
                mode_id=cursor.mode_id,
                track_id=cursor.track_id,
                node_index=0,
            )
            return new_cursor, now_ms() + 50, None, None

        idx = cursor.node_index
        if idx < 0 or idx >= len(track.nodes):
            idx = 0

        node = track.nodes[idx]
        cursor_for_exec = ExecutionCursor(
            preset_id=cursor.preset_id,
            mode_id=cursor.mode_id,
            track_id=cursor.track_id,
            node_index=idx,
        )
        cursor_before = cursor_for_exec

        try:
            if isinstance(node, SkillNode):
                result = self._exec_skill_node(
                    node=node,
                    cursor=cursor_for_exec,
                    cast_strategy=cast_strategy,
                    rt_ctx_factory=rt_ctx_factory,
                    skill_state=skill_state,
                )
            elif isinstance(node, GatewayNode):
                result = self._exec_gateway_node(
                    node=node,
                    cursor=cursor_for_exec,
                    preset=preset,
                    rt_ctx_factory=rt_ctx_factory,
                    resolver=resolver,
                )
            else:
                # 其他节点：简单顺序前进
                result = NodeExecResult(
                    cursor=ExecutionCursor(
                        preset_id=cursor.preset_id,
                        mode_id=cursor.mode_id,
                        track_id=cursor.track_id,
                        node_index=idx + 1,
                    ),
                    next_time_ms=now_ms() + 10,
                )
        except Exception as e:
            log.exception("node execution failed")
            self._emit_error("节点执行失败", str(e))
            if self._cfg.stop_on_error:
                # 抛出给上层让主循环停止
                raise
            result = NodeExecResult(cursor=cursor_for_exec, next_time_ms=now_ms() + 200)

        return result.cursor, result.next_time_ms, cursor_before, node

    # ---------- SkillNode 执行 ----------

    def _exec_skill_node(
        self,
        *,
        node: SkillNode,
        cursor: ExecutionCursor,
        cast_strategy: CastCompletionStrategy,
        rt_ctx_factory: Callable[[], RuntimeContext],
        skill_state: SimpleSkillState,
    ) -> NodeExecResult:
        # 找到对应 Skill
        skills = getattr(self._ctx.profile.skills, "skills", []) or []
        skill = next((s for s in skills if s.id == node.skill_id), None)
        if skill is None:
            # 找不到技能，直接跳过
            return NodeExecResult(
                cursor=ExecutionCursor(
                    preset_id=cursor.preset_id,
                    mode_id=cursor.mode_id,
                    track_id=cursor.track_id,
                    node_index=cursor.node_index + 1,
                ),
                next_time_ms=now_ms() + 50,
            )

        key = (skill.trigger.key or "").strip()
        if key:
            try:
                self._key_sender.send_key(key)
            except Exception:
                log.exception("send_key failed")

        # 更新状态
        skill_state.record_cast(skill.id)

        # 读条时间：优先使用 SkillNode.override_cast_ms
        readbar_ms = int(node.override_cast_ms or skill.cast.readbar_ms or 0)

        # 等待施法完成（由策略决定用时间还是条像素）
        cast_strategy.wait_for_complete(
            skill_id=skill.id,
            node_readbar_ms=readbar_ms,
            rt_ctx_factory=rt_ctx_factory,
        )

        next_cursor = ExecutionCursor(
            preset_id=cursor.preset_id,
            mode_id=cursor.mode_id,
            track_id=cursor.track_id,
            node_index=cursor.node_index + 1,
        )
        next_time = now_ms() + self._cfg.default_skill_gap_ms
        return NodeExecResult(cursor=next_cursor, next_time_ms=next_time)

    # ---------- GatewayNode 执行（增强版） ----------

    def _exec_gateway_node(
        self,
        *,
        node: GatewayNode,
        cursor: ExecutionCursor,
        preset: RotationPreset,
        rt_ctx_factory: Callable[[], RuntimeContext],
        resolver: TrackResolver,
    ) -> NodeExecResult:
        """
        网关节点：

        - 若 condition_id 为空：视为“无条件”，直接执行 action
        - 若 condition_id 非空：
            * 找到对应 Condition
            * 使用 eval_condition(cond, RuntimeContext) 评估
            * False => 不触发动作，顺序前进
            * True  => 执行动作

        支持的 action：
        - "switch_mode" : 切换到 target_mode_id 的第一条轨道
        - "jump_track"  : 跳转到指定模式/轨道的起点：
                          * mode_id = node.target_mode_id 或保持当前 cursor.mode_id
                          * track_id = node.target_track_id（必需）
        - "jump_node"   : 在当前轨道内按索引跳转：
                          * target_node_index 超界时回到 0
        - "end"         : 结束整个 MacroEngine 执行（相当于用户点击“停止”）
        """

        # 1) 评估条件
        cond_id = (node.condition_id or "").strip()
        cond_ok = True

        if cond_id:
            cond: Optional[Condition] = None
            for c in preset.conditions or []:
                if c.id == cond_id:
                    cond = c
                    break

            if cond is None:
                log.warning("GatewayNode condition not found: id=%s", cond_id)
                cond_ok = False
            else:
                try:
                    rt_ctx = rt_ctx_factory()
                    cond_ok = bool(eval_condition(cond, rt_ctx))
                except Exception:
                    log.exception("eval_condition failed (condition_id=%s)", cond_id)
                    cond_ok = False

        if not cond_ok:
            # 条件不满足：顺序前进
            return NodeExecResult(
                cursor=ExecutionCursor(
                    preset_id=cursor.preset_id,
                    mode_id=cursor.mode_id,
                    track_id=cursor.track_id,
                    node_index=cursor.node_index + 1,
                ),
                next_time_ms=now_ms() + 10,
            )

        # 2) 执行动作
        action = (node.action or "switch_mode").strip().lower() or "switch_mode"

        # ------ end：结束整个执行引擎 ------
        if action == "end":
            # 标记停止原因，并设置停止事件；
            # _run_loop 将自然退出并在 finally 中触发 on_stopped("gateway_end") 回调。
            self._stop_reason = "gateway_end"
            self._stop_evt.set()

            # 当前游标不再前进，给一个很短的 next_time_ms 即可；
            # 主循环检测到 _stop_evt 已设置后会退出。
            return NodeExecResult(
                cursor=cursor,
                next_time_ms=now_ms() + 10,
            )
        # ------ switch_mode ------
        if action == "switch_mode":
            target_mode_id = (node.target_mode_id or "").strip()
            if not target_mode_id:
                log.warning("gateway switch_mode without target_mode_id, no-op")
                return NodeExecResult(
                    cursor=ExecutionCursor(
                        preset_id=cursor.preset_id,
                        mode_id=cursor.mode_id,
                        track_id=cursor.track_id,
                        node_index=cursor.node_index + 1,
                    ),
                    next_time_ms=now_ms() + 10,
                )

            # 找到目标模式及其第一条轨道
            mode = None
            for m in preset.modes or []:
                if m.id == target_mode_id:
                    mode = m
                    break

            if mode is None or not mode.tracks:
                log.warning("gateway switch_mode target mode invalid or has no tracks: %s", target_mode_id)
                return NodeExecResult(
                    cursor=ExecutionCursor(
                        preset_id=cursor.preset_id,
                        mode_id=cursor.mode_id,
                        track_id=cursor.track_id,
                        node_index=cursor.node_index + 1,
                    ),
                    next_time_ms=now_ms() + 10,
                )

            t = mode.tracks[0]
            new_cursor = ExecutionCursor(
                preset_id=cursor.preset_id,
                mode_id=mode.id or "",
                track_id=t.id or "",
                node_index=0,
            )
            return NodeExecResult(cursor=new_cursor, next_time_ms=now_ms() + 10)

        # ------ jump_track ------
        if action == "jump_track":
            # 目标模式：若未指定，则保持当前模式
            target_mode_id = (node.target_mode_id or cursor.mode_id or "").strip()
            # 目标轨道：必须指定
            target_track_id = (node.target_track_id or "").strip()
            if not target_track_id:
                log.warning("gateway jump_track without target_track_id, no-op")
                return NodeExecResult(
                    cursor=ExecutionCursor(
                        preset_id=cursor.preset_id,
                        mode_id=cursor.mode_id,
                        track_id=cursor.track_id,
                        node_index=cursor.node_index + 1,
                    ),
                    next_time_ms=now_ms() + 10,
                )

            # 不强制检查 track 是否存在，交给后续 resolver；也可以显式检查一次：
            t = resolver.track_for(target_mode_id or None, target_track_id)
            if t is None:
                log.warning(
                    "gateway jump_track target track not found: mode=%r track=%r",
                    target_mode_id, target_track_id,
                )
                return NodeExecResult(
                    cursor=ExecutionCursor(
                        preset_id=cursor.preset_id,
                        mode_id=cursor.mode_id,
                        track_id=cursor.track_id,
                        node_index=cursor.node_index + 1,
                    ),
                    next_time_ms=now_ms() + 10,
                )

            new_cursor = ExecutionCursor(
                preset_id=cursor.preset_id,
                mode_id=target_mode_id or None,
                track_id=t.id or "",
                node_index=0,
            )
            return NodeExecResult(cursor=new_cursor, next_time_ms=now_ms() + 10)

        # ------ jump_node ------
        if action == "jump_node":
            # 在当前轨道内跳转到指定索引
            track = resolver.track_for(cursor.mode_id, cursor.track_id)
            if track is None or not track.nodes:
                return NodeExecResult(
                    cursor=ExecutionCursor(
                        preset_id=cursor.preset_id,
                        mode_id=cursor.mode_id,
                        track_id=cursor.track_id,
                        node_index=cursor.node_index + 1,
                    ),
                    next_time_ms=now_ms() + 10,
                )

            idx = node.target_node_index if node.target_node_index is not None else 0
            if idx < 0 or idx >= len(track.nodes):
                idx = 0

            new_cursor = ExecutionCursor(
                preset_id=cursor.preset_id,
                mode_id=cursor.mode_id,
                track_id=cursor.track_id,
                node_index=int(idx),
            )
            return NodeExecResult(cursor=new_cursor, next_time_ms=now_ms() + 10)

        # ------ 其他未支持动作：视为 noop，顺序前进 ------
        log.warning("unsupported gateway action=%r, treat as no-op", action)
        return NodeExecResult(
            cursor=ExecutionCursor(
                preset_id=cursor.preset_id,
                mode_id=cursor.mode_id,
                track_id=cursor.track_id,
                node_index=cursor.node_index + 1,
            ),
            next_time_ms=now_ms() + 10,
        )

    # ---------- 回调封装 ----------

    def _emit_error(self, msg: str, detail: str) -> None:
        self._sch.call_soon(lambda: self._cb.on_error(msg, detail))

    def _emit_node_executed(self, cursor: ExecutionCursor, node) -> None:
        self._sch.call_soon(lambda: self._cb.on_node_executed(cursor, node))

    def _build_mode_flat(
        self,
        preset: RotationPreset,
        mode_id: Optional[str],
    ) -> list[tuple[str, int]]:
        """
        为给定 mode_id 构建拍平后的节点序列（基于步骤轴）：

        规则：
        - 先按 Node.step_index 分桶（step 从小到大）；
        - 每个 step 内：
            * 按轨道在 UI 中的顺序（mode.tracks 列表顺序）；
            * 再按 Node.order_in_step；
            * 再按节点在轨道中的索引 node_index；
          排成一个局部序列；
        - 最终 flat = step0 的所有节点 + step1 的所有节点 + step2 的所有节点 + ...

        兼容性要点：
        - 旧数据中有些 Track.id 可能是空字符串：
            * 以前的引擎仍然可以通过空 id 找到这些轨道；
            * 因此这里不能简单略过 Track.id 为空的轨道，否则会导致整
              个模式侧被视为“无轨道”，只剩全局轨道在执行。
        - 所以我们仍然使用 tid = t.id 或 ""，但不再因为 tid 为空就跳过。
        """
        mid = (mode_id or "").strip()
        if not mid:
            return []

        mode = None
        for m in preset.modes or []:
            if m.id == mid:
                mode = m
                break
        if mode is None:
            return []

        tracks = list(mode.tracks or [])
        if not tracks:
            return []

        # step_index -> List[ (track_order, order_in_step, node_index, track_id) ]
        buckets: dict[int, list[tuple[int, int, int, str]]] = {}

        for t_order, t in enumerate(tracks):
            tid = t.id or ""   # 允许为空字符串，保持与旧数据兼容
            if not t.nodes:
                continue
            for idx, n in enumerate(t.nodes or []):
                # 读取 step_index / order_in_step，兼容异常情况
                try:
                    s = int(getattr(n, "step_index", 0) or 0)
                except Exception:
                    s = 0
                if s < 0:
                    s = 0
                try:
                    ois = int(getattr(n, "order_in_step", 0) or 0)
                except Exception:
                    ois = 0

                buckets.setdefault(s, []).append((t_order, ois, idx, tid))

        if not buckets:
            return []

        flat: list[tuple[str, int]] = []

        # 按 step_index 从小到大遍历
        for step in sorted(buckets.keys()):
            items = buckets[step]
            # 同一步内：按轨道顺序、order_in_step、节点索引排序
            items.sort(key=lambda x: (x[0], x[1], x[2]))
            for _t_order, _ois, idx, tid in items:
                flat.append((tid, idx))

        return flat        
    
    @staticmethod
    def _find_flat_index(
        flat: list[tuple[str, int]],
        track_id: str,
        node_index: int,
    ) -> int:
        """
        在 flat 序列中查找 (track_id, node_index) 的位置，找不到则返回 0。
        """
        tid = (track_id or "").strip()
        idx = int(node_index)
        for i, (t, n) in enumerate(flat):
            if t == tid and n == idx:
                return i
        return 0