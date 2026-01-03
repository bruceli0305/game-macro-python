from __future__ import annotations

"""
rotation_editor.core.runtime

运行时相关的基础设施：
- RuntimeContext: 条件评估/执行引擎运行时上下文
- SkillState: 技能状态机接口（Protocol，占位）
- eval_condition: 条件评估入口（基于 Condition.expr 的 AST）
"""

from .context import RuntimeContext
from .skill_state import SkillState
from .condition_eval import eval_condition

__all__ = [
    "RuntimeContext",
    "SkillState",
    "eval_condition",
]