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
    施法完成判定策略抽象：
    - wait_for_complete: 阻塞直到本次施法完成或超时
    必须支持 stop_evt：一旦 stop_evt set，应尽快返回
    """

    def wait_for_complete(
        self,
        *,
        skill_id: str,
        node_readbar_ms: int,
        rt_ctx_factory: Callable[[], RuntimeContext],
        stop_evt: Optional[threading.Event] = None,
    ) -> None:
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
    纯时间模式：
    - 只根据 node_readbar_ms 等待，不做任何像素检查
    - 支持 stop_evt 可中断
    """

    default_gap_ms: int = 50
    chunk_ms: int = 30  # 分片 sleep，确保 stop 能快速生效

    def wait_for_complete(
        self,
        *,
        skill_id: str,
        node_readbar_ms: int,
        rt_ctx_factory: Callable[[], RuntimeContext],
        stop_evt: Optional[threading.Event] = None,
    ) -> None:
        total = max(0, int(node_readbar_ms))
        if total <= 0:
            return

        remaining = total
        chunk = max(5, int(self.chunk_ms))
        while remaining > 0:
            if stop_evt is not None and stop_evt.is_set():
                return
            step = chunk if remaining > chunk else remaining
            stopped = _wait_ms(stop_evt, step)
            if stopped:
                return
            remaining -= step


@dataclass
class BarCastStrategy(CastCompletionStrategy):
    """
    施法条像素模式（可中断）：

    - 使用 ProfileContext.points 中的某个点位作为“施法条读满时颜色”
    - 在 [0, node_readbar_ms * max_wait_factor] 内轮询该点颜色是否接近目标颜色
    - stop_evt set 时立即返回
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
    ) -> None:
        # 瞬发技能：直接返回
        try:
            total_ms = int(node_readbar_ms)
        except Exception:
            total_ms = 0
        if total_ms <= 0:
            return

        if stop_evt is not None and stop_evt.is_set():
            return

        # 找到施法条点位
        pts = getattr(self.ctx.points, "points", []) or []
        pt = next((p for p in pts if p.id == self.point_id), None)
        if pt is None:
            # 找不到点位时退回 Timer
            TimerCastStrategy().wait_for_complete(
                skill_id=skill_id,
                node_readbar_ms=total_ms,
                rt_ctx_factory=rt_ctx_factory,
                stop_evt=stop_evt,
            )
            return

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
                return

            now = time.monotonic() * 1000.0
            if now - start >= float(max_wait):
                return  # 超时视为完成

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
                # 采样失败：短暂等待后重试（可被 stop 打断）
                _wait_ms(stop_evt, poll)
                continue

            dr = abs(int(r) - int(target.r))
            dg = abs(int(g) - int(target.g))
            db = abs(int(b) - int(target.b))
            if max(dr, dg, db) <= tol:
                return

            _wait_ms(stop_evt, poll)


def make_cast_strategy(ctx: ProfileContext, *, default_gap_ms: int = 50) -> CastCompletionStrategy:
    """
    根据 ctx.base.cast_bar 选择合适的施法完成策略。
    """
    cb = getattr(ctx.base, "cast_bar", None)
    if cb is None:
        return TimerCastStrategy(default_gap_ms=default_gap_ms)

    mode = (getattr(cb, "mode", "timer") or "timer").strip().lower()
    pid = getattr(cb, "point_id", "") or ""
    tol = int(getattr(cb, "tolerance", 15) or 15)

    if mode != "bar" or not pid:
        return TimerCastStrategy(default_gap_ms=default_gap_ms)

    try:
        poll = int(getattr(cb, "poll_interval_ms", 30) or 30)
    except Exception:
        poll = 30
    if poll < 10:
        poll = 10
    if poll > 1000:
        poll = 1000

    try:
        factor = float(getattr(cb, "max_wait_factor", 1.5) or 1.5)
    except Exception:
        factor = 1.5
    if factor < 0.1:
        factor = 0.1
    if factor > 10.0:
        factor = 10.0

    return BarCastStrategy(
        ctx=ctx,
        point_id=pid,
        tolerance=tol,
        poll_interval_ms=poll,
        max_wait_factor=factor,
    )