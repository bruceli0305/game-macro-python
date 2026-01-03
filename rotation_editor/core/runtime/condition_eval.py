from __future__ import annotations

import logging
from typing import Any, Dict, Iterable

from core.pick.capture import SampleSpec
from core.models.point import Point
from core.models.skill import Skill
from rotation_editor.core.models import Condition

from .context import RuntimeContext

log = logging.getLogger(__name__)


def eval_condition(cond: Condition, ctx: RuntimeContext) -> bool:
    """
    评估单个 Condition 是否满足。

    约定：
    - kind == "expr_tree_v1" 时，expr 使用 AST 结构（见 eval_expr_node）。
    - 其他 kind 暂时统一返回 False（未来可在此兼容旧格式/simple 条件）。
    """
    kind = (cond.kind or "").strip().lower()
    expr = cond.expr or {}

    if kind == "expr_tree_v1":
        if not isinstance(expr, dict):
            log.warning("Condition.expr_tree_v1 expects dict expr, got %r", type(expr))
            return False
        try:
            return eval_expr_node(expr, ctx)
        except Exception:
            log.exception("eval_condition failed (id=%s, name=%s)", cond.id, cond.name)
            return False

    # TODO: 这里可以按需兼容旧格式的 pixel_point/pixel_skill/simple expr
    log.debug("Unsupported condition kind: %s (id=%s, name=%s)", kind, cond.id, cond.name)
    return False


def eval_expr_node(node: Dict[str, Any], ctx: RuntimeContext) -> bool:
    """
    递归评估 AST 节点。

    约定的 node["type"]：
    - "logic_and"  : children: [subnodes...]
    - "logic_or"   : children: [subnodes...]
    - "logic_not"  : child: {...}
    - "pixel_point": point_id, tolerance
    - "pixel_skill": skill_id, tolerance
    - "skill_cast_ge": skill_id, count           （占位，实现依赖 skill_state）
    """
    t = (node.get("type") or "").strip().lower()

    if t == "logic_and":
        children = _as_list(node.get("children"))
        return all(eval_expr_node(ch, ctx) for ch in children)

    if t == "logic_or":
        children = _as_list(node.get("children"))
        return any(eval_expr_node(ch, ctx) for ch in children)

    if t == "logic_not":
        child = node.get("child")
        if isinstance(child, dict):
            return not eval_expr_node(child, ctx)
        return True  # child 无效时，视为 not False => True

    if t == "pixel_point":
        return _eval_pixel_point(node, ctx)

    if t == "pixel_skill":
        return _eval_pixel_skill(node, ctx)

    if t == "skill_cast_ge":
        return _eval_skill_cast_ge(node, ctx)  # 占位实现

    log.warning("Unknown expr node type: %r", t)
    return False


def _as_list(v: Any) -> list:
    if isinstance(v, list):
        return v
    if v is None:
        return []
    return [v]


# ---------- 像素：点位 ----------

def _eval_pixel_point(node: Dict[str, Any], ctx: RuntimeContext) -> bool:
    pid = (node.get("point_id") or "").strip()
    tol = int(node.get("tolerance", 0) or 0)
    tol = max(0, min(255, tol))

    if not pid:
        return False

    pts = getattr(ctx.profile.points, "points", []) or []
    p: Point | None = next((x for x in pts if x.id == pid), None)
    if p is None:
        log.debug("pixel_point: point not found (id=%s)", pid)
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
        log.exception("pixel_point sampling failed (point_id=%s)", pid)
        return False

    dr = abs(int(r) - int(p.color.r))
    dg = abs(int(g) - int(p.color.g))
    db = abs(int(b) - int(p.color.b))
    diff = max(dr, dg, db)

    return diff <= tol


# ---------- 像素：技能 pixel ----------

def _eval_pixel_skill(node: Dict[str, Any], ctx: RuntimeContext) -> bool:
    sid = (node.get("skill_id") or "").strip()
    tol = int(node.get("tolerance", 0) or 0)
    tol = max(0, min(255, tol))

    if not sid:
        return False

    skills = getattr(ctx.profile.skills, "skills", []) or []
    s: Skill | None = next((x for x in skills if x.id == sid), None)
    if s is None:
        log.debug("pixel_skill: skill not found (id=%s)", sid)
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
        log.exception("pixel_skill sampling failed (skill_id=%s)", sid)
        return False

    dr = abs(int(r) - int(pix.color.r))
    dg = abs(int(g) - int(pix.color.g))
    db = abs(int(b) - int(pix.color.b))
    diff = max(dr, dg, db)

    return diff <= tol


# ---------- 技能施放次数（占位实现） ----------

def _eval_skill_cast_ge(node: Dict[str, Any], ctx: RuntimeContext) -> bool:
    """
    未来扩展口：技能施放次数 >= N。

    目前策略：
    - 如果 RuntimeContext.skill_state 未提供，统一返回 False。
    - 等你写好技能状态机，并在 RuntimeContext 里挂上实现后，
      只需要在这里接 skill_state.get_cast_count 即可。
    """
    if ctx.skill_state is None:
        # 现在还没有状态机实现，一律视为条件不满足
        return False

    sid = (node.get("skill_id") or "").strip()
    need = int(node.get("count", 0) or 0)
    if not sid or need <= 0:
        return False

    try:
        cur = int(ctx.skill_state.get_cast_count(sid))
    except Exception:
        log.exception("skill_state.get_cast_count failed (skill_id=%s)", sid)
        return False

    return cur >= need