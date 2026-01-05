from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from core.profiles import ProfileContext
from rotation_editor.core.models import RotationPreset, Mode, Track, SkillNode, GatewayNode, Condition


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    location: str
    message: str
    detail: str = ""


class PresetValidator:
    """
    启动前校验器：不考虑兼容，严格检查。
    - 任何关键 ID 为空 / 重复：直接报错
    - condition.kind 必须是 "groups"
    - gateway action 必须在允许集合内，并且参数与作用域一致
    - 可选：结合 ProfileContext 校验 skill/point 引用存在
    """

    ALLOWED_ACTIONS: Set[str] = {"switch_mode", "jump_track", "jump_node", "end"}
    ALLOWED_GROUP_OPS: Set[str] = {"and", "or"}
    ALLOWED_ATOM_TYPES: Set[str] = {"pixel_point", "pixel_skill", "skill_cast_ge"}

    def validate(self, preset: RotationPreset, ctx: Optional[ProfileContext] = None) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []

        # ---------- 基础：preset ----------
        pid = (preset.id or "").strip()
        if not pid:
            issues.append(ValidationIssue("preset.id.empty", "preset", "Preset.id 不能为空"))

        # ---------- 预构建：skills/points ----------
        skill_ids: Set[str] = set()
        point_ids: Set[str] = set()
        if ctx is not None:
            skill_ids = set(s.id for s in (ctx.skills.skills or []) if getattr(s, "id", ""))
            point_ids = set(p.id for p in (ctx.points.points or []) if getattr(p, "id", ""))

        # ---------- 模式 ID ----------
        mode_ids: Set[str] = set()
        for mi, m in enumerate(preset.modes or []):
            mid = (m.id or "").strip()
            if not mid:
                issues.append(ValidationIssue("mode.id.empty", f"modes[{mi}]", "Mode.id 不能为空"))
                continue
            if mid in mode_ids:
                issues.append(ValidationIssue("mode.id.dup", f"modes[{mi}]", "Mode.id 重复", detail=mid))
                continue
            mode_ids.add(mid)

        # ---------- Track / Node ID 唯一性 ----------
        track_ids_global: Set[str] = set()
        track_ids_by_mode: Dict[str, Set[str]] = {mid: set() for mid in mode_ids}
        node_ids: Set[str] = set()

        def check_track_nodes(track: Track, loc: str) -> None:
            for ni, n in enumerate(track.nodes or []):
                nid = (getattr(n, "id", "") or "").strip()
                if not nid:
                    issues.append(ValidationIssue("node.id.empty", f"{loc}.nodes[{ni}]", "Node.id 不能为空"))
                elif nid in node_ids:
                    issues.append(ValidationIssue("node.id.dup", f"{loc}.nodes[{ni}]", "Node.id 重复", detail=nid))
                else:
                    node_ids.add(nid)

                kind = (getattr(n, "kind", "") or "").strip().lower()
                if kind == "skill" and isinstance(n, SkillNode):
                    sid = (n.skill_id or "").strip()
                    if not sid:
                        issues.append(ValidationIssue("skill.ref.empty", f"{loc}.nodes[{ni}]", "SkillNode.skill_id 不能为空"))
                    elif ctx is not None and sid not in skill_ids:
                        issues.append(ValidationIssue("skill.ref.missing", f"{loc}.nodes[{ni}]", "引用了不存在的 skill_id", detail=sid))

                if kind == "gateway" and isinstance(n, GatewayNode):
                    self._check_gateway_node(n, preset, loc=f"{loc}.nodes[{ni}]", mode_ids=mode_ids, issues=issues)

        # 全局轨道
        for ti, t in enumerate(preset.global_tracks or []):
            tid = (t.id or "").strip()
            loc = f"global_tracks[{ti}]"
            if not tid:
                issues.append(ValidationIssue("track.id.empty", loc, "全局 Track.id 不能为空"))
            elif tid in track_ids_global:
                issues.append(ValidationIssue("track.id.dup", loc, "全局 Track.id 重复", detail=tid))
            else:
                track_ids_global.add(tid)
            check_track_nodes(t, loc)

        # 模式轨道
        for mi, m in enumerate(preset.modes or []):
            mid = (m.id or "").strip()
            if not mid:
                continue
            seen = track_ids_by_mode.setdefault(mid, set())
            for ti, t in enumerate(m.tracks or []):
                tid = (t.id or "").strip()
                loc = f"modes[{mi}].tracks[{ti}]"
                if not tid:
                    issues.append(ValidationIssue("track.id.empty", loc, "模式 Track.id 不能为空"))
                elif tid in seen:
                    issues.append(ValidationIssue("track.id.dup", loc, "同一模式下 Track.id 重复", detail=tid))
                else:
                    seen.add(tid)
                check_track_nodes(t, loc)

        # ---------- Conditions ----------
        cond_ids: Set[str] = set()
        for ci, c in enumerate(preset.conditions or []):
            cid = (c.id or "").strip()
            loc = f"conditions[{ci}]"
            if not cid:
                issues.append(ValidationIssue("cond.id.empty", loc, "Condition.id 不能为空"))
                continue
            if cid in cond_ids:
                issues.append(ValidationIssue("cond.id.dup", loc, "Condition.id 重复", detail=cid))
                continue
            cond_ids.add(cid)

            kind = (c.kind or "").strip().lower()
            if kind != "groups":
                issues.append(ValidationIssue("cond.kind.invalid", loc, "Condition.kind 必须是 'groups'", detail=kind))
                continue

            expr = c.expr or {}
            if not isinstance(expr, dict):
                issues.append(ValidationIssue("cond.expr.invalid", loc, "Condition.expr 必须是 dict"))
                continue

            self._check_condition_groups(expr, ctx, loc, issues, skill_ids, point_ids)

        # ---------- 网关 condition_id 引用存在 ----------
        # （_check_gateway_node 已做，但这里对“所有轨道上 gateway”统一兜底也可）
        # 保持简洁：不重复扫描

        return issues

    def _check_gateway_node(
        self,
        n: GatewayNode,
        preset: RotationPreset,
        *,
        loc: str,
        mode_ids: Set[str],
        issues: List[ValidationIssue],
    ) -> None:
        action = (n.action or "").strip().lower() or "switch_mode"
        if action not in self.ALLOWED_ACTIONS:
            issues.append(ValidationIssue("gw.action.invalid", loc, "GatewayNode.action 非法", detail=action))

        # condition_id 若存在必须能找到
        cid = (n.condition_id or "").strip()
        if cid:
            ok = any((c.id or "").strip() == cid for c in (preset.conditions or []))
            if not ok:
                issues.append(ValidationIssue("gw.cond.missing", loc, "GatewayNode.condition_id 指向不存在的 Condition", detail=cid))

        if action == "switch_mode":
            tm = (n.target_mode_id or "").strip()
            if not tm:
                issues.append(ValidationIssue("gw.switch_mode.no_target", loc, "switch_mode 必须设置 target_mode_id"))
            elif tm not in mode_ids:
                issues.append(ValidationIssue("gw.switch_mode.bad_target", loc, "target_mode_id 不存在", detail=tm))

        elif action == "jump_track":
            tt = (n.target_track_id or "").strip()
            if not tt:
                issues.append(ValidationIssue("gw.jump_track.no_track", loc, "jump_track 必须设置 target_track_id"))
            # target_mode_id 允许为空（表示当前作用域）；若非空则必须存在
            tm = (n.target_mode_id or "").strip()
            if tm and tm not in mode_ids:
                issues.append(ValidationIssue("gw.jump_track.bad_mode", loc, "jump_track 的 target_mode_id 不存在", detail=tm))

        elif action == "jump_node":
            # node_index 可为空（默认 0），不做强制；但可提示负数
            if n.target_node_index is not None:
                try:
                    if int(n.target_node_index) < 0:
                        issues.append(ValidationIssue("gw.jump_node.neg", loc, "jump_node 的 target_node_index < 0，将被归零"))
                except Exception:
                    issues.append(ValidationIssue("gw.jump_node.invalid", loc, "jump_node 的 target_node_index 不是整数"))

        elif action == "end":
            pass

    def _check_condition_groups(
        self,
        expr: Dict[str, Any],
        ctx: Optional[ProfileContext],
        loc: str,
        issues: List[ValidationIssue],
        skill_ids: Set[str],
        point_ids: Set[str],
    ) -> None:
        groups = expr.get("groups", [])
        if not isinstance(groups, list):
            issues.append(ValidationIssue("cond.groups.invalid", loc, "expr['groups'] 必须是 list"))
            return

        for gi, g in enumerate(groups):
            gloc = f"{loc}.expr.groups[{gi}]"
            if not isinstance(g, dict):
                issues.append(ValidationIssue("cond.group.invalid", gloc, "group 必须是 dict"))
                continue

            op = (g.get("op") or "and").strip().lower()
            if op not in self.ALLOWED_GROUP_OPS:
                issues.append(ValidationIssue("cond.group.op.invalid", gloc, "group.op 必须是 and/or", detail=op))

            atoms = g.get("atoms", [])
            if not isinstance(atoms, list):
                issues.append(ValidationIssue("cond.group.atoms.invalid", gloc, "group.atoms 必须是 list"))
                continue

            for ai, a in enumerate(atoms):
                aloc = f"{gloc}.atoms[{ai}]"
                if not isinstance(a, dict):
                    issues.append(ValidationIssue("cond.atom.invalid", aloc, "atom 必须是 dict"))
                    continue

                t = (a.get("type") or "").strip().lower()
                if t not in self.ALLOWED_ATOM_TYPES:
                    issues.append(ValidationIssue("cond.atom.type.invalid", aloc, "atom.type 非法", detail=t))
                    continue

                if t == "pixel_point":
                    pid = (a.get("point_id") or "").strip()
                    if not pid:
                        issues.append(ValidationIssue("cond.atom.point.empty", aloc, "pixel_point 必须有 point_id"))
                    elif ctx is not None and pid not in point_ids:
                        issues.append(ValidationIssue("cond.atom.point.missing", aloc, "引用了不存在的 point_id", detail=pid))

                    tol = a.get("tolerance", 0)
                    try:
                        tol_i = int(tol)
                        if tol_i < 0 or tol_i > 255:
                            issues.append(ValidationIssue("cond.atom.tol.range", aloc, "tolerance 应在 0..255", detail=str(tol_i)))
                    except Exception:
                        issues.append(ValidationIssue("cond.atom.tol.invalid", aloc, "tolerance 不是整数", detail=str(tol)))

                if t == "pixel_skill":
                    sid = (a.get("skill_id") or "").strip()
                    if not sid:
                        issues.append(ValidationIssue("cond.atom.skill.empty", aloc, "pixel_skill 必须有 skill_id"))
                    elif ctx is not None and sid not in skill_ids:
                        issues.append(ValidationIssue("cond.atom.skill.missing", aloc, "引用了不存在的 skill_id", detail=sid))

                    tol = a.get("tolerance", 0)
                    try:
                        tol_i = int(tol)
                        if tol_i < 0 or tol_i > 255:
                            issues.append(ValidationIssue("cond.atom.tol.range", aloc, "tolerance 应在 0..255", detail=str(tol_i)))
                    except Exception:
                        issues.append(ValidationIssue("cond.atom.tol.invalid", aloc, "tolerance 不是整数", detail=str(tol)))

                if t == "skill_cast_ge":
                    sid = (a.get("skill_id") or "").strip()
                    if not sid:
                        issues.append(ValidationIssue("cond.atom.skill.empty", aloc, "skill_cast_ge 必须有 skill_id"))
                    elif ctx is not None and sid not in skill_ids:
                        issues.append(ValidationIssue("cond.atom.skill.missing", aloc, "引用了不存在的 skill_id", detail=sid))

                    cnt = a.get("count", 0)
                    try:
                        cnt_i = int(cnt)
                        if cnt_i <= 0:
                            issues.append(ValidationIssue("cond.atom.count.range", aloc, "count 必须 >= 1", detail=str(cnt_i)))
                    except Exception:
                        issues.append(ValidationIssue("cond.atom.count.invalid", aloc, "count 不是整数", detail=str(cnt)))