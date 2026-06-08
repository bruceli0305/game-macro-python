from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Tuple

from .types import Advance, ExecutionResult


LockPolicy = Literal[
    "SKIP_AND_ADVANCE",  # 锁忙 -> 直接跳过并推进（你旧引擎行为）
    "WAIT_LOCK",         # 锁忙 -> 等锁（不推进）
    "SKIP_BUT_HOLD",     # 锁忙 -> 跳过但不推进（下轮继续尝试同一节点）
]


@dataclass(frozen=True)
class LockPolicyConfig:
    policy: LockPolicy = "SKIP_AND_ADVANCE"

    # WAIT_LOCK 用：
    wait_timeout_ms: int = 300      # 等锁最多多久
    wait_poll_ms: int = 15          # 等锁期间轮询间隔

    # skip 类策略用：
    skip_delay_ms: int = 50         # 锁忙跳过后下一次调度延迟


def decide_on_lock_busy(cfg: LockPolicyConfig) -> ExecutionResult:
    """
    当全局施法锁被占用时，按策略返回“应该如何处理”的 ExecutionResult。
    """
    pol = (cfg.policy or "SKIP_AND_ADVANCE").strip().upper()  # type: ignore[assignment]
    if pol == "WAIT_LOCK":
        # WAIT_LOCK 的结果不在这里直接返回；由 executor 做实际 wait/acquire。
        return ExecutionResult(outcome="SKIPPED_LOCK_BUSY", advance="HOLD", next_delay_ms=max(1, int(cfg.wait_poll_ms)), reason="wait_lock")
    if pol == "SKIP_BUT_HOLD":
        return ExecutionResult(outcome="SKIPPED_LOCK_BUSY", advance="HOLD", next_delay_ms=max(10, int(cfg.skip_delay_ms)), reason="lock_busy_hold")
    # default: SKIP_AND_ADVANCE
    return ExecutionResult(outcome="SKIPPED_LOCK_BUSY", advance="ADVANCE", next_delay_ms=max(10, int(cfg.skip_delay_ms)), reason="lock_busy_advance")