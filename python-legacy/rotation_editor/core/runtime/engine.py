from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Protocol, Any, Dict

from core.profiles import ProfileContext

from rotation_editor.core.models import RotationPreset, SkillNode, GatewayNode, Condition
from rotation_editor.core.runtime.keyboard import KeySender, PynputKeySender

from rotation_editor.core.runtime.state import StateStore
from rotation_editor.core.runtime.capture import CaptureManager, StateStoreCaptureSink
from rotation_editor.core.runtime.executor.skill_attempt import SkillAttemptExecutor, SkillAttemptConfig

from rotation_editor.ast.codec import decode_expr
from rotation_editor.ast import collect_probes_from_expr
from rotation_editor.ast.nodes import Expr, And, Or, Not, Const, SkillMetricGE
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

log = logging.getLogger(__name__)


class SchedulerLike(Protocol):
    def call_soon(self, fn: Callable[[], None]) -> None: ...


class EngineCallbacks(Protocol):
    def on_started(self, preset_id: str) -> None: ...
    def on_stopped(self, reason: str) -> None: ...
    def on_error(self, msg: str, detail: str) -> None: ...
    def on_node_executed(self, cursor, node) -> None: ...
    def on_exec_log(self, entry: "ExecLogEntry") -> None: ...


@dataclass(frozen=True)
class ExecutionCursor:
    preset_id: str
    mode_id: Optional[str]
    track_id: str
    node_index: int


