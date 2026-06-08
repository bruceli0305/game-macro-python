"""
rotation_editor.core.runtime.cycle_executor — 循环阶段执行器。

基于 CycleConfig 的优先级调度执行器，实现用户描述的场景：
  "有4个技能ABCD，当A满足条件释放A，B满足条件释放B，
   当AB都释放了且C未释放时释放D，ABD都释放了再释放C"

执行模型：
  1. 引擎维护当前 Phase 索引和已释放技能集合
  2. 每个 tick，从当前 Phase 的候选技能中按优先级检查就绪状态
  3. 执行第一个就绪的技能
  4. Phase 完成条件满足后推进到下一个 Phase
  5. 所有 Phase 完成后循环重置

与 MacroEngineNew 的关系：
  - CycleExecutor 是一个独立的执行器，不依赖 Track/Mode/Node 模型
  - 复用 SkillAttemptExecutor 进行实际的技能发送和就绪检查
  - 复用 CaptureManager 进行截屏
  - 通过 EngineCallbacks 通知 UI
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from core.profiles import ProfileContext

from rotation_editor.core.models.cycle import CycleConfig, CyclePhase, SkillSlot
from rotation_editor.core.runtime.keyboard import KeySender, PynputKeySender
from rotation_editor.core.runtime.state import StateStore
from rotation_editor.core.runtime.capture import CaptureManager, StateStoreCaptureSink
from rotation_editor.core.runtime.capture.eval_bridge import eval_expr_with_capture, ensure_plan_for_probes
from rotation_editor.core.runtime.executor.skill_attempt import SkillAttemptExecutor, SkillAttemptConfig
from rotation_editor.ast.codec import decode_expr
from rotation_editor.ast import collect_probes_from_expr
from rotation_editor.ast.nodes import Expr

log = logging.getLogger(__name__)


@dataclass
class CycleExecState:
    """循环执行器的运行时状态。"""
    phase_index: int = 0                    # 当前阶段索引
    cycle_count: int = 0                    # 已完成的循环次数
    fired_in_phase: Set[str] = field(default_factory=set)  # 当前阶段已释放的技能ID
    fired_in_cycle: Set[str] = field(default_factory=set)  # 当前循环已释放的所有技能ID
    total_executed: int = 0                 # 总执行次数
    last_skill_id: str = ""                 # 最后执行的技能ID
    last_outcome: str = ""                  # 最后执行结果


@dataclass
class CycleExecLogEntry:
    """循环执行日志条目。"""
    ts_ms: int
    phase_index: int
    phase_name: str
    event: str          # "select" | "execute" | "skip" | "phase_complete" | "cycle_reset"
    skill_id: str = ""
    skill_name: str = ""
    outcome: str = ""   # SUCCESS / FAILED / SKIPPED_NOT_READY / ...
    reason: str = ""
    detail: str = ""


class CycleExecutor:
    """
    循环阶段执行器。

    独立于 MacroEngineNew 运行，使用自己的线程和调度逻辑。
    """

    def __init__(
        self,
        *,
        ctx: ProfileContext,
        config: CycleConfig,
        scheduler: Any,  # SchedulerLike
        callbacks: Any,  # EngineCallbacks
        store: Optional[StateStore] = None,
        key_sender: Optional[KeySender] = None,
        attempt_cfg: Optional[SkillAttemptConfig] = None,
    ) -> None:
        self._ctx = ctx
        self._config = config
        self._sch = scheduler
        self._cb = callbacks
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

        # AST 缓存：slot 条件表达式
        self._expr_cache: Dict[int, Optional[Expr]] = {}  # id(slot) → Expr

        # 运行时状态
        self._state = CycleExecState()

        # 执行日志
        self._exec_log: List[CycleExecLogEntry] = []
        self._exec_log_max = 500

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  生命周期
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def is_running(self) -> bool:
        th = self._thread
        return bool(th is not None and th.is_alive())

    def start(self) -> None:
        if self.is_running():
            return
        self._stop_evt.clear()
        self._paused = False
        self._step_once = False
        self._stop_reason = "finished"
        self._state = CycleExecState()
        self._exec_log.clear()
        self._expr_cache.clear()

        # 预编译所有条件表达式
        self._build_expr_cache()

        # 预热截屏计划
        self._warmup_capture()

        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self, reason: str = "user_stop") -> None:
        if not self.is_running():
            return
        self._stop_reason = reason
        self._stop_evt.set()
        th = self._thread
        if th is not None:
            try:
                th.join(timeout=0.5)
            except Exception:
                pass

    def pause(self) -> None:
        if not self.is_running():
            return
        self._paused = True
        self._step_once = False

    def resume(self) -> None:
        if not self.is_running():
            return
        self._paused = False
        self._step_once = False

    def step(self) -> None:
        if not self.is_running():
            return
        self._paused = True
        self._step_once = True

    def get_state(self) -> CycleExecState:
        return self._state

    def get_exec_log(self) -> List[CycleExecLogEntry]:
        return list(self._exec_log)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  AST 缓存
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _build_expr_cache(self) -> None:
        for phase in self._config.phases:
            for slot in phase.skills:
                key = id(slot)
                ce = slot.condition_expr
                if isinstance(ce, dict) and ce:
                    try:
                        expr, _diags = decode_expr(ce, path="$")
                        self._expr_cache[key] = expr
                    except Exception:
                        log.warning("Failed to compile condition for slot '%s'", slot.skill_id, exc_info=True)
                        self._expr_cache[key] = None
                else:
                    self._expr_cache[key] = None  # 无条件，仅检查 CD

    def _warmup_capture(self) -> None:
        """收集所有需要的 probes 并预热截屏计划。"""
        from rotation_editor.ast import ProbeRequirements
        probes = ProbeRequirements()
        for phase in self._config.phases:
            for slot in phase.skills:
                key = id(slot)
                expr = self._expr_cache.get(key)
                if expr is not None:
                    probes.merge(collect_probes_from_expr(expr))
        try:
            ensure_plan_for_probes(capman=self._capman, probes=probes)
        except Exception:
            log.warning("Failed to warmup capture plan", exc_info=True)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  主循环
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _run_loop(self) -> None:
        self._store.engine_started("cycle")
        self._emit_started()

        try:
            config = self._config
            phases = config.phases

            if not phases:
                self._emit_error("没有配置任何阶段", "请添加至少一个 CyclePhase")
                self._stop_reason = "no_phases"
                return

            while not self._stop_evt.is_set():
                # 暂停检查
                if self._paused and not self._step_once:
                    self._stop_evt.wait(config.poll_interval_ms / 1000.0)
                    continue

                # 最大循环次数检查
                if config.max_cycles > 0 and self._state.cycle_count >= config.max_cycles:
                    self._stop_reason = "max_cycles"
                    self._log_event(event="cycle_limit", reason=f"达到最大循环次数 {config.max_cycles}")
                    break

                # 获取当前阶段
                phase_idx = self._state.phase_index
                if phase_idx >= len(phases):
                    # 所有阶段完成，循环重置
                    self._on_cycle_reset()
                    continue

                phase = phases[phase_idx]

                # 从当前阶段选择并执行技能
                executed = self._try_execute_phase(phase, phase_idx)

                if self._step_once:
                    self._paused = True
                    self._step_once = False

                if not executed:
                    # 没有就绪技能，等待一个 poll 周期
                    self._stop_evt.wait(config.poll_interval_ms / 1000.0)

        except Exception as e:
            self._store.engine_error("cycle_crash", str(e))
            self._emit_error("循环执行器异常退出", str(e))
            self._stop_reason = "error"
        finally:
            try:
                self._capman.close_current_thread()
            except Exception:
                pass
            reason = self._stop_reason or "finished"
            self._store.engine_stopped(reason)
            self._emit_stopped(reason)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  阶段执行逻辑
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _try_execute_phase(self, phase: CyclePhase, phase_idx: int) -> bool:
        """
        尝试在当前阶段执行一个技能。

        返回 True 表示执行了技能（或阶段完成），False 表示没有就绪技能。
        """
        state = self._state

        # 按优先级遍历候选技能
        for slot in phase.skills:
            skill_id = (slot.skill_id or "").strip()
            if not skill_id:
                continue

            # 检查该技能在本阶段是否还需要释放
            if skill_id in state.fired_in_phase:
                # 已释放，跳过（除非 complete_when == "always"）
                if phase.complete_when != "always":
                    continue

            # 检查就绪状态
            ready_result = self._check_skill_ready(slot)

            if not ready_result:
                # 未就绪，尝试下一个候选
                self._log_event(
                    event="skip", phase_index=phase_idx, phase_name=phase.name,
                    skill_id=skill_id, skill_name=self._resolve_skill_name(skill_id),
                    outcome="NOT_READY", reason="技能未就绪（CD中或条件不满足）",
                )
                continue

            # 就绪！执行
            outcome = self._execute_skill(slot, phase_idx, phase.name)

            if outcome in ("SUCCESS", "FAILED"):
                # 标记为已释放
                state.fired_in_phase.add(skill_id)
                state.fired_in_cycle.add(skill_id)
                state.total_executed += 1
                state.last_skill_id = skill_id
                state.last_outcome = outcome

                # 检查阶段完成条件
                if self._is_phase_complete(phase, state):
                    self._on_phase_complete(phase, phase_idx)

            return True

        return False

    def _check_skill_ready(self, slot: SkillSlot) -> bool:
        """
        检查技能是否就绪：
        1. 技能存在且启用
        2. 如果有自定义条件表达式，求值为 True
        3. 如果没有自定义条件，默认检查像素匹配（CD 就绪）
        """
        skill_id = (slot.skill_id or "").strip()
        if not skill_id:
            return False

        # 查找技能定义
        skill = self._find_skill(skill_id)
        if skill is None or not getattr(skill, "enabled", True):
            return False

        # 获取编译后的条件表达式
        expr = self._expr_cache.get(id(slot))

        if expr is not None:
            # 有自定义条件：求值
            from rotation_editor.ast import collect_probes_from_expr
            probes = collect_probes_from_expr(expr)
            try:
                ensure_plan_for_probes(capman=self._capman, probes=probes)
            except Exception:
                pass

            out = eval_expr_with_capture(
                expr, profile=self._ctx, capman=self._capman,
                metrics=self._store, baseline=None,
            )
            return out.tri.value is True

        # 无自定义条件：默认检查像素匹配（CD 就绪）
        # 使用 SkillAttemptExecutor 的默认 ready 检查
        # 这里我们直接尝试执行，让执行器内部处理 ready check
        return True  # 假定就绪，实际检查在 _execute_skill 中

    def _execute_skill(self, slot: SkillSlot, phase_idx: int, phase_name: str) -> str:
        """
        执行一个技能，返回 outcome 字符串。
        """
        skill_id = (slot.skill_id or "").strip()
        skill_name = self._resolve_skill_name(skill_id)

        self._log_event(
            event="execute", phase_index=phase_idx, phase_name=phase_name,
            skill_id=skill_id, skill_name=skill_name,
            reason=f"优先级 {slot.priority}，开始执行",
        )

        # 使用 SkillAttemptExecutor 执行
        res = self._attempt_exec.exec_skill_node(
            skill_id=skill_id,
            node_id=f"cycle_phase{phase_idx}_{skill_id}",
            override_cast_ms=slot.override_cast_ms,
            node_start_expr_json=None,
            node_complete_expr_json=None,
        )

        self._log_event(
            event="result", phase_index=phase_idx, phase_name=phase_name,
            skill_id=skill_id, skill_name=skill_name,
            outcome=res.outcome, reason=res.reason or "",
        )

        # 通知 UI
        self._emit_node_executed(skill_id, skill_name, phase_name)

        return res.outcome

    def _is_phase_complete(self, phase: CyclePhase, state: CycleExecState) -> bool:
        """检查阶段完成条件。"""
        if phase.complete_when == "always":
            return True
        if phase.complete_when == "any_fired":
            return bool(state.fired_in_phase)
        # "all_fired"：所有候选技能都已释放
        all_ids = {(s.skill_id or "").strip() for s in phase.skills if (s.skill_id or "").strip()}
        return all_ids.issubset(state.fired_in_phase)

    def _on_phase_complete(self, phase: CyclePhase, phase_idx: int) -> None:
        """阶段完成：推进到下一个阶段。"""
        self._state.phase_index = phase_idx + 1
        self._state.fired_in_phase.clear()

        self._log_event(
            event="phase_complete", phase_index=phase_idx, phase_name=phase.name,
            reason=f"阶段完成，推进到阶段 {phase_idx + 2}",
        )

    def _on_cycle_reset(self) -> None:
        """所有阶段完成，循环重置。"""
        self._state.cycle_count += 1
        self._state.phase_index = 0
        self._state.fired_in_phase.clear()
        self._state.fired_in_cycle.clear()

        self._log_event(
            event="cycle_reset",
            reason=f"第 {self._state.cycle_count} 轮循环完成，重置",
        )

        # 通知 UI
        self._sch.call_soon(lambda: self._cb.on_stopped(f"cycle_reset_{self._state.cycle_count}"))
        # 重新启动下一轮（通过重新触发 started）
        self._sch.call_soon(lambda: self._cb.on_started("cycle"))

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  工具方法
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _find_skill(self, skill_id: str) -> Any:
        for s in (self._ctx.skills.skills or []):
            if (getattr(s, "id", "") or "") == skill_id:
                return s
        return None

    def _resolve_skill_name(self, skill_id: str) -> str:
        s = self._find_skill(skill_id)
        return getattr(s, "name", "") or "" if s else ""

    def _log_event(self, *, event: str, phase_index: int = 0, phase_name: str = "",
                   skill_id: str = "", skill_name: str = "",
                   outcome: str = "", reason: str = "", detail: str = "") -> None:
        from rotation_editor.core.runtime.state.store import mono_ms
        entry = CycleExecLogEntry(
            ts_ms=int(mono_ms()),
            phase_index=phase_index,
            phase_name=phase_name,
            event=event,
            skill_id=skill_id,
            skill_name=skill_name,
            outcome=outcome,
            reason=reason,
            detail=detail,
        )
        self._exec_log.append(entry)
        if len(self._exec_log) > self._exec_log_max:
            self._exec_log = self._exec_log[-self._exec_log_max:]

        # 推送到 UI
        try:
            self._sch.call_soon(lambda e=entry: self._cb.on_exec_log(e))
        except Exception:
            pass

    def _emit_started(self) -> None:
        self._sch.call_soon(lambda: self._cb.on_started("cycle"))

    def _emit_stopped(self, reason: str) -> None:
        self._sch.call_soon(lambda: self._cb.on_stopped(reason))

    def _emit_error(self, msg: str, detail: str) -> None:
        self._sch.call_soon(lambda: self._cb.on_error(msg, detail))

    def _emit_node_executed(self, skill_id: str, skill_name: str, phase_name: str) -> None:
        """通知 UI 一个技能被执行（复用 on_node_executed 回调）。"""
        # 构造一个伪 cursor 和 node 供 UI 使用
        from rotation_editor.core.runtime.engine import ExecutionCursor
        cursor = ExecutionCursor(
            preset_id="cycle",
            mode_id=None,
            track_id=f"phase:{phase_name}",
            node_index=0,
        )
        # 构造一个伪 node
        class _PseudoNode:
            def __init__(self, sid, sname):
                self.id = sid
                self.label = sname or sid
                self.kind = "skill"
                self.skill_id = sid
        self._sch.call_soon(lambda: self._cb.on_node_executed(cursor, _PseudoNode(skill_id, skill_name)))
