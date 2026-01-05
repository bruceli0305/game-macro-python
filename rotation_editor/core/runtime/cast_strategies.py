from __future__ import annotations

import time
import threading
from dataclasses import dataclass
from typing import Callable, Optional

from core.pick.capture import SampleSpec
from core.profiles import ProfileContext
from .context import RuntimeContext


class CastCompletionStrategy:
    """
    施法完成判定策略抽象（可中断）：
    - 返回 True 表示“完成信号成立/正常完成”
    - 返回 False 表示“stop/超时/无法确认完成”
    """

    def wait_for_complete(
        self,
        *,
        skill_id: str,
        node_readbar_ms: int,
        rt_ctx_factory: Callable[[], RuntimeContext],
        stop_evt: Optional[threading.Event] = None,
    ) -> bool:
        raise NotImplementedError


def _wait_ms(stop_evt: Optional[threading.Event], ms: int) -> bool:
    """
    等待 ms 毫秒。若 stop_evt 在等待期间被 set，则提前返回 True。
    """
    ms = int(ms)
    if ms <= 0:
        return bool(stop_evt and stop_evt.is_set())
    if stop_evt is None:
        time.sleep(ms / 1000.0)
        return False
    return bool(stop_evt.wait(ms / 1000.0))


@dataclass
class TimerCastStrategy(CastCompletionStrategy):
    """
    纯时间模式（可中断）：
    - readbar_ms <= 0：直接返回 True
    - readbar_ms > 0 ：等待 readbar_ms，若 stop 则返回 False，否则 True
    """

    chunk_ms: int = 30

    def wait_for_complete(
        self,
        *,
        skill_id: str,
        node_readbar_ms: int,
        rt_ctx_factory: Callable[[], RuntimeContext],
        stop_evt: Optional[threading.Event] = None,
    ) -> bool:
        total = int(node_readbar_ms or 0)
        if total <= 0:
            return True

        remaining = total
        chunk = max(5, int(self.chunk_ms))
        while remaining > 0:
            if stop_evt is not None and stop_evt.is_set():
                return False
            step = chunk if remaining > chunk else remaining
            if _wait_ms(stop_evt, step):
                return False
            remaining -= step

        return True


@dataclass
class BarCastStrategy(CastCompletionStrategy):
    """
    施法条像素模式（可中断）：
    - 若检测到施法条“完成颜色”匹配：返回 True
    - 若超时或 stop：返回 False
    """

    ctx: ProfileContext
    point_id: str
    tolerance: int
    poll_interval_ms: int = 30
    max_wait_factor: float = 1.5

    def wait_for_complete(
        self,
        *,
        skill_id: str,
        node_readbar_ms: int,
        rt_ctx_factory: Callable[[], RuntimeContext],
        stop_evt: Optional[threading.Event] = None,
    ) -> bool:
        total_ms = int(node_readbar_ms or 0)
        if total_ms <= 0:
            # 瞬发：视为完成
            return True

        if stop_evt is not None and stop_evt.is_set():
            return False

        pts = getattr(self.ctx.points, "points", []) or []
        pt = next((p for p in pts if p.id == self.point_id), None)
        if pt is None:
            # 找不到点位：退回 Timer（能被 stop 中断）
            return TimerCastStrategy().wait_for_complete(
                skill_id=skill_id,
                node_readbar_ms=total_ms,
                rt_ctx_factory=rt_ctx_factory,
                stop_evt=stop_evt,
            )

        target = pt.color
        tol = max(0, min(255, int(self.tolerance)))

        max_wait = int(total_ms * float(self.max_wait_factor))
        if max_wait <= 0:
            max_wait = 500

        poll = int(self.poll_interval_ms)
        if poll < 10:
            poll = 10
        if poll > 1000:
            poll = 1000

        start = time.monotonic() * 1000.0
        sample = SampleSpec(mode=pt.sample.mode, radius=int(pt.sample.radius))

        while True:
            if stop_evt is not None and stop_evt.is_set():
                return False

            now = time.monotonic() * 1000.0
            if now - start >= float(max_wait):
                return False  # 超时

            rt_ctx = rt_ctx_factory()
            try:
                r, g, b = rt_ctx.capture.get_rgb_scoped_abs(
                    x_abs=int(pt.vx),
                    y_abs=int(pt.vy),
                    sample=sample,
                    monitor_key=pt.monitor or "primary",
                    require_inside=False,
                )
            except Exception:
                _wait_ms(stop_evt, poll)
                continue

            dr = abs(int(r) - int(target.r))
            dg = abs(int(g) - int(target.g))
            db = abs(int(b) - int(target.b))
            if max(dr, dg, db) <= tol:
                return True

            _wait_ms(stop_evt, poll)


def make_cast_strategy(ctx: ProfileContext, *, default_gap_ms: int = 50) -> CastCompletionStrategy:
    cb = getattr(ctx.base, "cast_bar", None)
    if cb is None:
        return TimerCastStrategy()

    mode = (getattr(cb, "mode", "timer") or "timer").strip().lower()
    pid = getattr(cb, "point_id", "") or ""
    tol = int(getattr(cb, "tolerance", 15) or 15)

    if mode != "bar" or not pid:
        return TimerCastStrategy()

    try:
        poll = int(getattr(cb, "poll_interval_ms", 30) or 30)
    except Exception:
        poll = 30
    poll = max(10, min(1000, poll))

    try:
        factor = float(getattr(cb, "max_wait_factor", 1.5) or 1.5)
    except Exception:
        factor = 1.5
    factor = max(0.1, min(10.0, factor))

    return BarCastStrategy(
        ctx=ctx,
        point_id=pid,
        tolerance=tol,
        poll_interval_ms=poll,
        max_wait_factor=factor,
    )