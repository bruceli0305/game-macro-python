from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from core.models.common import as_dict, as_str, as_int


@dataclass
class Node:
    """
    轨道节点基类：

    - kind: "skill" | "gateway" | ...
    - id: 节点 ID（字符串）
    - label: UI 上展示用的短标签（例如 "2" / "A→B" 等）

    实际使用时一般是 SkillNode 或 GatewayNode 子类。
    """

    id: str = ""
    kind: str = "skill"
    label: str = ""

    # ---------- 工厂方法 ----------

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Node":
        """
        工厂方法：根据 kind 字段分发到具体子类。
        """

        d = as_dict(d)
        kind = as_str(d.get("kind", "skill"), "skill").strip().lower()
        if kind == "gateway":
            return GatewayNode.from_dict(d)
        # 默认当作 skill 节点处理
        return SkillNode.from_dict(d)

    # ---------- 序列化（基类兜底） ----------

    def to_dict(self) -> Dict[str, Any]:
        """
        子类应覆写本方法；这里只做兜底。
        """
        return {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
        }


# ---------- SkillNode ----------

@dataclass
class SkillNode(Node):
    """
    技能节点：
    - skill_id: 引用 skills.json 中的 Skill.id
    - override_cast_ms: 可选，覆盖 Skill.cast.readbar_ms
    - comment: 备注（UI 展示用）
    """

    skill_id: str = ""
    override_cast_ms: Optional[int] = None
    comment: str = ""

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "SkillNode":
        d = as_dict(d)
        node_id = as_str(d.get("id", ""))
        label = as_str(d.get("label", ""))

        skill_id = as_str(d.get("skill_id", ""))
        oc_raw = d.get("override_cast_ms", None)
        if oc_raw is None:
            override_cast_ms: Optional[int] = None
        else:
            v = as_int(oc_raw, 0)
            override_cast_ms = v if v >= 0 else None

        comment = as_str(d.get("comment", ""))

        return SkillNode(
            id=node_id,
            kind="skill",
            label=label,
            skill_id=skill_id,
            override_cast_ms=override_cast_ms,
            comment=comment,
        )

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "id": self.id,
            "kind": "skill",
            "label": self.label,
            "skill_id": self.skill_id,
            "comment": self.comment,
        }
        if self.override_cast_ms is not None:
            out["override_cast_ms"] = int(self.override_cast_ms)
        return out


# ---------- GatewayNode ----------

@dataclass
class GatewayNode(Node):
    """
    网关节点（控制流节点，不直接放技能）：

    - condition_id: 条件 ID（可选），为空则无条件，执行到此节点即触发动作
    - action: 动作类型，MVP 先支持：
        - "switch_mode": 切换到另一个模式
      预留:
        - "jump_track": 跳转到当前/其他轨道
        - "jump_node": 跳转到当前轨道某个节点索引
        - "end": 结束当前模式/轨道
    - target_mode_id / target_track_id / target_node_index:
        动作需要的目标参数（视 action 而定）
    """

    condition_id: Optional[str] = None
    action: str = "switch_mode"
    target_mode_id: Optional[str] = None
    target_track_id: Optional[str] = None
    target_node_index: Optional[int] = None

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "GatewayNode":
        d = as_dict(d)
        node_id = as_str(d.get("id", ""))
        label = as_str(d.get("label", ""))

        cond_id = d.get("condition_id", None)
        if cond_id is not None:
            cond_id = as_str(cond_id, "")

        action = as_str(d.get("action", "switch_mode"), "switch_mode").strip() or "switch_mode"

        t_mode = d.get("target_mode_id", None)
        if t_mode is not None:
            t_mode = as_str(t_mode, "")

        t_track = d.get("target_track_id", None)
        if t_track is not None:
            t_track = as_str(t_track, "")

        idx_raw = d.get("target_node_index", None)
        if idx_raw is None:
            t_index: Optional[int] = None
        else:
            v = as_int(idx_raw, -1)
            t_index = v if v >= 0 else None

        return GatewayNode(
            id=node_id,
            kind="gateway",
            label=label,
            condition_id=cond_id or None,
            action=action,
            target_mode_id=t_mode or None,
            target_track_id=t_track or None,
            target_node_index=t_index,
        )

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "id": self.id,
            "kind": "gateway",
            "label": self.label,
            "action": self.action,
        }
        if self.condition_id:
            out["condition_id"] = self.condition_id
        if self.target_mode_id:
            out["target_mode_id"] = self.target_mode_id
        if self.target_track_id:
            out["target_track_id"] = self.target_track_id
        if self.target_node_index is not None:
            out["target_node_index"] = int(self.target_node_index)
        return out