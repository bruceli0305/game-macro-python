from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

from core.profiles import ProfileContext

from rotation_editor.ast import ProbeRequirements, compile_expr_json
from rotation_editor.ast.diagnostics import Diagnostic, err, warn
from rotation_editor.core.models import RotationPreset, Track, SkillNode, GatewayNode, Condition

@dataclass(frozen=True)
class ValidationReport:
    diagnostics: List[Diagnostic]
    probes: ProbeRequirements

    def has_errors(self) -> bool:
        return any(d.level == "error" for d in (self.diagnostics or []))

    def format_text(self, *, max_lines: int = 60) -> str:
        ds = list(self.diagnostics or [])
        if not ds:
            return "校验通过：未发现问题。"

        lines: List[str] = []
        errs = [d for d in ds if d.level == "error"]
        warns = [d for d in ds if d.level == "warning"]
        infos = [d for d in ds if d.level == "info"]

        lines.append(f"错误: {len(errs)}  警告: {len(warns)}  信息: {len(infos)}")
        lines.append("")

        def fmt(d: Diagnostic) -> str:
            det = f" ({d.detail})" if d.detail else ""
            return f"- [{d.level}] [{d.code}] {d.path}: {d.message}{det}"

        for d in ds[: max(0, int(max_lines))]:
            lines.append(fmt(d))

        if len(ds) > max_lines:
            lines.append(f"... 还有 {len(ds) - max_lines} 条")

        return "\n".join(lines)


