from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Literal

log = logging.getLogger(__name__)

EngineEventType = Literal[
    "ENGINE_STARTED",
    "ENGINE_STOPPING",
    "ENGINE_STOPPED",
    "ENGINE_PAUSED",
    "ENGINE_RESUMED",
    "ENGINE_ERROR",
]

AttemptEventType = Literal[
    "NODE_EXEC",
    "READY_CHECK",
    "SKIPPED_DISABLED",
    "SKIPPED_LOCK_BUSY",
    "ATTEMPT_BEGIN",
    "LOCK_ACQUIRED",
    "LOCK_WAIT",
    "SEND_KEY_OK",
    "SEND_KEY_FAIL",
    "START_WAIT",
    "START_CHECK",
    "START_OBSERVED",
    "RETRY_SCHEDULED",
    "CASTING_BEGIN",
    "COMPLETE_WAIT",
    "COMPLETE_CHECK",
    "COMPLETE_OBSERVED",
    "ATTEMPT_SUCCESS",
    "ATTEMPT_FAILED",
    "ATTEMPT_STOPPED",
    "BASELINE_SAMPLED",
]

CaptureEventType = Literal[
    "CAPTURE_PLAN_UPDATED",
    "CAPTURE_OK",
    "CAPTURE_ERROR",
]


@dataclass(frozen=True)
class EngineEvent:
    t_ms: int
    type: EngineEventType
    preset_id: str = ""
    reason: str = ""
    message: str = ""
    detail: str = ""
    extra: Dict[str, Any] = None  # type: ignore[assignment]


@dataclass(frozen=True)
class AttemptEvent:
    t_ms: int
    type: AttemptEventType
    attempt_id: str
    skill_id: str
    node_id: str = ""
    message: str = ""
    detail: str = ""
    extra: Dict[str, Any] = None  # type: ignore[assignment]


@dataclass(frozen=True)
class CaptureEvent:
    t_ms: int
    type: CaptureEventType
    message: str = ""
    detail: str = ""
    extra: Dict[str, Any] = None  # type: ignore[assignment]


Event = EngineEvent | AttemptEvent | CaptureEvent


class EventBus:
    """
    最小可用事件总线：
    - subscribe(fn) 注册回调（fn(event)）
    - publish(event) 逐个调用，吞异常
    """
    def __init__(self) -> None:
        self._subs: List[Callable[[Event], None]] = []

    def subscribe(self, fn: Callable[[Event], None]) -> None:
        if fn is None:
            return
        self._subs.append(fn)

    def publish(self, event: Event) -> None:
        for fn in list(self._subs):
            try:
                fn(event)
            except Exception:
                log.exception("EventBus subscriber failed")