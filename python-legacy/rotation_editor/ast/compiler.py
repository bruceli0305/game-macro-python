from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

from core.profiles import ProfileContext

from .diagnostics import Diagnostic, err, warn, pjoin
from .codec import decode_expr
from .nodes import (
    Expr,
    And,
    Or,
    Not,
    Const,
    PixelMatchPoint,
    PixelMatchSkill,
    CastBarChanged,
    SkillMetricGE,
)
from .probes import ProbeRequirements


_ALLOWED_METRICS = {"success", "attempt_started", "key_sent_ok", "cast_started", "fail"}


@dataclass(frozen=True)
class CompileResult:
    expr: Optional[Expr]
    diagnostics: List[Diagnostic]
    probes: ProbeRequirements

    def ok(self) -> bool:
        return self.expr is not None and not any(d.is_error() for d in (self.diagnostics or []))


def compile_expr_json(
    expr_json: Any,
    *,
    ctx: Optional[ProfileContext] = None,
    path: str = "$",
) -> CompileResult:
    """
    编译入口：
    - 先 decode（语法检查）
    - 再 semantic validate（引用/范围/约束）
    - 最后提取 probes
    """
    expr, diags = decode_expr(expr_json, path=path or "$")
    probes = ProbeRequirements()

    if expr is None:
        return CompileResult(expr=None, diagnostics=diags, probes=probes)

    _semantic_validate(expr, ctx=ctx, diags=diags, path=path or "$")
    _collect_probes(expr, probes=probes)
    return CompileResult(expr=expr, diagnostics=diags, probes=probes)


def _semantic_validate(expr: Expr, *, ctx: Optional[ProfileContext], diags: List[Diagnostic], path: str) -> None:
    # 预构建引用集合
    skill_ids = set()
    point_ids = set()
    skills_by_id = {}
    points_by_id = {}

    if ctx is not None:
        try:
            skills = getattr(ctx.skills, "skills", []) or []
            for s in skills:
                sid = getattr(s, "id", "") or ""
                if sid:
                    skill_ids.add(sid)
                    skills_by_id[sid] = s
        except Exception:
            pass

        try:
            points = getattr(ctx.points, "points", []) or []
            for p in points:
                pid = getattr(p, "id", "") or ""
                if pid:
                    point_ids.add(pid)
                    points_by_id[pid] = p
        except Exception:
            pass

    def walk(e: Expr, p: str) -> None:
        if isinstance(e, And) or isinstance(e, Or):
            if not e.children:
                diags.append(err("expr.children.empty", p, "children 不能为空"))
            for i, c in enumerate(e.children):
                walk(c, pjoin(p, f".children[{i}]"))
            return

        if isinstance(e, Not):
            walk(e.child, pjoin(p, ".child"))
            return

        if isinstance(e, Const):
            return

        # ---- atoms ----
        if isinstance(e, PixelMatchPoint) or isinstance(e, CastBarChanged):
            pid = (e.point_id or "").strip()
            if not pid:
                diags.append(err("expr.point_id.empty", p, "point_id 不能为空"))
            elif ctx is not None and pid not in point_ids:
                diags.append(err("expr.point_id.missing", p, "引用了不存在的点位", detail=pid))

            tol = int(e.tolerance)
            if tol < 0 or tol > 255:
                diags.append(err("expr.tolerance.range", p, "tolerance 应在 0..255", detail=str(tol)))
            return

        if isinstance(e, PixelMatchSkill):
            sid = (e.skill_id or "").strip()
            if not sid:
                diags.append(err("expr.skill_id.empty", p, "skill_id 不能为空"))
            elif ctx is not None and sid not in skill_ids:
                diags.append(err("expr.skill_id.missing", p, "引用了不存在的技能", detail=sid))
            else:
                # 可选：如果 skill 没有 pixel，给 warning（否则 ready/像素条件一定不可判）
                if ctx is not None:
                    s = skills_by_id.get(sid)
                    pix = getattr(s, "pixel", None) if s is not None else None
                    if pix is None:
                        diags.append(warn("expr.skill_pixel.missing", p, "技能未配置 pixel，像素条件可能永远失败", detail=sid))

            tol = int(e.tolerance)
            if tol < 0 or tol > 255:
                diags.append(err("expr.tolerance.range", p, "tolerance 应在 0..255", detail=str(tol)))
            return

        if isinstance(e, SkillMetricGE):
            sid = (e.skill_id or "").strip()
            if not sid:
                diags.append(err("expr.skill_id.empty", p, "skill_id 不能为空"))
            elif ctx is not None and sid not in skill_ids:
                diags.append(err("expr.skill_id.missing", p, "引用了不存在的技能", detail=sid))

            metric = (str(e.metric or "")).strip().lower()
            if metric not in _ALLOWED_METRICS:
                diags.append(err("expr.metric.invalid", p, "metric 非法", detail=metric))

            cnt = int(e.count)
            if cnt <= 0:
                diags.append(err("expr.count.range", p, "count 必须 >= 1", detail=str(cnt)))
            return

        # 未知节点（理论上不会出现）
        diags.append(err("expr.node.unhandled", p, "表达式节点未处理", detail=type(e).__name__))

    walk(expr, path)


def _collect_probes(expr: Expr, *, probes: ProbeRequirements) -> None:
    def walk(e: Expr) -> None:
        if isinstance(e, And) or isinstance(e, Or):
            for c in e.children:
                walk(c)
            return
        if isinstance(e, Not):
            walk(e.child)
            return
        if isinstance(e, Const):
            return

        if isinstance(e, PixelMatchPoint):
            pid = (e.point_id or "").strip()
            if pid:
                probes.point_ids.add(pid)
            return

        if isinstance(e, CastBarChanged):
            pid = (e.point_id or "").strip()
            if pid:
                probes.point_ids.add(pid)
            return

        if isinstance(e, PixelMatchSkill):
            sid = (e.skill_id or "").strip()
            if sid:
                probes.skill_pixel_ids.add(sid)
            return

        if isinstance(e, SkillMetricGE):
            sid = (e.skill_id or "").strip()
            if sid:
                probes.skill_metric_ids.add(sid)
            return

    walk(expr)