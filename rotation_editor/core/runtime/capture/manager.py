from __future__ import annotations

import time
import threading
from dataclasses import dataclass
from typing import Any, Optional, Tuple

from core.profiles import ProfileContext
from core.pick.capture import ScreenCapture
from core.pick.scanner import PixelScanner, CapturePlan

from rotation_editor.ast import ProbeRequirements

from .plan_builder import CapturePlanBuilder, PlanBuildResult


def _mono_ms() -> int:
    return int(time.monotonic() * 1000)


@dataclass(frozen=True)
class SnapshotOk:
    snapshot: Any
    captured_ms: int
    snapshot_age_ms: int
    plan: CapturePlan


@dataclass(frozen=True)
class CaptureUnavailable:
    error: str
    detail: str
    now_ms: int
    retry_after_ms: int


SnapshotResult = SnapshotOk | CaptureUnavailable


class CaptureEventSink:
    """
    可选的事件回调（先留接口，后续接 StateStore/EventBus）：
    """
    def on_plan_updated(self, probes: ProbeRequirements, plan: CapturePlan) -> None: ...
    def on_capture_ok(self, snapshot_age_ms: int) -> None: ...
    def on_capture_error(self, error: str, detail: str) -> None: ...


class CaptureManager:
    """
    集中管理：
    - capture plan（由 probes 驱动）
    - snapshot 缓存（减少重复截屏）
    - capture 异常吞并 + backoff（避免引擎崩溃/忙等）

    线程模型：
    - 预期在引擎线程使用（仍加锁，避免 UI 线程误用导致竞态）。
    """

    def __init__(
        self,
        *,
        ctx: ProfileContext,
        capture: Optional[ScreenCapture] = None,
        scanner: Optional[PixelScanner] = None,
        plan_builder: Optional[CapturePlanBuilder] = None,
        snapshot_cache_ttl_ms: int = 30,
        base_backoff_ms: int = 50,
        max_backoff_ms: int = 1000,
        sink: Optional[CaptureEventSink] = None,
    ) -> None:
        self._ctx = ctx
        self._cap = capture or ScreenCapture()
        self._scanner = scanner or PixelScanner(self._cap)
        self._builder = plan_builder or CapturePlanBuilder()
        self._sink = sink

        self._ttl_ms = int(max(0, snapshot_cache_ttl_ms))
        self._base_backoff_ms = int(max(0, base_backoff_ms))
        self._max_backoff_ms = int(max(0, max_backoff_ms))

        self._lock = threading.Lock()

        # plan cache
        self._last_probes_sig: Optional[Tuple[frozenset[str], frozenset[str]]] = None
        self._plan: CapturePlan = CapturePlan(plans={})

        # snapshot cache
        self._last_snapshot: Any = None
        self._last_capture_ms: int = 0

        # failure backoff
        self._fail_count: int = 0
        self._next_allowed_ms: int = 0
        self._last_error: str = ""
        self._last_detail: str = ""

    def get_scanner(self) -> PixelScanner:
        """
        给 SnapshotPixelSampler 使用：用同一个 PixelScanner 在 snapshot 上取样。
        """
        return self._scanner

    def invalidate_plan(self) -> None:
        with self._lock:
            self._last_probes_sig = None

    def update_plan(self, probes: ProbeRequirements) -> None:
        """
        若 probes 与上次相同则不重建。

        修正点：
        - 当 CapturePlanBuilder.build 抛异常时，不再更新 _last_probes_sig，
          这样同一组 probes 后续仍会尝试重新构建 plan，而不是“永远停留在失败状态”。
        """
        p_points = frozenset((probes.point_ids or set()))
        p_skillpix = frozenset((probes.skill_pixel_ids or set()))
        sig = (p_points, p_skillpix)

        with self._lock:
            if self._last_probes_sig == sig:
                return

        # build outside lock (可能较慢)
        res: PlanBuildResult
        try:
            res = self._builder.build(ctx=self._ctx, probes=probes, capture=self._cap)
        except Exception as e:
            # plan 构建失败也不抛；不更新 _last_probes_sig，这样后续仍会尝试重建
            with self._lock:
                self._plan = CapturePlan(plans={})
                self._last_error = "plan_build_failed"
                self._last_detail = str(e)

            if self._sink is not None:
                try:
                    self._sink.on_capture_error("plan_build_failed", str(e))
                except Exception:
                    pass
            return

        with self._lock:
            self._plan = res.plan
            self._last_probes_sig = sig

            # plan 改变时，丢弃旧 snapshot（避免 roi 改变导致坐标不一致）
            self._last_snapshot = None
            self._last_capture_ms = 0

        if self._sink is not None:
            try:
                self._sink.on_plan_updated(probes, res.plan)
            except Exception:
                pass

    def get_plan(self) -> CapturePlan:
        with self._lock:
            return self._plan

    def get_snapshot(self) -> SnapshotResult:
        """
        获取最新 snapshot（带缓存/退避），永不抛异常。
        """
        now = _mono_ms()

        with self._lock:
            # backoff gate
            if now < self._next_allowed_ms:
                return CaptureUnavailable(
                    error=self._last_error or "capture_backoff",
                    detail=self._last_detail or "",
                    now_ms=now,
                    retry_after_ms=int(self._next_allowed_ms),
                )

            plan = self._plan
            last_snap = self._last_snapshot
            last_ms = int(self._last_capture_ms)

        # cache hit
        if last_snap is not None and last_ms > 0 and self._ttl_ms > 0:
            age = now - last_ms
            if age >= 0 and age <= self._ttl_ms:
                if self._sink is not None:
                    try:
                        self._sink.on_capture_ok(int(age))
                    except Exception:
                        pass
                return SnapshotOk(
                    snapshot=last_snap,
                    captured_ms=last_ms,
                    snapshot_age_ms=int(age),
                    plan=plan,
                )

        # no probes -> allow returning "empty snapshot"
        if not getattr(plan, "plans", None):
            if self._sink is not None:
                try:
                    self._sink.on_capture_ok(0)
                except Exception:
                    pass
            return SnapshotOk(snapshot=None, captured_ms=now, snapshot_age_ms=0, plan=plan)

        # capture
        try:
            snap = self._scanner.capture_with_plan(plan)
        except Exception as e:
            # failure -> backoff
            with self._lock:
                self._fail_count += 1
                backoff = self._base_backoff_ms * (2 ** min(6, self._fail_count - 1))
                if self._max_backoff_ms > 0:
                    backoff = min(backoff, self._max_backoff_ms)
                self._next_allowed_ms = now + int(max(0, backoff))
                self._last_error = "capture_failed"
                self._last_detail = str(e)

            if self._sink is not None:
                try:
                    self._sink.on_capture_error("capture_failed", str(e))
                except Exception:
                    pass

            return CaptureUnavailable(
                error="capture_failed",
                detail=str(e),
                now_ms=now,
                retry_after_ms=int(now + int(max(0, backoff))),
            )

        # success
        with self._lock:
            self._last_snapshot = snap
            self._last_capture_ms = now
            self._fail_count = 0
            self._next_allowed_ms = 0
            self._last_error = ""
            self._last_detail = ""

        if self._sink is not None:
            try:
                self._sink.on_capture_ok(0)
            except Exception:
                pass

        return SnapshotOk(snapshot=snap, captured_ms=now, snapshot_age_ms=0, plan=plan)

    def close_current_thread(self) -> None:
        """
        释放 capture 线程资源（对齐你旧引擎 finally 逻辑）。
        """
        try:
            self._cap.close_current_thread()
        except Exception:
            pass