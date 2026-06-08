from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


Outcome = Literal[
    "SUCCESS",
    "FAILED",
    "STOPPED",
    "SKIPPED_DISABLED",
    "SKIPPED_LOCK_BUSY",
    "SKIPPED_NOT_READY",
    "ERROR",
]

Advance = Literal[
    "ADVANCE",   # 推进 cursor 到下一个节点
    "HOLD",      # 不推进（下一轮继续尝试同一节点）
    "JUMP",      # 控制流跳转（给 gateway 用；本执行器暂不用）
]


@dataclass(frozen=True)
class ExecutionResult:
    outcome: Outcome
    advance: Advance
    next_delay_ms: int
    reason: str = ""