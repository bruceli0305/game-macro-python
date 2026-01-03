from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

from core.models.common import as_dict, as_str


@dataclass
class Condition:
    """
    条件定义（占位结构）：
    - id: 条件唯一 ID，供节点引用
    - name: 简短名称，UI 展示用
    - kind: 条件类型（例如 "pixel" / "buff_remain_lt" / "hp_lt" / "expr"...）
    - expr: 具体参数（结构后续可扩展）

    当前实现：
    - expr 是任意 dict，通常由 UI 的 ConditionEditorDialog 维护。
    """

    id: str = ""
    name: str = ""
    kind: str = ""
    expr: Dict[str, Any] = field(default_factory=dict)

    # ---------- 序列化 ----------

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Condition":
        d = as_dict(d)
        return Condition(
            id=as_str(d.get("id", "")),
            name=as_str(d.get("name", "")),
            kind=as_str(d.get("kind", "")),
            expr=as_dict(d.get("expr", {})),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "expr": dict(self.expr or {}),
        }