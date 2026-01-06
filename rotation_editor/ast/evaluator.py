from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Protocol, Tuple, Literal

from core.profiles import ProfileContext
from core.pick.capture import SampleSpec

from .nodes import (
    Expr,
    And,
    Or,
    Not,
    Const,
    PixelMatchPoint,
    PixelMatchSkill,
    CastBarChanged,
    SkillMetricGE,
    SkillMetric,
)

RGB = Tuple[int, int, int]


class PixelSampler(Protocol):
    """
    像素采样接口（基于 snapshot 或实时截屏都可以实现）：
    - sample_rgb_abs 返回 (r,g,b) 或 None（表示采样不可用/失败 -> Unknown）
    """
    def sample_rgb_abs(
        self,
        *,
        monitor_key: str,
        x_abs: int,
        y_abs: int,
        sample: SampleSpec,
        require_inside: bool = False,
    ) -> Optional[RGB]: ...


class MetricProvider(Protocol):
    """
    指标读取接口：
    - 返回 int 或 None（不可用 -> Unknown）
    """
    def get_metric(self, skill_id: str, metric: SkillMetric) -> Optional[int]: ...


class BaselineProvider(Protocol):
    """
    基线读取接口（用于 CastBarChanged 等“相对变化”信号）：
    - point_id -> baseline rgb
    - 若无 baseline，返回 None（-> Unknown）
    """
    def get_point_baseline_rgb(self, point_id: str) -> Optional[RGB]: ...


@dataclass(frozen=True)
class TriBool:
    """
    三值逻辑结果：
    - value: True/False/None(None 表示 Unknown)
    - reason: 可选（Unknown 的原因/上下文，便于调试面板展示）
    """
    value: Optional[bool]
    reason: str = ""

    @staticmethod
    def t() -> "TriBool":
        return TriBool(True, "")

    @staticmethod
    def f(reason: str = "") -> "TriBool":
        return TriBool(False, reason)

    @staticmethod
    def u(reason: str = "") -> "TriBool":
        return TriBool(None, reason)

    def is_true(self) -> bool:
        return self.value is True

    def is_false(self) -> bool:
        return self.value is False

    def is_unknown(self) -> bool:
        return self.value is None


def tri_to_bool(v: TriBool, *, unknown_as: bool = False) -> bool:
    """
    把 TriBool 压成 bool：Unknown 按 unknown_as 处理。
    """
    if v.value is None:
        return bool(unknown_as)
    return bool(v.value)


@dataclass
class EvalContext:
    """
    evaluator 的运行时上下文：
    - profile: 用于把 point_id/skill_id 解析为坐标与目标色
    - sampler: 基于 snapshot 的取样器（或实时取样器）
    - metrics: 技能指标提供者（success/attempt/cast_started 等）
    - baseline: CastBarChanged 等需要的 baseline 提供者（可选）
    """
    profile: ProfileContext
    sampler: PixelSampler
    metrics: Optional[MetricProvider] = None
    baseline: Optional[BaselineProvider] = None


def evaluate(expr: Expr, ctx: EvalContext) -> TriBool:
    """
    三值逻辑求值（Kleene 逻辑）：

    AND：
      - 任一 False -> False
      - 否则若存在 Unknown -> Unknown
      - 否则 True

    OR：
      - 任一 True -> True
      - 否则若存在 Unknown -> Unknown
      - 否则 False

    NOT：Unknown 仍是 Unknown
    """
    if isinstance(expr, Const):
        return TriBool.t() if expr.value else TriBool.f()

    if isinstance(expr, Not):
        r = evaluate(expr.child, ctx)
        if r.is_unknown():
            return r
        return TriBool.f() if r.is_true() else TriBool.t()

    if isinstance(expr, And):
        saw_unknown: Optional[TriBool] = None
        for c in expr.children:
            r = evaluate(c, ctx)
            if r.is_false():
                return r
            if r.is_unknown() and saw_unknown is None:
                saw_unknown = r
        return saw_unknown if saw_unknown is not None else TriBool.t()

    if isinstance(expr, Or):
        saw_unknown: Optional[TriBool] = None
        for c in expr.children:
            r = evaluate(c, ctx)
            if r.is_true():
                return r
            if r.is_unknown() and saw_unknown is None:
                saw_unknown = r
        return saw_unknown if saw_unknown is not None else TriBool.f()

    # atoms
    return _eval_atom(expr, ctx)


