from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from core.models.common import as_dict, as_str, as_int


@dataclass
class Node:
    id: str = ""
    kind: str = "skill"
    label: str = ""

    step_index: int = 0
    order_in_step: int = 0

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Node":
        d = as_dict(d)
        kind = as_str(d.get("kind", "skill"), "skill").strip().lower()
        if kind == "gateway":
            return GatewayNode.from_dict(d)
        return SkillNode.from_dict(d)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "step_index": int(self.step_index),
            "order_in_step": int(self.order_in_step),
        }


@dataclass
class SkillNode(Node):
    skill_id: str = ""
    override_cast_ms: Optional[int] = None
    comment: str = ""

    # 节点级 AST JSON（可选）
    start_expr: Optional[Dict[str, Any]] = None
    complete_expr: Optional[Dict[str, Any]] = None

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "SkillNode":
        d = as_dict(d)
        node_id = as_str(d.get("id", ""))
        label = as_str(d.get("label", ""))

        step_index = as_int(d.get("step_index", 0), 0)
        order_in_step = as_int(d.get("order_in_step", 0), 0)

        skill_id = as_str(d.get("skill_id", ""))
        oc_raw = d.get("override_cast_ms", None)
        if oc_raw is None:
            override_cast_ms: Optional[int] = None
        else:
            v = as_int(oc_raw, 0)
            override_cast_ms = v if v >= 0 else None

        comment = as_str(d.get("comment", ""))

        se = d.get("start_expr", None)
        start_expr = dict(se) if isinstance(se, dict) and se else None

        ce = d.get("complete_expr", None)
        complete_expr = dict(ce) if isinstance(ce, dict) and ce else None

        return SkillNode(
            id=node_id,
            kind="skill",
            label=label,
            step_index=step_index,
            order_in_step=order_in_step,
            skill_id=skill_id,
            override_cast_ms=override_cast_ms,
            comment=comment,
            start_expr=start_expr,
            complete_expr=complete_expr,
        )

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "id": self.id,
            "kind": "skill",
            "label": self.label,
            "step_index": int(self.step_index),
            "order_in_step": int(self.order_in_step),
            "skill_id": self.skill_id,
            "comment": self.comment,
        }
        if self.override_cast_ms is not None:
            out["override_cast_ms"] = int(self.override_cast_ms)

        if isinstance(self.start_expr, dict) and self.start_expr:
            out["start_expr"] = dict(self.start_expr)
        if isinstance(self.complete_expr, dict) and self.complete_expr:
            out["complete_expr"] = dict(self.complete_expr)

        return out


@dataclass
class GatewayNode(Node):
    """
    网关节点（控制流节点）：

    - condition_id: 引用 Condition.id（可选）
    - condition_expr: 内联 AST JSON（可选，优先于 condition_id）
    - action: switch_mode / jump_track / jump_node / end
    - target_*：跳转目标（稳定使用 node_id，不再支持 index）
    """
    condition_id: Optional[str] = None
    condition_expr: Optional[Dict[str, Any]] = None

    action: str = "switch_mode"
    target_mode_id: Optional[str] = None
    target_track_id: Optional[str] = None
    target_node_id: Optional[str] = None

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "GatewayNode":
        d = as_dict(d)
        node_id = as_str(d.get("id", ""))
        label = as_str(d.get("label", ""))

        step_index = as_int(d.get("step_index", 0), 0)
        order_in_step = as_int(d.get("order_in_step", 0), 0)

        cond_id = d.get("condition_id", None)
        if cond_id is not None:
            cond_id = as_str(cond_id, "")

        cond_expr_raw = d.get("condition_expr", None)
        condition_expr = dict(cond_expr_raw) if isinstance(cond_expr_raw, dict) and cond_expr_raw else None

        action = as_str(d.get("action", "switch_mode"), "switch_mode").strip() or "switch_mode"

        t_mode = d.get("target_mode_id", None)
        if t_mode is not None:
            t_mode = as_str(t_mode, "")

        t_track = d.get("target_track_id", None)
        if t_track is not None:
            t_track = as_str(t_track, "")

        t_node_id = d.get("target_node_id", None)
        if t_node_id is not None:
            t_node_id = as_str(t_node_id, "")

        # 旧字段 target_node_index：彻底忽略（不兼容，不再使用）
        # d.get("target_node_index", None)

        return GatewayNode(
            id=node_id,
            kind="gateway",
            label=label,
            step_index=step_index,
            order_in_step=order_in_step,
            condition_id=cond_id or None,
            condition_expr=condition_expr,
            action=action,
            target_mode_id=t_mode or None,
            target_track_id=t_track or None,
            target_node_id=(t_node_id or None),
        )

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "id": self.id,
            "kind": "gateway",
            "label": self.label,
            "step_index": int(self.step_index),
            "order_in_step": int(self.order_in_step),
            "action": self.action,
        }
        if self.condition_id:
            out["condition_id"] = self.condition_id
        if isinstance(self.condition_expr, dict) and self.condition_expr:
            out["condition_expr"] = dict(self.condition_expr)

        if self.target_mode_id:
            out["target_mode_id"] = self.target_mode_id
        if self.target_track_id:
            out["target_track_id"] = self.target_track_id
        if self.target_node_id:
            out["target_node_id"] = self.target_node_id

        return out