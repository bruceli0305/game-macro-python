# rotation_editor/core/runtime/cast_strategies.py
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from core.pick.capture import SampleSpec
from core.profiles import ProfileContext
from .context import RuntimeContext


class CastCompletionStrategy:
    """
    施法完成判定策略抽象：
    - wait_for_complete: 阻塞直到本次施法完成或超时
    """

    def wait_for_complete(
        self,
        *,
        skill_id: str,
        node_readbar_ms: int,
        rt_ctx_factory: Callable[[], RuntimeContext],
    ) -> None:
        raise NotImplementedError


@dataclass
class TimerCastStrategy(CastCompletionStrategy):
    """
    纯时间模式：
    - 只根据 node_readbar_ms 等待，不做任何像素检查
    """

    default_gap_ms: int = 50

    def wait_for_complete(
        self,
        *,
        skill_id: str,
        node_readbar_ms: int,
        rt_ctx_factory: Callable[[], RuntimeContext],
    ) -> None:
        total = max(0, int(node_readbar_ms))
        if total > 0:
            time.sleep(total / 1000.0)


@dataclass
class BarCastStrategy(CastCompletionStrategy):
    """
    施法条像素模式：

    - 使用 ProfileContext.points 中的某个点位作为“施法条读满时颜色”
    - 在 [0, node_readbar_ms * max_wait_factor] 内轮询该点颜色是否接近目标颜色
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
    ) -> None:
        # 找到施法条点位
        pts = getattr(self.ctx.points, "points", []) or []
        pt = next((p for p in pts if p.id == self.point_id), None)
        if pt is None:
            # 找不到点位时退回 Timer 策略
            TimerCastStrategy().wait_for_complete(
                skill_id=skill_id,
                node_readbar_ms=node_readbar_ms,
                rt_ctx_factory=rt_ctx_factory,
            )
            return

        target = pt.color
        tol = max(0, min(255, int(self.tolerance)))
        max_wait = int(node_readbar_ms * self.max_wait_factor) if node_readbar_ms > 0 else 2000
        if max_wait <= 0:
            max_wait = 2000

        start = time.monotonic() * 1000.0
        sample = SampleSpec(mode=pt.sample.mode, radius=int(pt.sample.radius))

        while True:
            now = time.monotonic() * 1000.0
            if now - start >= max_wait:
                break  # 超时视为完成

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
                # 采样失败时短暂等待重试
                time.sleep(self.poll_interval_ms / 1000.0)
                continue

            dr = abs(int(r) - int(target.r))
            dg = abs(int(g) - int(target.g))
            db = abs(int(b) - int(target.b))
            if max(dr, dg, db) <= tol:
                break

            time.sleep(self.poll_interval_ms / 1000.0)


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

    return BarCastStrategy(
        ctx=ctx,
        point_id=pid,
        tolerance=tol,
        poll_interval_ms=30,
        max_wait_factor=1.5,
    )