@dataclass
class ExecLogEntry:
    """引擎执行日志条目 — 记录每一次调度决策的详细信息。"""
    ts_ms: int                          # 单调时钟毫秒
    kind: str                           # "skill" | "gateway" | "schedule" | "error"
    outcome: str                        # SUCCESS / FAILED / SKIPPED_* / GW_COND_TRUE / GW_COND_FALSE ...
    track_id: str                       # 轨道 ID
    node_id: str = ""                   # 节点 ID
    node_label: str = ""               # 节点显示标签
    skill_id: str = ""                 # 技能 ID（仅 skill 节点）
    skill_name: str = ""               # 技能名称
    reason: str = ""                   # 原因说明
    advance: str = ""                  # ADVANCE / HOLD / JUMP
    next_delay_ms: int = 0             # 下次调度延迟
    detail: str = ""                   # 额外详情（如条件求值结果）


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

        # AST 条件缓存：condition_id/condition_expr_key → 编译后的 Expr 对象
        # 避免每次网关执行时重复 decode_expr()
        self._cond_cache: Dict[str, Optional[Expr]] = {}
        self._cond_cache_built = False

        # 执行日志（环形缓冲，最多保留 500 条）
        self._exec_log: List[ExecLogEntry] = []
        self._exec_log_max = 500

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

        # 清空上次运行的日志和缓存
        self._exec_log.clear()
        self._cond_cache.clear()
        self._cond_cache_built = False

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

    def _emit_log(self, entry: ExecLogEntry) -> None:
        """将日志条目推送到 UI 回调（通过 call_soon 切到 UI 线程）。"""
        try:
            self._sch.call_soon(lambda e=entry: self._cb.on_exec_log(e))
        except Exception:
            pass

    def _log_exec(self, *, kind: str, outcome: str, track_id: str,
                  node_id: str = "", node_label: str = "",
                  skill_id: str = "", skill_name: str = "",
                  reason: str = "", advance: str = "", next_delay_ms: int = 0,
                  detail: str = "") -> None:
        """记录一条执行日志（环形缓冲 + 推送到 UI）。"""
        entry = ExecLogEntry(
            ts_ms=self._now(),
            kind=kind,
            outcome=outcome,
            track_id=track_id,
            node_id=node_id,
            node_label=node_label,
            skill_id=skill_id,
            skill_name=skill_name,
            reason=reason,
            advance=advance,
            next_delay_ms=next_delay_ms,
            detail=detail,
        )
        self._exec_log.append(entry)
        if len(self._exec_log) > self._exec_log_max:
            self._exec_log = self._exec_log[-self._exec_log_max:]
        self._emit_log(entry)

    def get_exec_log(self) -> List[ExecLogEntry]:
        """获取完整的执行日志（副本）。"""
        return list(self._exec_log)

    def get_exec_log_since(self, ts_ms: int) -> List[ExecLogEntry]:
        """获取指定时间戳之后的执行日志。"""
        return [e for e in self._exec_log if e.ts_ms >= ts_ms]

    # ---------------- AST condition cache ----------------

    def _build_cond_cache(self, preset: RotationPreset) -> None:
        """
        在引擎启动时预编译所有条件表达式，缓存为 Expr 对象。
        避免每次网关执行时重复 decode_expr()。
        """
        self._cond_cache.clear()
        for cond in (preset.conditions or []):
            cid = (getattr(cond, "id", "") or "").strip()
            expr_json = getattr(cond, "expr", None)
            if not cid or not isinstance(expr_json, dict):
                continue
            try:
                expr, _diags = decode_expr(expr_json, path="$")
                self._cond_cache[cid] = expr
            except Exception:
                log.warning("Failed to pre-compile condition '%s'", cid, exc_info=True)
                self._cond_cache[cid] = None

        # 也预编译所有网关节点的内联条件
        for mode in (preset.modes or []):
            for track in (mode.tracks or []):
                for node in (track.nodes or []):
                    if isinstance(node, GatewayNode):
                        ce = getattr(node, "condition_expr", None)
                        if isinstance(ce, dict) and ce:
                            cache_key = f"inline:{node.id}"
                            try:
                                expr, _diags = decode_expr(ce, path="$")
                                self._cond_cache[cache_key] = expr
                            except Exception:
                                log.warning("Failed to pre-compile inline condition for gateway '%s'", node.id, exc_info=True)
                                self._cond_cache[cache_key] = None

        for track in (preset.global_tracks or []):
            for node in (track.nodes or []):
                if isinstance(node, GatewayNode):
                    ce = getattr(node, "condition_expr", None)
                    if isinstance(ce, dict) and ce:
                        cache_key = f"inline:{node.id}"
                        try:
                            expr, _diags = decode_expr(ce, path="$")
                            self._cond_cache[cache_key] = expr
                        except Exception:
                            log.warning("Failed to pre-compile inline condition for gateway '%s'", node.id, exc_info=True)
                            self._cond_cache[cache_key] = None

        self._cond_cache_built = True
        log.info("AST condition cache built: %d entries", len(self._cond_cache))

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

    def _gateway_condition_ok(self, preset: RotationPreset, gw: GatewayNode) -> tuple[bool, str]:
        """
        求值网关条件，返回 (条件是否成立, 详情字符串)。
        使用 AST 缓存避免重复编译。
        """
        has_inline = False
        try:
            has_inline = isinstance(getattr(gw, "condition_expr", None), dict)
        except Exception:
            has_inline = False
        cid = (getattr(gw, "condition_id", "") or "").strip()
        if not cid and not has_inline:
            return True, "无条件（默认通过）"

        # 从缓存获取编译后的 Expr
        cache_key = f"inline:{gw.id}" if has_inline else cid

        if self._cond_cache_built:
            expr = self._cond_cache.get(cache_key)
        else:
            # 缓存未构建时（fallback），实时编译
            expr_json = self._load_gateway_condition_expr(preset, gw)
            if not isinstance(expr_json, dict) or not expr_json:
                return False, "条件表达式为空"
            expr, _diags = decode_expr(expr_json, path="$")

        if expr is None:
            return False, f"条件编译失败 (key={cache_key})"

        probes = collect_probes_from_expr(expr)
        ensure_plan_for_probes(capman=self._capman, probes=probes)

        out = eval_expr_with_capture(expr, profile=self._ctx, capman=self._capman, metrics=self._store, baseline=None)

        if out.tri.value is True:
            return True, f"条件成立 (key={cache_key})"
        elif out.tri.value is False:
            return False, f"条件不成立 (key={cache_key}, reason={out.tri.reason})"
        else:
            return False, f"条件未知/Unknown (key={cache_key}, reason={out.tri.reason})"

    # ---------------- Engine loop ----------------

    def _run_loop(self, preset: RotationPreset) -> None:
        preset_id = (preset.id or "").strip()
        self._store.engine_started(preset_id)
        self._emit_started(preset_id)

        try:
            now = self._now()

            # 预编译所有 AST 条件，缓存到 self._cond_cache
            self._build_cond_cache(preset)

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
            skill_id = (node.skill_id or "").strip()
            res: ExecutionResult = self._attempt_exec.exec_skill_node(
                skill_id=skill_id,
                node_id=(node.id or "").strip(),
                override_cast_ms=node.override_cast_ms,
                node_start_expr_json=getattr(node, "start_expr", None),
                node_complete_expr_json=getattr(node, "complete_expr", None),
            )
            # 记录技能执行日志
            skill_name = self._resolve_skill_name(skill_id)
            self._log_exec(
                kind="skill",
                outcome=res.outcome,
                track_id=track_id,
                node_id=(node.id or ""),
                node_label=(getattr(node, "label", "") or ""),
                skill_id=skill_id,
                skill_name=skill_name,
                reason=res.reason or "",
                advance=res.advance,
                next_delay_ms=res.next_delay_ms,
            )
            # 严格顺序只作用于模式轨道上的 SkillNode
            strict = (scope == "mode")
            self._apply_exec_result(
                scope=scope,
                track_id=track_id,
                res=res,
                now_ms=now_ms,
                strict=strict,
            )
            return
        if isinstance(node, GatewayNode):
            self._exec_gateway(preset=preset, scope=scope, track_id=track_id, gw=node, now_ms=now_ms)
            return

        self._log_exec(
            kind="error", outcome="ERROR", track_id=track_id,
            reason="unknown_node", node_id=(getattr(node, "id", "") or ""),
        )
        self._apply_exec_result(
            scope=scope,
            track_id=track_id,
            res=ExecutionResult(outcome="ERROR", advance="ADVANCE", next_delay_ms=int(self._cfg.gateway_poll_delay_ms), reason="unknown_node"),
            now_ms=now_ms,
        )

    def _resolve_skill_name(self, skill_id: str) -> str:
        """从 ProfileContext 中查找技能名称。"""
        try:
            for s in (self._ctx.skills.skills or []):
                if (getattr(s, "id", "") or "") == skill_id:
                    return getattr(s, "name", "") or ""
        except Exception:
            pass
        return ""

    def _apply_exec_result(
        self,
        *,
        scope: str,
        track_id: str,
        res: ExecutionResult,
        now_ms: int,
        strict: bool = False,
    ) -> None:
        """
        根据 ExecutionResult 更新运行时状态：

        - scope: "global" | "mode"
        - track_id: 对应运行时里的某条轨道
        - res: 执行结果（SUCCESS/FAILED/SKIPPED_* 等）
        - now_ms: 当前时间戳（毫秒）
        - strict: 严格顺序模式标志（目前仅对 mode 轨道上的 SkillNode 使用）

        严格顺序语义（仅作用于 mode 轨道 + strict=True）：
        - outcome == SKIPPED_NOT_READY:
            * 表示技能 CD / 像素等“尚未就绪”，不允许跳过；
            * 强制 HOLD（不推进节点），等待下一次再试。
        - outcome == FAILED:
            * send_key_failed: 发键/配置致命问题 -> 直接停止引擎并报错；
            * 其他 FAILED（no_cast_start / complete_failed / timeout 等）：
                - 认为当前节点本轮尝试失败，允许按原始 advance 推进，
                  避免整条主循环轨道被永久卡在一个节点。
        - 其他 outcome（SUCCESS / SKIPPED_DISABLED / SKIPPED_LOCK_BUSY 等）：
            * 完全按 ExecutionResult.advance 行事。
        """
        global_rt = self._global_rt
        if global_rt is None:
            return

        # 执行器显式请求停止（STOPPED），直接停引擎
        if res.outcome == "STOPPED":
            self._stop_reason = "stopped"
            self._stop_evt.set()
            return

        delay = int(max(0, res.next_delay_ms))

        # 先按原始结果初始化“有效 advance 策略”
        eff_advance = res.advance

        # 严格顺序只作用于 mode 轨道
        if scope == "mode" and strict:
            # 1) 未 ready：严格顺序下绝不允许跳过
            if res.outcome == "SKIPPED_NOT_READY":
                eff_advance = "HOLD"

            # 2) 已经尝试过但 FAILED：根据 reason 决定是否致命
            elif res.outcome == "FAILED":
                reason = (res.reason or "").strip().lower()

                # 2.1 发键失败：配置/环境致命问题 -> 停引擎
                if reason == "send_key_failed":
                    # 记录到状态仓库
                    self._store.engine_error(
                        "send_key_failed",
                        f"技能发键失败，track={track_id}",
                    )
                    # 通知 UI
                    self._emit_error(
                        "技能发键失败，已停止循环",
                        f"track_id={track_id}, reason=send_key_failed",
                    )
                    if getattr(self._cfg, "stop_on_error", True):
                        self._stop_reason = "error"
                        self._stop_evt.set()
                    # 不再为该轨道安排后续调度
                    return

                # 2.2 其他 FAILED（no_cast_start / complete_failed / timeout 等）
                #     保持原始 eff_advance（通常是 ADVANCE），允许推进到下一个节点，
                #     避免因为像素/网络/被打断导致整条主循环锁死。
                #     这里不做额外修改。
                #     pass

        # ---- 更新运行时调度信息 ----

        if scope == "global":
            rt = global_rt.get(track_id)
            if rt is None:
                return
            rt.next_time_ms = int(now_ms + delay)
            if eff_advance == "ADVANCE":
                rt.advance()
            return

        # mode 轨道
        if self._mode_rt is None:
            return
        rt2 = self._mode_rt.tracks.get(track_id)
        if rt2 is None:
            return
        rt2.next_time_ms = int(now_ms + delay)
        if eff_advance == "ADVANCE":
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
        cond_ok, cond_detail = self._gateway_condition_ok(preset, gw)

        gw_label = (getattr(gw, "label", "") or "") or (getattr(gw, "action", "") or "gateway")
        gw_id = (getattr(gw, "id", "") or "")

        if not cond_ok:
            # 条件不成立是正常情况，不是 ERROR — 使用 SKIPPED_NOT_READY + HOLD
            self._log_exec(
                kind="gateway", outcome="GW_COND_FALSE", track_id=track_id,
                node_id=gw_id, node_label=gw_label,
                reason="条件不成立", detail=cond_detail,
                advance="HOLD", next_delay_ms=int(self._cfg.gateway_poll_delay_ms),
            )
            self._apply_exec_result(
                scope=scope,
                track_id=track_id,
                res=ExecutionResult(outcome="SKIPPED_NOT_READY", advance="HOLD", next_delay_ms=int(self._cfg.gateway_poll_delay_ms), reason="gw_cond_false"),
                now_ms=now_ms,
            )
            return

        # 条件已成立
        self._log_exec(
            kind="gateway", outcome="GW_COND_TRUE", track_id=track_id,
            node_id=gw_id, node_label=gw_label,
            reason="条件成立", detail=cond_detail,
        )

        # 若配置了 reset_metrics_on_fire，则重置条件中涉及的所有 skill_metric 计数
        self._reset_metrics_for_gateway(preset, gw)

        act = (getattr(gw, "action", "") or "switch_mode").strip().lower() or "switch_mode"

        if act == "end":
            self._log_exec(
                kind="gateway", outcome="GW_END", track_id=track_id,
                node_id=gw_id, node_label=gw_label,
                reason="网关动作: 结束循环",
            )
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
                self._log_exec(
                    kind="gateway", outcome="ERROR", track_id=track_id,
                    node_id=gw_id, node_label=gw_label,
                    reason=f"切换模式失败: 目标模式 {target_mode} 不存在或无轨道",
                )
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

            self._log_exec(
                kind="gateway", outcome="GW_SWITCH_MODE", track_id=track_id,
                node_id=gw_id, node_label=gw_label,
                reason=f"切换模式 → {target_mode}",
                detail=f"target_track={tgt_track}, target_node={tgt_node}",
            )
            self._apply_exec_result(
                scope=scope,
                track_id=track_id,
                res=ExecutionResult(outcome="SKIPPED_NOT_READY", advance="ADVANCE", next_delay_ms=int(self._cfg.gateway_poll_delay_ms), reason="gw_switch_mode_consume"),
                now_ms=now_ms,
            )
            return

        if act == "jump_node":
            target_node_id = (getattr(gw, "target_node_id", "") or "").strip()
            if not target_node_id:
                self._log_exec(
                    kind="gateway", outcome="ERROR", track_id=track_id,
                    node_id=gw_id, node_label=gw_label,
                    reason="跳转节点失败: 未指定目标节点",
                )
                self._apply_exec_result(
                    scope=scope,
                    track_id=track_id,
                    res=ExecutionResult(outcome="ERROR", advance="ADVANCE", next_delay_ms=int(self._cfg.gateway_poll_delay_ms), reason="gw_jump_node_no_target"),
                    now_ms=now_ms,
                )
                return

            self._log_exec(
                kind="gateway", outcome="GW_JUMP_NODE", track_id=track_id,
                node_id=gw_id, node_label=gw_label,
                reason=f"跳转节点 → {target_node_id}",
            )
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

                self._log_exec(
                    kind="gateway", outcome="GW_JUMP_TRACK", track_id=track_id,
                    node_id=gw_id, node_label=gw_label,
                    reason=f"跨轨道跳转 → mode={target_mode}, track={target_track}",
                )
                self._apply_exec_result(
                    scope=scope,
                    track_id=track_id,
                    res=ExecutionResult(outcome="SKIPPED_NOT_READY", advance="ADVANCE", next_delay_ms=int(self._cfg.gateway_poll_delay_ms), reason="gw_jump_track_consume"),
                    now_ms=now_ms,
                )
                return

            if (target_track or "") == (track_id or ""):
                self._log_exec(
                    kind="gateway", outcome="GW_JUMP_TRACK", track_id=track_id,
                    node_id=gw_id, node_label=gw_label,
                    reason=f"同轨跳转 → node={target_node}",
                )
                self._jump_same_scope(scope=scope, track_id=track_id, node_id=target_node)
                self._set_next_time(scope=scope, track_id=track_id, next_time_ms=now_ms + int(self._cfg.gateway_poll_delay_ms))
                return

            self._log_exec(
                kind="gateway", outcome="GW_JUMP_TRACK", track_id=track_id,
                node_id=gw_id, node_label=gw_label,
                reason=f"跨轨道跳转 → track={target_track}, node={target_node}",
            )
            self._jump_same_scope(scope=scope, track_id=target_track, node_id=target_node)
            self._set_next_time(scope=scope, track_id=target_track, next_time_ms=now_ms + int(self._cfg.gateway_poll_delay_ms))

            self._apply_exec_result(
                scope=scope,
                track_id=track_id,
                res=ExecutionResult(outcome="SKIPPED_NOT_READY", advance="ADVANCE", next_delay_ms=int(self._cfg.gateway_poll_delay_ms), reason="gw_jump_track_consume"),
                now_ms=now_ms,
            )
            return

        if act == "exec_skill":
            # 条件已成立，尝试执行指定技能（不做模式跳转）
            exec_sid = (getattr(gw, "exec_skill_id", "") or "").strip()
            if not exec_sid:
                self._log_exec(
                    kind="gateway", outcome="ERROR", track_id=track_id,
                    node_id=gw_id, node_label=gw_label,
                    reason="网关执行技能失败: 未指定技能ID",
                )
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

            exec_skill_name = self._resolve_skill_name(exec_sid)
            self._log_exec(
                kind="gateway", outcome="GW_EXEC_SKILL", track_id=track_id,
                node_id=gw_id, node_label=gw_label,
                skill_id=exec_sid, skill_name=exec_skill_name,
                reason=f"网关触发执行技能: {exec_skill_name or exec_sid}",
            )

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