class ValidationService:
    ALLOWED_GW_ACTIONS: Set[str] = {"switch_mode", "jump_track", "jump_node", "exec_skill", "end"}

    def validate_preset(self, preset: RotationPreset, *, ctx: Optional[ProfileContext] = None) -> ValidationReport:
        diags: List[Diagnostic] = []
        probes = ProbeRequirements()

        pid = (preset.id or "").strip()
        if not pid:
            diags.append(err("preset.id.empty", "$.id", "Preset.id 不能为空"))

        skill_ids: Set[str] = set()
        if ctx is not None:
            try:
                skill_ids = set((s.id or "") for s in (ctx.skills.skills or []) if getattr(s, "id", ""))
            except Exception:
                skill_ids = set()

        self._validate_entry(preset, diags)

        # Conditions compile
        cond_ids: Set[str] = set()
        for ci, c in enumerate(preset.conditions or []):
            cid = (c.id or "").strip()
            if not cid:
                diags.append(err("cond.id.empty", f"$.conditions[{ci}].id", "Condition.id 不能为空"))
                continue
            if cid in cond_ids:
                diags.append(err("cond.id.dup", f"$.conditions[{ci}].id", "Condition.id 重复", detail=cid))
                continue
            cond_ids.add(cid)

            self._validate_condition_ast(c, path=f"$.conditions[{ci}]", ctx=ctx, diags=diags, probes=probes)

        # Track/node validation
        node_ids: Set[str] = set()
        mode_ids: Set[str] = set((m.id or "").strip() for m in (preset.modes or []) if (m.id or "").strip())

        def validate_track_nodes(track: Track, *, path: str, scope: str, mode_id: str = "") -> None:
            tid = (track.id or "").strip()
            if not tid:
                diags.append(err("track.id.empty", f"{path}.id", "Track.id 不能为空"))

            for ni, n in enumerate(track.nodes or []):
                npath = f"{path}.nodes[{ni}]"
                nid = (getattr(n, "id", "") or "").strip()
                if not nid:
                    diags.append(err("node.id.empty", f"{npath}.id", "Node.id 不能为空"))
                elif nid in node_ids:
                    diags.append(err("node.id.dup", f"{npath}.id", "Node.id 重复", detail=nid))
                else:
                    node_ids.add(nid)

                kind = (getattr(n, "kind", "") or "").strip().lower()
                if kind == "skill" and isinstance(n, SkillNode):
                    self._validate_skill_node(n, path=npath, ctx=ctx, skill_ids=skill_ids, diags=diags, probes=probes)
                elif kind == "gateway" and isinstance(n, GatewayNode):
                    self._validate_gateway_node(
                        preset=preset,
                        gw=n,
                        path=npath,
                        ctx=ctx,
                        diags=diags,
                        probes=probes,
                        scope=scope,
                        current_mode_id=mode_id,
                        current_track=track,
                        current_track_id=tid,
                        mode_ids=mode_ids,
                    )
                else:
                    diags.append(warn("node.kind.unknown", f"{npath}.kind", "未知节点 kind", detail=kind))

        for ti, t in enumerate(preset.global_tracks or []):
            validate_track_nodes(t, path=f"$.global_tracks[{ti}]", scope="global", mode_id="")

        for mi, m in enumerate(preset.modes or []):
            mid = (m.id or "").strip()
            for ti, t in enumerate(m.tracks or []):
                validate_track_nodes(t, path=f"$.modes[{mi}].tracks[{ti}]", scope="mode", mode_id=mid)

        return ValidationReport(diagnostics=diags, probes=probes)

    def _validate_entry(self, preset: RotationPreset, diags: List[Diagnostic]) -> None:
        """
        校验 preset.entry 的基础合法性：
        - scope: 必须为 global/mode
        - scope=mode 时 mode_id 不能为空
        - track_id / node_id 不能为空
        - track_id 必须指向存在的轨道
        - node_id 必须属于该轨道

        为避免导入时循环依赖，这里在函数内部延迟导入 runtime_state：
        - rotation_editor.core.runtime.__init__ 会导入 engine
        - engine 会导入 ValidationService
        - 若在模块顶层导入 runtime_state 会导致 ValidationService 尚未初始化完毕就被引用
        """
        entry = getattr(preset, "entry", None)
        if entry is None:
            diags.append(err("entry.missing", "$.entry", "入口 entry 缺失（新引擎强制要求）"))
            return

        scope = (getattr(entry, "scope", "") or "global").strip().lower()
        mode_id = (getattr(entry, "mode_id", "") or "").strip()
        track_id = (getattr(entry, "track_id", "") or "").strip()
        node_id = (getattr(entry, "node_id", "") or "").strip()

        if scope not in ("global", "mode"):
            diags.append(err("entry.scope.invalid", "$.entry.scope", "entry.scope 必须是 global/mode", detail=scope))

        if scope == "mode" and not mode_id:
            diags.append(err("entry.mode_id.empty", "$.entry.mode_id", "entry.scope=mode 时 entry.mode_id 不能为空"))

        if not track_id:
            diags.append(err("entry.track_id.empty", "$.entry.track_id", "entry.track_id 不能为空"))

        if not node_id:
            diags.append(err("entry.node_id.empty", "$.entry.node_id", "entry.node_id 不能为空（入口必须指向节点）"))

        # 若前面已有 scope/track/node 基础错误，后续引用检查可以跳过
        if any(d.code.startswith("entry.") and d.level == "error" for d in diags):
            return

        # 延迟导入，避免 import 阶段循环依赖
        try:
            from rotation_editor.core.runtime.runtime_state import find_track_in_preset, track_has_node
        except Exception as e:
            diags.append(
                err(
                    "entry.runtime_state.import_failed",
                    "$.entry",
                    "内部错误：无法导入 runtime_state 以校验入口轨道/节点",
                    detail=str(e),
                )
            )
            return

        # 轨道存在性检查
        tr = find_track_in_preset(preset, scope=scope, mode_id=mode_id, track_id=track_id)
        if tr is None:
            diags.append(
                err(
                    "entry.track.missing",
                    "$.entry.track_id",
                    "entry.track_id 指向的轨道不存在",
                    detail=track_id,
                )
            )
            return

        # 节点属于该轨道
        if not track_has_node(tr, node_id):
            diags.append(
                err(
                    "entry.node.missing",
                    "$.entry.node_id",
                    "entry.node_id 不属于指定轨道",
                    detail=node_id,
                )
            )

    def _validate_condition_ast(self, c: Condition, *, path: str, ctx: Optional[ProfileContext], diags: List[Diagnostic], probes: ProbeRequirements) -> None:
        expr = getattr(c, "expr", None)
        if not isinstance(expr, dict) or not expr:
            diags.append(err("cond.expr.invalid", f"{path}.expr", "Condition.expr 必须是 AST JSON dict"))
            return
        res = compile_expr_json(expr, ctx=ctx, path=f"{path}.expr")
        diags.extend(res.diagnostics)
        probes.merge(res.probes)

    def _validate_skill_node(self, n: SkillNode, *, path: str, ctx: Optional[ProfileContext], skill_ids: Set[str], diags: List[Diagnostic], probes: ProbeRequirements) -> None:
        sid = (n.skill_id or "").strip()
        if not sid:
            diags.append(err("skill.ref.empty", f"{path}.skill_id", "SkillNode.skill_id 不能为空"))
        elif ctx is not None and sid not in skill_ids:
            diags.append(err("skill.ref.missing", f"{path}.skill_id", "引用了不存在的 skill_id", detail=sid))

        se = getattr(n, "start_expr", None)
        if se is not None:
            if not isinstance(se, dict) or not se:
                diags.append(err("node.start_expr.invalid", f"{path}.start_expr", "start_expr 必须是 AST JSON dict"))
            else:
                res = compile_expr_json(se, ctx=ctx, path=f"{path}.start_expr")
                diags.extend(res.diagnostics)
                probes.merge(res.probes)

        ce = getattr(n, "complete_expr", None)
        if ce is not None:
            if not isinstance(ce, dict) or not ce:
                diags.append(err("node.complete_expr.invalid", f"{path}.complete_expr", "complete_expr 必须是 AST JSON dict"))
            else:
                res = compile_expr_json(ce, ctx=ctx, path=f"{path}.complete_expr")
                diags.extend(res.diagnostics)
                probes.merge(res.probes)

    def _validate_gateway_node(
        self,
        *,
        preset: RotationPreset,
        gw: GatewayNode,
        path: str,
        ctx: Optional[ProfileContext],
        diags: List[Diagnostic],
        probes: ProbeRequirements,
        scope: str,
        current_mode_id: str,
        current_track: Track,
        current_track_id: str,
        mode_ids: Set[str],
    ) -> None:
        action = (gw.action or "switch_mode").strip().lower() or "switch_mode"
        if action not in self.ALLOWED_GW_ACTIONS:
            diags.append(err("gw.action.invalid", f"{path}.action", "GatewayNode.action 非法", detail=action))

        ce = getattr(gw, "condition_expr", None)
        cid = (getattr(gw, "condition_id", "") or "").strip()

        if ce is not None:
            if not isinstance(ce, dict) or not ce:
                diags.append(err("gw.cond_expr.invalid", f"{path}.condition_expr", "condition_expr 必须是 AST JSON dict"))
            else:
                res = compile_expr_json(ce, ctx=ctx, path=f"{path}.condition_expr")
                diags.extend(res.diagnostics)
                probes.merge(res.probes)
        elif cid:
            cobj = next((c for c in (preset.conditions or []) if (c.id or "").strip() == cid), None)
            if cobj is None:
                diags.append(err("gw.cond.missing", f"{path}.condition_id", "condition_id 指向不存在的 Condition", detail=cid))
            else:
                expr = getattr(cobj, "expr", None)
                if not isinstance(expr, dict) or not expr:
                    diags.append(err("gw.cond.expr.invalid", f"{path}.condition_id", "引用的 Condition.expr 不是 AST JSON dict", detail=cid))
                else:
                    res = compile_expr_json(expr, ctx=ctx, path=f"$.conditions[id={cid}].expr")
                    diags.extend(res.diagnostics)
                    probes.merge(res.probes)

        if action == "end":
            return

        if action == "switch_mode":
            tm = (getattr(gw, "target_mode_id", "") or "").strip()
            if not tm:
                diags.append(err("gw.switch_mode.no_target", f"{path}.target_mode_id", "switch_mode 必须设置 target_mode_id"))
            elif tm not in mode_ids:
                diags.append(err("gw.switch_mode.bad_target", f"{path}.target_mode_id", "target_mode_id 不存在", detail=tm))
            return

        if action == "jump_node":
            tn = (getattr(gw, "target_node_id", "") or "").strip()
            if not tn:
                diags.append(err("gw.jump_node.no_target", f"{path}.target_node_id", "jump_node 必须设置 target_node_id"))
                return
            ok = any((getattr(n, "id", "") or "").strip() == tn for n in (current_track.nodes or []))
            if not ok:
                diags.append(err(
                    "gw.jump_node.target_not_in_current_track",
                    f"{path}.target_node_id",
                    "jump_node 的 target_node_id 不属于当前轨道",
                    detail=f"track_id={current_track_id}, node_id={tn}",
                ))
            return

        if action == "jump_track":
            tt = (getattr(gw, "target_track_id", "") or "").strip()
            tn = (getattr(gw, "target_node_id", "") or "").strip()
            if not tt:
                diags.append(err("gw.jump_track.no_track", f"{path}.target_track_id", "jump_track 必须设置 target_track_id"))
            if not tn:
                diags.append(err("gw.jump_track.no_node", f"{path}.target_node_id", "jump_track 必须设置 target_node_id"))
            return

        if action == "exec_skill":
            exec_sid = (getattr(gw, "exec_skill_id", "") or "").strip()
            if not exec_sid:
                diags.append(
                    err(
                        "gw.exec_skill.no_id",
                        f"{path}.exec_skill_id",
                        "exec_skill 必须设置 exec_skill_id（要执行的技能 ID）",
                    )
                )
                return

            # ctx 若提供，则检查该技能是否存在
            if ctx is not None:
                try:
                    skill_ids = set(
                        (s.id or "") for s in (ctx.skills.skills or []) if getattr(s, "id", "")
                    )
                except Exception:
                    skill_ids = set()
                if exec_sid not in skill_ids:
                    diags.append(
                        err(
                            "gw.exec_skill.bad_skill",
                            f"{path}.exec_skill_id",
                            "exec_skill_id 指向不存在的技能",
                            detail=exec_sid,
                        )
                    )
            return