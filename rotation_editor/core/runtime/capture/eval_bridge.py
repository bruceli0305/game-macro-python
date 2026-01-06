from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Any

from core.profiles import ProfileContext

from rotation_editor.ast import (
    Expr,
    TriBool,
    EvalContext,
    evaluate,
    SnapshotPixelSampler,
    PixelSampler,
    MetricProvider,
    BaselineProvider,
)
from rotation_editor.runtime.capture.manager import (
    CaptureManager,
    SnapshotOk,
    CaptureUnavailable,
    SnapshotResult,
)
from rotation_editor.ast import ProbeRequirements


class NullPixelSampler:
    """
    一个永远返回 None 的采样器：
    - 用于 snapshot=None 的情况
    - 这样 evaluator 会对像素原子返回 Unknown，但 metric 原子仍可正常求值
    """
    def sample_rgb_abs(
        self,
        *,
        monitor_key: str,
        x_abs: int,
        y_abs: int,
        sample,
        require_inside: bool = False,
    ):
        return None


@dataclass(frozen=True)
class EvalWithCaptureResult:
    """
    用于上层（executor/state）记录调试信息：
    - tri: 三值结果
    - snapshot_age_ms: snapshot 缓存年龄（便于定位“用的是旧帧”）
    - capture_error: 若 capture 不可用，这里有错误码
    - capture_detail: 详细错误
    """
    tri: TriBool
    snapshot_age_ms: int = 0
    capture_error: str = ""
    capture_detail: str = ""


def ensure_plan_for_probes(
    *,
    capman: CaptureManager,
    probes: ProbeRequirements,
) -> None:
    """
    确保 capture plan 与 probes 匹配（如无变化则不会重建）。
    """
    capman.update_plan(probes)


def eval_expr_with_capture(
    expr: Expr,
    *,
    profile: ProfileContext,
    capman: CaptureManager,
    metrics: Optional[MetricProvider] = None,
    baseline: Optional[BaselineProvider] = None,
) -> EvalWithCaptureResult:
    """
    组合工具：
    - 从 CaptureManager 获取 snapshot（缓存 + backoff + 不抛异常）
    - 构造 PixelSampler（SnapshotPixelSampler / NullPixelSampler）
    - 调用 AST evaluator 进行三值逻辑求值

    关键点：
    - CaptureUnavailable -> 返回 Unknown（tri.value=None），并带 error/detail
    - snapshot=None -> 仍可求值（像素相关原子 Unknown，但 metric 原子可用）
    """
    snap_res: SnapshotResult = capman.get_snapshot()

    if isinstance(snap_res, CaptureUnavailable):
        tri = TriBool.u(f"capture_unavailable:{snap_res.error}")
        return EvalWithCaptureResult(
            tri=tri,
            snapshot_age_ms=0,
            capture_error=snap_res.error,
            capture_detail=snap_res.detail,
        )

    # SnapshotOk
    snapshot = snap_res.snapshot
    snapshot_age_ms = int(snap_res.snapshot_age_ms)

    if snapshot is None:
        sampler: PixelSampler = NullPixelSampler()  # type: ignore[assignment]
    else:
        # 使用 CaptureManager 内部的 PixelScanner 对 snapshot 进行 sample_rgb
        sampler = SnapshotPixelSampler(scanner=capman.get_scanner(), snapshot=snapshot)

    ectx = EvalContext(
        profile=profile,
        sampler=sampler,
        metrics=metrics,
        baseline=baseline,
    )

    tri = evaluate(expr, ectx)
    return EvalWithCaptureResult(
        tri=tri,
        snapshot_age_ms=snapshot_age_ms,
        capture_error="",
        capture_detail="",
    )