def _eval_atom(expr: Expr, ctx: EvalContext) -> TriBool:
    if isinstance(expr, PixelMatchPoint):
        return _eval_pixel_match_point(expr, ctx)

    if isinstance(expr, PixelMatchSkill):
        return _eval_pixel_match_skill(expr, ctx)

    if isinstance(expr, CastBarChanged):
        return _eval_cast_bar_changed(expr, ctx)

    if isinstance(expr, SkillMetricGE):
        return _eval_skill_metric_ge(expr, ctx)

    # 理论上不会到这里（codec/compiler 已限制）
    return TriBool.u(f"unhandled_atom:{type(expr).__name__}")


def _rgb_diff_max(a: RGB, b: RGB) -> int:
    return max(abs(int(a[0]) - int(b[0])), abs(int(a[1]) - int(b[1])), abs(int(a[2]) - int(b[2])))


def _clamp_tol(tol: int) -> int:
    t = int(tol)
    if t < 0:
        return 0
    if t > 255:
        return 255
    return t


def _eval_pixel_match_point(expr: PixelMatchPoint, ctx: EvalContext) -> TriBool:
    pid = (expr.point_id or "").strip()
    if not pid:
        return TriBool.u("point_id_empty")

    # resolve point
    pts = getattr(ctx.profile.points, "points", []) or []
    p = next((x for x in pts if (getattr(x, "id", "") or "") == pid), None)
    if p is None:
        return TriBool.u("point_missing")

    # build sample spec
    try:
        sample = SampleSpec(mode=p.sample.mode, radius=int(p.sample.radius))
    except Exception:
        sample = SampleSpec(mode="single", radius=0)

    # target rgb
    try:
        target: RGB = (int(p.color.r), int(p.color.g), int(p.color.b))
    except Exception:
        return TriBool.u("point_color_invalid")

    cur = ctx.sampler.sample_rgb_abs(
        monitor_key=(getattr(p, "monitor", None) or "primary"),
        x_abs=int(getattr(p, "vx", 0)),
        y_abs=int(getattr(p, "vy", 0)),
        sample=sample,
        require_inside=False,
    )
    if cur is None:
        return TriBool.u("sample_failed")

    tol = _clamp_tol(int(expr.tolerance))
    diff = _rgb_diff_max(cur, target)
    return TriBool.t() if diff <= tol else TriBool.f()


def _eval_pixel_match_skill(expr: PixelMatchSkill, ctx: EvalContext) -> TriBool:
    sid = (expr.skill_id or "").strip()
    if not sid:
        return TriBool.u("skill_id_empty")

    skills = getattr(ctx.profile.skills, "skills", []) or []
    s = next((x for x in skills if (getattr(x, "id", "") or "") == sid), None)
    if s is None:
        return TriBool.u("skill_missing")

    pix = getattr(s, "pixel", None)
    if pix is None:
        return TriBool.u("skill_pixel_missing")

    # coords + sample
    try:
        sample = SampleSpec(mode=pix.sample.mode, radius=int(pix.sample.radius))
    except Exception:
        sample = SampleSpec(mode="single", radius=0)

    try:
        target: RGB = (int(pix.color.r), int(pix.color.g), int(pix.color.b))
    except Exception:
        return TriBool.u("skill_pixel_color_invalid")

    cur = ctx.sampler.sample_rgb_abs(
        monitor_key=(getattr(pix, "monitor", None) or "primary"),
        x_abs=int(getattr(pix, "vx", 0)),
        y_abs=int(getattr(pix, "vy", 0)),
        sample=sample,
        require_inside=False,
    )
    if cur is None:
        return TriBool.u("sample_failed")

    tol = _clamp_tol(int(expr.tolerance))
    diff = _rgb_diff_max(cur, target)
    return TriBool.t() if diff <= tol else TriBool.f()


