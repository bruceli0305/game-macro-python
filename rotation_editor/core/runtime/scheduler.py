from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from .runtime_state import GlobalRuntimeState, ModeRuntimeState


@dataclass(frozen=True)
class ScheduleItem:
    scope: str           # "global" | "mode"
    track_id: str
    due_ms: int


class Scheduler:
    """
    最小调度器：
    - global 优先于 mode（同 due_ms 时）
    - mode 只在 eligible step 下运行
    """
    def choose_next(
        self,
        *,
        now_ms: int,
        global_rt: GlobalRuntimeState,
        mode_rt: Optional[ModeRuntimeState],
    ) -> Optional[ScheduleItem]:
        candidates: List[Tuple[int, int, str, str]] = []
        # tuple: (due, priority, scope, track_id) priority: global=0, mode=1

        for due, tid in global_rt.ready_candidates(now_ms):
            candidates.append((int(due), 0, "global", tid))

        if mode_rt is not None:
            mode_rt.ensure_step_runnable()
            for due, tid in mode_rt.ready_candidates(now_ms):
                candidates.append((int(due), 1, "mode", tid))

        if not candidates:
            return None

        candidates.sort(key=lambda x: (x[0], x[1]))
        due, _prio, scope, tid = candidates[0]
        return ScheduleItem(scope=scope, track_id=tid, due_ms=int(due))

    def next_wakeup_ms(
        self,
        *,
        global_rt: GlobalRuntimeState,
        mode_rt: Optional[ModeRuntimeState],
    ) -> Optional[int]:
        times: List[int] = []
        times.extend(global_rt.all_next_times())
        if mode_rt is not None:
            times.extend(mode_rt.eligible_next_times())
        if not times:
            return None
        return int(min(times))