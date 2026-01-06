from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

from core.models.common import as_dict, as_str


@dataclass
class Condition:
    """
    条件定义（AST 版）：

    - id: 条件唯一 ID，供节点引用
    - name: 简短名称，UI 展示用
    - kind: 条件类型，目前固定为 "ast"
    - expr: AST JSON dict（由 ConditionEditorDialog 维护）

    说明：
    - 旧版曾使用 kind="expr_tree_v1" + 非 AST 结构；本轮重构后不再支持：
      * from_dict 时会忽略旧 kind 值，一律视为 "ast"
      * expr 不是 dict 或缺少 "type" 时，UI 会提示并重置为一个空的 AST 结构
    """

    id: str = ""
    name: str = ""
    kind: str = "ast"
    expr: Dict[str, Any] = field(default_factory=dict)

    # ---------- 序列化 ----------

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Condition":
        d = as_dict(d)

        # 旧数据里可能有 kind="expr_tree_v1" 等，这里一律收敛为 "ast"
        kind_raw = as_str(d.get("kind", "ast"), "ast").strip().lower()
        kind = "ast"  # 统一成 ast

        expr_raw = d.get("expr", {})
        expr = as_dict(expr_raw) if isinstance(expr_raw, dict) else {}

        return Condition(
            id=as_str(d.get("id", "")),
            name=as_str(d.get("name", "")),
            kind=kind,
            expr=expr,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            # 永远写出 "ast"，避免再产生新的旧格式
            "kind": "ast",
            "expr": dict(self.expr or {}),
        }