def _eval_cast_bar_changed(expr: CastBarChanged, ctx: EvalContext) -> TriBool:
    """
    与 baseline 比较：diff > tol 认为“变化成立”。

    注意：
    - baseline 的采集由执行器/状态机在合适时机记录（例如发键前），并通过 ctx.baseline 提供；
    - 若 baseline 不存在 -> Unknown（上层可选择重试/失败）。
    """
    pid = (expr.point_id or "").strip()
    if not pid:
        return TriBool.u("point_id_empty")

    if ctx.baseline is None:
        return TriBool.u("baseline_provider_missing")

    base = ctx.baseline.get_point_baseline_rgb(pid)
    if base is None:
        return TriBool.u("baseline_missing")

    # resolve point
    pts = getattr(ctx.profile.points, "points", []) or []
    p = next((x for x in pts if (getattr(x, "id", "") or "") == pid), None)
    if p is None:
        return TriBool.u("point_missing")

    try:
        sample = SampleSpec(mode=p.sample.mode, radius=int(p.sample.radius))
    except Exception:
        sample = SampleSpec(mode="single", radius=0)

    cur = ctx.sampler.sample_rgb_abs(
        monitor_key=(getattr(p, "monitor", None) or "primary"),
        x_abs=int(getattr(p, "vx", 0)),
        y_abs=int(getattr(p, "vy", 0)),
        sample=sample,
        require_inside=False,
    )
    if cur is None:
        return TriBool.u("sample_failed")

    tol = _clamp_tol(int(expr.tolerance))
    diff = _rgb_diff_max(cur, base)
    return TriBool.t() if diff > tol else TriBool.f()


def _eval_skill_metric_ge(expr: SkillMetricGE, ctx: EvalContext) -> TriBool:
    sid = (expr.skill_id or "").strip()
    if not sid:
        return TriBool.u("skill_id_empty")

    if ctx.metrics is None:
        return TriBool.u("metrics_provider_missing")

    metric = expr.metric
    try:
        cur = ctx.metrics.get_metric(sid, metric)
    except Exception:
        cur = None

    if cur is None:
        return TriBool.u("metric_unavailable")

    need = int(expr.count)
    if need <= 0:
        need = 1
    return TriBool.t() if int(cur) >= need else TriBool.f()


# ----------------------------
# Snapshot sampler adapter
# ----------------------------

class SnapshotPixelSampler:
    """
    基于 PixelScanner + snapshot 的采样器适配：
    - 用于“同一帧 snapshot”内反复评估多个 atom，不重复截屏。
    """
    def __init__(self, *, scanner, snapshot: Any) -> None:
        self._scanner = scanner
        self._snapshot = snapshot

    def sample_rgb_abs(
        self,
        *,
        monitor_key: str,
        x_abs: int,
        y_abs: int,
        sample: SampleSpec,
        require_inside: bool = False,
    ) -> Optional[RGB]:
        try:
            from core.pick.scanner import PixelProbe
        except Exception:
            return None

        try:
            probe = PixelProbe(
                monitor=str(monitor_key or "primary"),
                vx=int(x_abs),
                vy=int(y_abs),
                sample=sample,
            )
            r, g, b = self._scanner.sample_rgb(self._snapshot, probe)
            return int(r), int(g), int(b)
        except Exception:
            return None


# ----------------------------
# Simple providers (optional)
# ----------------------------

class DictMetricProvider:
    """
    一个简单的 metrics provider（用于单测或临时接线）：
    metrics_map[skill_id][metric] = int
    """
    def __init__(self, metrics_map: Dict[str, Dict[str, int]]) -> None:
        self._m = metrics_map or {}

    def get_metric(self, skill_id: str, metric: SkillMetric) -> Optional[int]:
        sid = (skill_id or "").strip()
        if not sid:
            return None
        row = self._m.get(sid)
        if not isinstance(row, dict):
            return None
        v = row.get(str(metric))
        if v is None:
            return None
        try:
            return int(v)
        except Exception:
            return None


class DictBaselineProvider:
    """
    baseline_map[point_id] = (r,g,b)
    """
    def __init__(self, baseline_map: Dict[str, RGB]) -> None:
        self._b = baseline_map or {}

    def get_point_baseline_rgb(self, point_id: str) -> Optional[RGB]:
        pid = (point_id or "").strip()
        if not pid:
            return None
        v = self._b.get(pid)
        if v is None:
            return None
        try:
            return int(v[0]), int(v[1]), int(v[2])
        except Exception:
            return None