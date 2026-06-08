from __future__ import annotations

from typing import Any, Dict, List, Tuple, Optional

from core.models.common import as_dict, as_list, as_str, as_int

from .diagnostics import Diagnostic, err, pjoin
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


_ALLOWED_ATOM_TYPES = {
    "pixel_point",
    "pixel_skill",
    "cast_bar_changed",
    "skill_metric_ge",
}

_ALLOWED_BOOL_TYPES = {"and", "or", "not", "const"}


def decode_expr(obj: Any, *, path: str = "$") -> Tuple[Optional[Expr], List[Diagnostic]]:
    diags: List[Diagnostic] = []
    expr = _decode_expr_inner(obj, diags=diags, path=path or "$")
    return expr, diags


def _decode_expr_inner(obj: Any, *, diags: List[Diagnostic], path: str) -> Optional[Expr]:
    if not isinstance(obj, dict):
        diags.append(err("expr.not_object", path, "表达式必须是对象(dict)"))
        return None

    d = as_dict(obj)
    t = as_str(d.get("type", "")).strip().lower()
    if not t:
        diags.append(err("expr.type.missing", path, "表达式缺少 type 字段"))
        return None

    # ---- bool nodes ----
    if t in ("and", "or"):
        children_raw = d.get("children", None)
        if not isinstance(children_raw, list):
            diags.append(err("expr.children.invalid", pjoin(path, ".children"), "children 必须是 list"))
            return None

        children: List[Expr] = []
        for i, item in enumerate(children_raw):
            child = _decode_expr_inner(item, diags=diags, path=pjoin(path, f".children[{i}]"))
            if child is not None:
                children.append(child)

        if t == "and":
            return And(children=tuple(children))
        return Or(children=tuple(children))

    if t == "not":
        child_raw = d.get("child", None)
        child = _decode_expr_inner(child_raw, diags=diags, path=pjoin(path, ".child"))
        if child is None:
            return None
        return Not(child=child)

    if t == "const":
        v = d.get("value", None)
        if isinstance(v, bool):
            return Const(value=v)
        # 允许 "true"/"false"
        sv = as_str(v, "").strip().lower()
        if sv in ("true", "1", "yes", "y"):
            return Const(value=True)
        if sv in ("false", "0", "no", "n"):
            return Const(value=False)
        diags.append(err("expr.const.invalid", pjoin(path, ".value"), "const.value 必须是 bool"))
        return None

    # ---- atoms ----
    if t not in _ALLOWED_ATOM_TYPES:
        diags.append(err("expr.type.invalid", path, "未知表达式类型", detail=t))
        return None

    if t == "pixel_point":
        pid = as_str(d.get("point_id", "")).strip()
        tol = as_int(d.get("tolerance", 0), 0)
        return PixelMatchPoint(point_id=pid, tolerance=int(tol))

    if t == "pixel_skill":
        sid = as_str(d.get("skill_id", "")).strip()
        tol = as_int(d.get("tolerance", 0), 0)
        return PixelMatchSkill(skill_id=sid, tolerance=int(tol))

    if t == "cast_bar_changed":
        pid = as_str(d.get("point_id", "")).strip()
        tol = as_int(d.get("tolerance", 0), 0)
        return CastBarChanged(point_id=pid, tolerance=int(tol))

    if t == "skill_metric_ge":
        sid = as_str(d.get("skill_id", "")).strip()
        metric = as_str(d.get("metric", "success"), "success").strip().lower()
        cnt = as_int(d.get("count", 1), 1)
        # metric 的合法性留给 compiler 做（这里先容忍）
        return SkillMetricGE(skill_id=sid, metric=metric, count=int(cnt))  # type: ignore[arg-type]

    diags.append(err("expr.type.unhandled", path, "表达式类型未实现", detail=t))
    return None


def encode_expr(expr: Expr) -> Dict[str, Any]:
    """
    把节点对象编码回 JSON dict（用于存盘）。
    """
    from .nodes import And, Or, Not, Const, PixelMatchPoint, PixelMatchSkill, CastBarChanged, SkillMetricGE

    if isinstance(expr, And):
        return {"type": "and", "children": [encode_expr(c) for c in expr.children]}
    if isinstance(expr, Or):
        return {"type": "or", "children": [encode_expr(c) for c in expr.children]}
    if isinstance(expr, Not):
        return {"type": "not", "child": encode_expr(expr.child)}
    if isinstance(expr, Const):
        return {"type": "const", "value": bool(expr.value)}

    if isinstance(expr, PixelMatchPoint):
        return {"type": "pixel_point", "point_id": expr.point_id, "tolerance": int(expr.tolerance)}
    if isinstance(expr, PixelMatchSkill):
        return {"type": "pixel_skill", "skill_id": expr.skill_id, "tolerance": int(expr.tolerance)}
    if isinstance(expr, CastBarChanged):
        return {"type": "cast_bar_changed", "point_id": expr.point_id, "tolerance": int(expr.tolerance)}
    if isinstance(expr, SkillMetricGE):
        return {"type": "skill_metric_ge", "skill_id": expr.skill_id, "metric": expr.metric, "count": int(expr.count)}

    # 理论上不会到这里
    return {"type": "const", "value": False}