from __future__ import annotations

import logging
from typing import Any, Dict, List

from core.pick.capture import SampleSpec
from core.models.point import Point
from core.models.skill import Skill
from rotation_editor.core.models import Condition

from .context import RuntimeContext

log = logging.getLogger(__name__)


def eval_condition(cond: Condition, ctx: RuntimeContext) -> bool:
    """
    评估单个 Condition 是否满足。

    仅支持：
    - kind == "groups"
      expr 结构：
        {"groups":[{"op":"and|or","atoms":[...]}]}

    语义：
    - 组与组之间固定 OR
    - 组内按 op 组合
    - atom 支持 neg（取反）
    """
    kind = (cond.kind or "").strip().lower()
    if kind != "groups":
        return False

    expr = cond.expr or {}
    if not isinstance(expr, dict):
        return False

    try:
        return _eval_groups_expr(expr, ctx)
    except Exception:
        log.exception("eval_condition(groups) failed (id=%s, name=%s)", cond.id, cond.name)
        return False


def _eval_groups_expr(expr: Dict[str, Any], ctx: RuntimeContext) -> bool:
    groups = expr.get("groups", [])
    if not isinstance(groups, list) or not groups:
        return False

    # groups 之间固定 OR
    for g in groups:
        if not isinstance(g, dict):
            continue
        if _eval_one_group(g, ctx):
            return True
    return False


def _eval_one_group(g: Dict[str, Any], ctx: RuntimeContext) -> bool:
    op = (g.get("op") or "and").strip().lower()
    if op not in ("and", "or"):
        op = "and"

    atoms = g.get("atoms", [])
    if not isinstance(atoms, list) or not atoms:
        return False

    results: List[bool] = []
    for a in atoms:
        if not isinstance(a, dict):
            continue
        results.append(_eval_atom(a, ctx))

    if not results:
        return False

    return any(results) if op == "or" else all(results)


def _eval_atom(a: Dict[str, Any], ctx: RuntimeContext) -> bool:
    t = (a.get("type") or "").strip().lower()
    neg = bool(a.get("neg", False))

    ok = False

    if t == "pixel_point":
        pid = (a.get("point_id") or "").strip()
        tol = int(a.get("tolerance", 0) or 0)
        tol = max(0, min(255, tol))
        ok = _eval_pixel_point(pid, tol, ctx)

    elif t == "pixel_skill":
        sid = (a.get("skill_id") or "").strip()
        tol = int(a.get("tolerance", 0) or 0)
        tol = max(0, min(255, tol))
        ok = _eval_pixel_skill(sid, tol, ctx)

    elif t == "skill_cast_ge":
        sid = (a.get("skill_id") or "").strip()
        cnt = int(a.get("count", 0) or 0)
        if cnt <= 0:
            cnt = 1
        ok = _eval_skill_cast_ge(sid, cnt, ctx)

    else:
        ok = False

    return (not ok) if neg else ok


# ---------- 像素：点位 ----------

def _eval_pixel_point(point_id: str, tolerance: int, ctx: RuntimeContext) -> bool:
    pid = (point_id or "").strip()
    tol = max(0, min(255, int(tolerance)))
    if not pid:
        return False

    pts = getattr(ctx.profile.points, "points", []) or []
    p: Point | None = next((x for x in pts if x.id == pid), None)
    if p is None:
        return False

    try:
        sample = SampleSpec(mode=p.sample.mode, radius=int(p.sample.radius))
    except Exception:
        sample = SampleSpec(mode="single", radius=0)

    try:
        r, g, b = ctx.capture.get_rgb_scoped_abs(
            x_abs=int(p.vx),
            y_abs=int(p.vy),
            sample=sample,
            monitor_key=p.monitor or "primary",
            require_inside=False,
        )
    except Exception:
        return False

    dr = abs(int(r) - int(p.color.r))
    dg = abs(int(g) - int(p.color.g))
    db = abs(int(b) - int(p.color.b))
    return max(dr, dg, db) <= tol


# ---------- 像素：技能 pixel ----------

def _eval_pixel_skill(skill_id: str, tolerance: int, ctx: RuntimeContext) -> bool:
    sid = (skill_id or "").strip()
    tol = max(0, min(255, int(tolerance)))
    if not sid:
        return False

    skills = getattr(ctx.profile.skills, "skills", []) or []
    s: Skill | None = next((x for x in skills if x.id == sid), None)
    if s is None:
        return False

    pix = s.pixel
    try:
        sample = SampleSpec(mode=pix.sample.mode, radius=int(pix.sample.radius))
    except Exception:
        sample = SampleSpec(mode="single", radius=0)

    try:
        r, g, b = ctx.capture.get_rgb_scoped_abs(
            x_abs=int(pix.vx),
            y_abs=int(pix.vy),
            sample=sample,
            monitor_key=pix.monitor or "primary",
            require_inside=False,
        )
    except Exception:
        return False

    dr = abs(int(r) - int(pix.color.r))
    dg = abs(int(g) - int(pix.color.g))
    db = abs(int(b) - int(pix.color.b))
    return max(dr, dg, db) <= tol


# ---------- 技能施放次数 ----------

def _eval_skill_cast_ge(skill_id: str, count: int, ctx: RuntimeContext) -> bool:
    if ctx.skill_state is None:
        return False

    sid = (skill_id or "").strip()
    need = int(count or 0)
    if not sid or need <= 0:
        return False

    try:
        cur = int(ctx.skill_state.get_cast_count(sid))
    except Exception:
        return False

    return cur >= need