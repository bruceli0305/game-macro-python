from __future__ import annotations

from typing import Protocol


class SkillState(Protocol):
    """
    技能状态机接口（占位）：

    - 未来由执行引擎实现，用于在条件判断时查询技能相关的运行时信息。
    - 当前阶段你可以先不实现具体类，RuntimeContext.skill_state 也可以留空。
    """

    def get_cast_count(self, skill_id: str) -> int:
        """
        返回指定技能从某个参考点（例如本轮战斗开始、本轮循环开始等）
        以来累计施放次数。

        后续如果需要，可以在这里扩展更多方法，比如：
        - get_last_cast_ms_ago(skill_id): 上次施放距今多少毫秒
        - is_on_cooldown(skill_id): 是否冷却中
        """
        ...