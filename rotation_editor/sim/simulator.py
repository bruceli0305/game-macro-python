# rotation_editor/sim/simulator.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, List, Tuple, Any

from core.profiles import ProfileContext
from core.models.skill import Skill  # 用于读取 cast.readbar_ms / cooldown_ms

from rotation_editor.core.models import (
    RotationPreset,
    SkillNode,
    GatewayNode,
    Track,
    Condition,
)
from rotation_editor.core.runtime.runtime_state import (
    GlobalRuntimeState,
    ModeRuntimeState,
    build_global_runtime,
    build_mode_runtime,
)
from rotation_editor.core.runtime.scheduler import Scheduler

from rotation_editor.ast import (
    decode_expr,
    evaluate as eval_ast,
    EvalContext,
    TriBool,
)
from rotation_editor.ast.nodes import And, Or, Not, SkillMetricGE

from .models import SkillSimState, SimConfig, SimResult, SimEvent


# ---------- AST evaluator 适配：像素返回 None，指标从 SkillSimState 读取 ----------

class _NullPixelSampler:
    """
    推演环境下不做真实取色：
    - 所有 pixel 原子都会得到 Unknown（TriBool.value=None），
      这样条件只会真正依赖 SkillMetricGE 等“指标型”原子。
    """
    def sample_rgb_abs(
        self,
        *,
        monitor_key: str,
        x_abs: int,
        y_abs: int,
        sample,
        require_inside: bool = False,
    ):
        return None


class _SimMetricProvider:
    """
    将 SkillSimState.metrics 暴露为 MetricProvider：
    - metric 名直接对应 SkillSimState.metrics 的 key：
        "success" / "attempt_started" / "key_sent_ok" / "cast_started" / "fail"
    """
    def __init__(self, skills_state: Dict[str, SkillSimState]) -> None:
        self._skills = skills_state

    def get_metric(self, skill_id: str, metric: Any) -> Optional[int]:
        sid = (skill_id or "").strip()
        if not sid:
            return None
        st = self._skills.get(sid)
        if st is None:
            return 0
        key = str(metric or "").strip()
        try:
            return int(st.metrics.get(key, 0))
        except Exception:
            return 0


