from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from core.models.common import as_dict, as_list, as_str
from .node import Node


@dataclass
class Track:
    """
    一条轨道：
    - id: 轨道 ID
    - name: 轨道名称（例如 "主循环"、"爆发维护" 等）
    - nodes: 有序节点列表（技能节点 / 网关节点等 Node 子类）
    """
    id: str = ""
    name: str = ""
    nodes: List[Node] = field(default_factory=list)

    # ---------- 反序列化 ----------

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Track":
        d = as_dict(d)
        tid = as_str(d.get("id", ""))
        name = as_str(d.get("name", ""))

        nodes_raw = as_list(d.get("nodes", []))
        nodes: List[Node] = []
        for item in nodes_raw:
            if isinstance(item, dict):
                try:
                    node = Node.from_dict(item)
                    nodes.append(node)
                except Exception:
                    # 忽略无法解析的节点
                    pass

        return Track(
            id=tid,
            name=name,
            nodes=nodes,
        )

    # ---------- 序列化 ----------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "nodes": [n.to_dict() for n in self.nodes],
        }