@dataclass
class RotationSimulator:
    """
    RotationPreset 离线推演器（核心逻辑）：

    - ctx    : ProfileContext（提供技能配置/冷却等信息）
    - preset : 要推演的 RotationPreset
    - cfg    : 推演配置（最大时长/最大节点数等）

    当前实现内容：
    - 复用 GlobalRuntimeState / ModeRuntimeState / Scheduler 的调度逻辑；
    - 对 SkillNode 做“理想成功”推演（读条 + 冷却 + 默认间隔）；
    - 对 GatewayNode：
        * 实际编译/求值 AST 条件（仅指标相关 SkillMetricGE 有效，像素原子视为 Unknown）；
        * 支持 action="end"：条件成立时结束推演；
        * 支持 action="exec_skill"：条件成立时额外执行一次指定技能（不改变轨道结构）；
        * 支持 action="jump_node" ：在当前轨道内跳转到指定节点（不 advance 当前轨道）；
        * 支持 action="jump_track"：在当前作用域内，将目标轨道跳到目标节点并快速调度；
        * 其它动作（如 switch_mode）当前只记录事件，不改变模式结构。
    """

    ctx: ProfileContext
    preset: RotationPreset
    cfg: SimConfig = field(default_factory=SimConfig)

    # ---------- 对外主入口 ----------

    def run(self) -> SimResult:
        """
        主入口：根据当前 ctx + preset + cfg，进行一次完整推演。
        """
        # ---------- 初始化技能状态 ----------
        skills_state: Dict[str, SkillSimState] = self._init_skills_state()

        # ---------- 构建运行时状态 ----------
        now_ms = 0

        global_rt: GlobalRuntimeState = build_global_runtime(self.preset, now_ms=now_ms)

        entry = getattr(self.preset, "entry", None)
        mode_rt: Optional[ModeRuntimeState] = None
        if entry is not None:
            scope = (getattr(entry, "scope", "global") or "global").strip().lower()
            mode_id = (getattr(entry, "mode_id", "") or "").strip()
            if scope == "mode" and mode_id:
                mode_rt = build_mode_runtime(self.preset, mode_id, now_ms=now_ms)

        # 根据 entry(track_id/node_id) 应用初始位置
        self._apply_entry(global_rt, mode_rt, now_ms)

        scheduler = Scheduler()
        events: List[SimEvent] = []
        exec_nodes = 0
        stop_flag = False

        # 结合 SimConfig 和 preset 本身的限制，算出有效上限
        max_run_ms = int(self.cfg.max_run_ms)
        if max_run_ms <= 0:
            max_run_ms = 120_000

        if getattr(self.preset, "max_run_seconds", 0) > 0:
            preset_ms = int(self.preset.max_run_seconds) * 1000
            if preset_ms > 0:
                max_run_ms = min(max_run_ms, preset_ms)

        max_exec_nodes = int(self.cfg.max_exec_nodes)
        if max_exec_nodes <= 0:
            max_exec_nodes = 500
        if getattr(self.preset, "max_exec_nodes", 0) > 0:
            preset_limit = int(self.preset.max_exec_nodes)
            if preset_limit > 0:
                max_exec_nodes = min(max_exec_nodes, preset_limit)

        # ---------- 调度循环 ----------
        while True:
            # 终止条件：时长 / 节点数
            if now_ms >= max_run_ms:
                break
            if exec_nodes >= max_exec_nodes:
                break
            if stop_flag:
                break

            item = scheduler.choose_next(now_ms=now_ms, global_rt=global_rt, mode_rt=mode_rt)
            if item is None:
                # 没有 ready 的轨道，尝试看看未来是否还有 wakeup
                wake = scheduler.next_wakeup_ms(global_rt=global_rt, mode_rt=mode_rt)
                if wake is None:
                    # 确实没有下一个事件了
                    break
                if wake <= now_ms:
                    # 防御：避免死循环，至少往前走 1ms
                    now_ms += 1
                else:
                    now_ms = int(wake)
                continue

            # 选中了具体的轨道和 scope
            if item.scope == "global":
                rt = global_rt.get(item.track_id)
                if rt is None or not rt.track.nodes:
                    # 无节点的轨道，从 runtime 中移除
                    global_rt.remove(item.track_id)
                    continue
                node = rt.current_node()
                node_index = rt.current_node_index()
                if node is None or node_index < 0:
                    # 理论上不该发生，防御性 advance 一下
                    rt.advance()
                    continue

                scope = "global"
                mode_id = ""
                track_id = item.track_id

            else:  # "mode"
                if mode_rt is None:
                    # 没有 mode runtime，忽略
                    continue
                mode_rt.ensure_step_runnable()
                rt2 = mode_rt.tracks.get(item.track_id)
                if rt2 is None or not rt2.track.nodes or rt2.done():
                    continue
                node = rt2.current_node()
                node_index = rt2.current_node_index()
                if node is None or node_index < 0:
                    rt2.advance()
                    mode_rt.ensure_step_runnable()
                    continue

                scope = "mode"
                mode_id = mode_rt.mode_id or ""
                track_id = item.track_id

            # ---------- 执行节点（推演版） ----------
            label = getattr(node, "label", "") or getattr(node, "kind", "") or "node"
            node_kind = (getattr(node, "kind", "") or "").strip().lower() or "node"

            if isinstance(node, SkillNode):
                outcome, reason, delay_ms = self._simulate_skill_node(
                    sn=node,
                    now_ms=now_ms,
                    skills_state=skills_state,
                )
                advance_flag = True
            elif isinstance(node, GatewayNode):
                outcome, reason, delay_ms, advance_flag, stop_here = self._simulate_gateway_node(
                    gw=node,
                    now_ms=now_ms,
                    skills_state=skills_state,
                    scope=scope,
                    track_id=track_id,
                    global_rt=global_rt,
                    mode_rt=mode_rt,
                )
                if stop_here:
                    stop_flag = True
            else:
                # 未知节点：直接视为“跳过并前进”，给一个小 delay
                outcome = "UNKNOWN_NODE"
                reason = "unknown_node_kind"
                delay_ms = self._default_gap_ms()
                advance_flag = True

            # 记录事件
            ev = SimEvent(
                index=exec_nodes,
                t_ms=now_ms,
                scope=scope,
                mode_id=mode_id,
                track_id=track_id,
                node_id=getattr(node, "id", "") or "",
                node_kind=node_kind,
                label=label,
                outcome=outcome,
                reason=reason,
            )
            events.append(ev)
            exec_nodes += 1

            # 若已要求立即停止（GW_END），不再为当前轨道安排后续时间
            if stop_flag:
                break

            # 更新时间与轨道的 next_time_ms + advance
            delay_ms = max(0, int(delay_ms))
            next_time = now_ms + delay_ms

            if item.scope == "global":
                rt = global_rt.get(track_id)
                if rt is not None:
                    rt.next_time_ms = int(next_time)
                    if advance_flag:
                        rt.advance()
            else:
                if mode_rt is not None:
                    rt2 = mode_rt.tracks.get(track_id)
                    if rt2 is not None:
                        rt2.next_time_ms = int(next_time)
                        if advance_flag:
                            rt2.advance()
                            mode_rt.ensure_step_runnable()

            # 时间前进到本次执行的“结束时刻”
            now_ms = int(next_time)

        # ---------- 返回结果 ----------
        return SimResult(
            preset_id=self.preset.id or "",
            events=events,
            final_time_ms=now_ms,
            final_metrics=skills_state,
        )

    # ---------- 内部工具：入口应用 ----------

    def _apply_entry(
        self,
        global_rt: GlobalRuntimeState,
        mode_rt: Optional[ModeRuntimeState],
        now_ms: int,
    ) -> None:
        """
        根据 preset.entry 设置初始的轨道/节点位置：

        - scope="global" 时，使用 entry.track_id / entry.node_id 定位到对应全局轨道；
        - scope="mode" 时，使用 entry.mode_id / entry.track_id / entry.node_id 定位到模式轨道。
        """
        entry = getattr(self.preset, "entry", None)
        if entry is None:
            return

        scope = (getattr(entry, "scope", "global") or "global").strip().lower()
        track_id = (getattr(entry, "track_id", "") or "").strip()
        node_id = (getattr(entry, "node_id", "") or "").strip()

        if scope == "global":
            if not track_id:
                return
            rt = global_rt.get(track_id)
            if rt is None:
                return
            if node_id:
                rt.jump_to_node_id(node_id)
            rt.next_time_ms = int(now_ms)
            return

        # mode 范围（当前实现只做最小设置，不重建 mode_rt）
        if mode_rt is None:
            return
        if not track_id:
            return
        rt2 = mode_rt.tracks.get(track_id)
        if rt2 is None:
            return
        if node_id:
            rt2.jump_to_node_id(node_id)
        rt2.next_time_ms = int(now_ms)
        mode_rt.maybe_backstep(track_id)

    # ---------- 内部工具：技能状态初始化 ----------

    def _init_skills_state(self) -> Dict[str, SkillSimState]:
        """
        根据当前 ProfileContext 中的 skills 初始化每个技能的模拟状态。
        """
        out: Dict[str, SkillSimState] = {}
        try:
            for s in getattr(self.ctx.skills, "skills", []) or []:
                sid = getattr(s, "id", "") or ""
                if not sid:
                    continue
                out[sid] = SkillSimState()
        except Exception:
            # 防御：出现错误时只返回当前已构建部分
            pass
        return out

    # ---------- 内部工具：读取配置 ----------

    def _default_gap_ms(self) -> int:
        """
        读取 base.exec.default_skill_gap_ms，失败时回退为 50ms。
        """
        try:
            ex = getattr(self.ctx.base, "exec", None)
            if ex is None:
                return 50
            v = int(getattr(ex, "default_skill_gap_ms", 50) or 50)
            if v < 0:
                v = 0
            if v > 10**6:
                v = 10**6
            return v
        except Exception:
            return 50

    def _find_skill_obj(self, skill_id: str) -> Optional[Skill]:
        """
        在 ProfileContext.skills.skills 里根据 id 查找 Skill 对象。
        """
        sid = (skill_id or "").strip()
        if not sid:
            return None
        try:
            for s in getattr(self.ctx.skills, "skills", []) or []:
                if getattr(s, "id", "") == sid:
                    return s
        except Exception:
            return None
        return None

    # ---------- 节点推演：SkillNode ----------

    def _simulate_skill_node(
        self,
        *,
        sn: SkillNode,
        now_ms: int,
        skills_state: Dict[str, SkillSimState],
    ) -> Tuple[str, str, int]:
        """
        推演单个 SkillNode 的行为（理想环境）：

        规则：
        - 若当前 now_ms < next_available_ms => 视为冷却未就绪，跳过本节点：
            * outcome="SKIPPED_CD"
            * reason="cd_not_ready"
            * delay = default_gap_ms
        - 否则：
            * 计数 metrics:
                - attempt_started / cast_started / key_sent_ok / success 各 +1
            * 读条时间 cast_ms：
                - override_cast_ms >0 优先；
                - 否则 Skill.cast.readbar_ms；
                - 都为 0 时，回退为 1000ms。
            * 冷却时间 cooldown_ms：
                - 使用 Skill.cooldown_ms（来自 GW2 JSON），<0 时视为 0。
            * next_available_ms = now_ms + cast_ms + cooldown_ms
            * delay = cast_ms + default_gap_ms
        """
        sid = (sn.skill_id or "").strip()
        if sid not in skills_state:
            skills_state[sid] = SkillSimState()
        st = skills_state[sid]

        # 冷却检查
        if now_ms < st.next_available_ms:
            return (
                "SKIPPED_CD",
                "cd_not_ready",
                self._default_gap_ms(),
            )

        # 读条时间
        cast_ms = 0
        if sn.override_cast_ms is not None and int(sn.override_cast_ms) > 0:
            cast_ms = int(sn.override_cast_ms)
        else:
            skill_obj = self._find_skill_obj(sid)
            if skill_obj is not None:
                try:
                    cast_ms = int(getattr(getattr(skill_obj, "cast", None), "readbar_ms", 0) or 0)
                except Exception:
                    cast_ms = 0

        if cast_ms <= 0:
            cast_ms = 1000  # 兜底读条 1s

        # 冷却时间
        cd_ms = 0
        skill_obj = self._find_skill_obj(sid)
        if skill_obj is not None:
            try:
                cd_ms = int(getattr(skill_obj, "cooldown_ms", 0) or 0)
            except Exception:
                cd_ms = 0
        if cd_ms < 0:
            cd_ms = 0

        # 更新指标
        for key in ("attempt_started", "cast_started", "key_sent_ok", "success"):
            st.metrics[key] = st.metrics.get(key, 0) + 1

        # 更新下一次可用时间
        st.next_available_ms = int(now_ms + cast_ms + cd_ms)
        skills_state[sid] = st

        delay_ms = cast_ms + self._default_gap_ms()
        return "SUCCESS", "sim_success", delay_ms

    # ---------- 网关条件加载/求值 ----------

    def _load_gateway_condition_expr(self, gw: GatewayNode) -> Optional[Dict[str, Any]]:
        """
        优先使用 gw.condition_expr（内联 AST）；
        否则根据 condition_id 在 preset.conditions 里查找对应 Condition.expr。
        """
        ce = getattr(gw, "condition_expr", None)
        if isinstance(ce, dict) and ce:
            return dict(ce)

        cid = (getattr(gw, "condition_id", "") or "").strip()
        if not cid:
            return None

        for c in (self.preset.conditions or []):
            if (c.id or "").strip() == cid:
                expr = getattr(c, "expr", None)
                if isinstance(expr, dict) and expr:
                    return dict(expr)
                break
        return None

    def _eval_gateway_condition(
        self,
        gw: GatewayNode,
        skills_state: Dict[str, SkillSimState],
    ) -> TriBool:
        """
        在推演环境中对网关条件 AST 求值：

        - 若既无 condition_expr 又无 condition_id：视为恒真（TriBool.t()）；
        - 若 AST 解析失败：视为 False（TriBool.f("cond_decode_error")）；
        - 像素相关原子通过 _NullPixelSampler 得到 Unknown；
        - SkillMetricGE 通过 _SimMetricProvider 使用 skills_state 中的 metrics。
        """
        expr_dict = self._load_gateway_condition_expr(gw)
        if expr_dict is None:
            # 无条件 => 恒真
            return TriBool.t()

        expr_obj, diags = decode_expr(expr_dict, path="$.gateway.condition")
        if expr_obj is None or any(d.is_error() for d in (diags or [])):
            return TriBool.f("cond_decode_error")

        sampler = _NullPixelSampler()
        metrics = _SimMetricProvider(skills_state)

        ctx = EvalContext(
            profile=self.ctx,
            sampler=sampler,
            metrics=metrics,
            baseline=None,
        )
        return eval_ast(expr_obj, ctx)

    def _reset_metrics_for_gateway(
        self,
        gw: GatewayNode,
        skills_state: Dict[str, SkillSimState],
    ) -> None:
        """
        若 gw.reset_metrics_on_fire=True，则解析其条件 AST，
        找出其中所有 SkillMetricGE(skill_id, metric)，并将对应计数归零。
        """
        if not getattr(gw, "reset_metrics_on_fire", False):
            return

        expr_dict = self._load_gateway_condition_expr(gw)
        if not isinstance(expr_dict, dict) or not expr_dict:
            return

        expr_obj, diags = decode_expr(expr_dict, path="$.gateway.condition")
        if expr_obj is None or any(d.is_error() for d in (diags or [])):
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
            # 其它节点：忽略

        walk(expr_obj)

        for sid, metric in pairs:
            st = skills_state.get(sid)
            if st is None:
                continue
            st.metrics[metric] = 0

    # ---------- 节点推演：GatewayNode ----------

    def _simulate_gateway_node(
        self,
        *,
        gw: GatewayNode,
        now_ms: int,
        skills_state: Dict[str, SkillSimState],
        scope: str,
        track_id: str,
        global_rt: GlobalRuntimeState,
        mode_rt: Optional[ModeRuntimeState],
    ) -> Tuple[str, str, int, bool, bool]:
        """
        网关节点推演：

        返回：
        - outcome    : 事件结果字符串
        - reason     : 具体原因说明
        - delay_ms   : 当前节点完成后到下次调度的延迟
        - advance    : 是否推进轨道当前索引（True 相当于“消费掉”该节点）
        - stop_here  : 若为 True，则本次执行后立即结束整个推演

        规则：
        1) 先用 _eval_gateway_condition 求值 TriBool：
            - value is not True（False 或 None） => 条件不成立：
                * outcome="GW_COND_FALSE"
                * reason=tri.reason 或 "cond_false_or_unknown"
                * delay=default_gap_ms
                * advance=True
        2) 条件成立：
            - 若 reset_metrics_on_fire=True，重置相关 skill metrics
            - 根据 action 分支：
                * "end" :
                    - outcome="GW_END"
                    - reason="gw_end"
                    - delay=0
                    - advance=True
                    - stop_here=True
                * "exec_skill":
                    - 额外执行一次 exec_skill_id 对应的技能（以“理想成功”规则）
                    - outcome 前缀 "GW_EXEC_" + 子结果
                    - delay=该技能的 delay
                    - advance=True
                * "jump_node":
                    - 在当前 scope / track 内，将 runtime 跳到 target_node_id，
                      不 advance 当前轨道：
                        outcome="GW_JUMP_NODE"
                        reason="gw_jump_node"
                        delay=default_gap_ms
                        advance=False
                * "jump_track":
                    - 在当前作用域内，将目标轨道跳到目标节点，并设置其 next_time_ms=now+default_gap；
                      当前轨道仍被消费（advance=True）：
                        outcome="GW_JUMP_TRACK"
                        reason="gw_jump_track"
                        delay=default_gap_ms
                        advance=True
                * 其它（switch_mode/...）:
                    - 当前实现只记录 outcome="GW_TAKEN"，reason="gw_action:xxx"
                    - 不改变模式结构，仅 advance=True，delay=default_gap_ms
        """
        tri = self._eval_gateway_condition(gw, skills_state)
        if tri.value is not True:
            reason = tri.reason or "cond_false_or_unknown"
            return "GW_COND_FALSE", reason, self._default_gap_ms(), True, False

        # 条件已成立
        self._reset_metrics_for_gateway(gw, skills_state)

        act = (gw.action or "switch_mode").strip().lower() or "switch_mode"

        # 结束执行
        if act == "end":
            return "GW_END", "gw_end", 0, True, True

        # 执行一次技能（不改变轨道结构）
        if act == "exec_skill":
            exec_sid = (gw.exec_skill_id or "").strip()
            if not exec_sid:
                return "GW_EXEC_SKILL_NO_ID", "gw_exec_skill_no_id", self._default_gap_ms(), True, False

            dummy_node = SkillNode(
                id="",
                kind="skill",
                label=f"[GW]{gw.label or ''}",
                skill_id=exec_sid,
            )
            outcome, reason, delay = self._simulate_skill_node(
                sn=dummy_node,
                now_ms=now_ms,
                skills_state=skills_state,
            )
            return f"GW_EXEC_{outcome}", reason, delay, True, False

        # 当前 runtime helpers
        def _get_current_rt():
            if scope == "global":
                return global_rt.get(track_id)
            if mode_rt is not None:
                return mode_rt.tracks.get(track_id)
            return None

        # 在当前轨道内跳转到指定节点
        if act == "jump_node":
            target_node_id = (gw.target_node_id or "").strip()
            if not target_node_id:
                return "GW_JUMP_NODE_NO_TARGET", "gw_jump_node_no_target", self._default_gap_ms(), True, False

            rt = _get_current_rt()
            if rt is not None:
                rt.jump_to_node_id(target_node_id)
            return "GW_JUMP_NODE", "gw_jump_node", self._default_gap_ms(), False, False

        # 在当前作用域内跳转到另一条轨道
        if act == "jump_track":
            target_track_id = (gw.target_track_id or "").strip()
            target_node_id = (gw.target_node_id or "").strip()
            if not target_track_id or not target_node_id:
                return "GW_JUMP_TRACK_NO_TARGET", "gw_jump_track_missing_target", self._default_gap_ms(), True, False

            # 找目标 runtime
            if scope == "global":
                rt_dest = global_rt.get(target_track_id)
            else:
                rt_dest = mode_rt.tracks.get(target_track_id) if mode_rt is not None else None

            if rt_dest is not None:
                rt_dest.jump_to_node_id(target_node_id)
                # 让目标轨道尽快被调度
                rt_dest.next_time_ms = int(now_ms + self._default_gap_ms())

            return "GW_JUMP_TRACK", "gw_jump_track", self._default_gap_ms(), True, False

        # 其它动作目前只记录一次“网关被触发”的事件，不改变路径
        return "GW_TAKEN", f"gw_action:{act}", self._default_gap_ms(), True, False