from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Tuple
import time

from core.pick.capture import ScreenCapture, SampleSpec


# ---------- 截图计划（由上层构建） ----------

@dataclass
class MonitorCapturePlan:
    """
    单个物理屏幕的截取计划：
    - monitor: monitor_key，例如 "primary" / "monitor_2" / "all"
    - mode:   "roi" 表示截取指定矩形，"full" 表示整屏
    - roi_left/top/width/height: ROI 的虚拟屏绝对坐标和尺寸（mode="full" 时为整屏）
    """
    monitor: str
    mode: str
    roi_left: int
    roi_top: int
    roi_width: int
    roi_height: int


@dataclass
class CapturePlan:
    """
    全局截取计划：
    - plans: monitor_key -> MonitorCapturePlan
    """
    plans: Dict[str, MonitorCapturePlan]


# ---------- 截图结果 ----------

@dataclass
class MonitorFrame:
    """
    单个物理屏幕的一帧截图（按照截取计划中的 ROI）：
    - monitor_key: 对应的 monitor 标识
    - left/top/width/height: 本帧在虚拟坐标系中的位置和大小
    - raw: BGRA 字节数组（mss.ScreenShot.raw）
    """
    monitor_key: str
    left: int
    top: int
    width: int
    height: int
    raw: bytes


@dataclass
class FrameSnapshot:
    """
    一次扫描得到的所有屏幕帧：
    - frames: monitor_key -> MonitorFrame
    - ts: 截图时间戳（秒）
    """
    frames: Dict[str, MonitorFrame]
    ts: float


# ---------- 单个采样点描述 ----------

@dataclass(frozen=True)
class PixelProbe:
    """
    待采样的像素点描述：
    - monitor: 物理屏幕标识（"primary" / "monitor_2" / "all" 等）
    - vx/vy:   虚拟屏绝对坐标
    - sample:  采样规格（single / mean_square + radius）
    """
    monitor: str
    vx: int
    vy: int
    sample: SampleSpec


class PixelScanner:
    """
    高效屏幕像素扫描器（基于 ROI + 整屏混合）：

    - capture_with_plan(plan): 按给定 CapturePlan，分别对每个 monitor 截取一帧 ROI/整屏
      => 返回 FrameSnapshot，包含所有 MonitorFrame
    - sample_rgb(snapshot, probe): 在 snapshot 中对某个 PixelProbe 采样 RGB 值

    注意：
    - 若某个 monitor 不在 snapshot 中，sample_rgb 会回退到 ScreenCapture.get_rgb_scoped_abs
     （保证兼容性，尽管效率稍低）。
    """

    def __init__(self, capture: ScreenCapture) -> None:
        self._cap = capture

    # ---------- 截图 ----------

    def capture_with_plan(self, plan: CapturePlan) -> FrameSnapshot:
        """
        按照 CapturePlan，对每个 monitor 抓取一帧 ROI/整屏截图。
        """
        # 使用 ScreenCapture 提供的 thread-local mss 实例
        sct = self._cap._get_sct()  # type: ignore[attr-defined]

        frames: Dict[str, MonitorFrame] = {}
        ts = time.time()

        for mon, mp in plan.plans.items():
            left = int(mp.roi_left)
            top = int(mp.roi_top)
            width = int(mp.roi_width)
            height = int(mp.roi_height)
            if width <= 0 or height <= 0:
                continue

            box = {
                "left": left,
                "top": top,
                "width": width,
                "height": height,
            }
            img = sct.grab(box)  # mss.ScreenShot
            mf = MonitorFrame(
                monitor_key=mon,
                left=left,
                top=top,
                width=width,
                height=height,
                raw=bytes(img.raw),  # BGRA
            )
            frames[mon] = mf

        return FrameSnapshot(frames=frames, ts=ts)

    # ---------- 采样 ----------

    def sample_rgb(self, snap: FrameSnapshot, probe: PixelProbe) -> Tuple[int, int, int]:
        """
        在给定 FrameSnapshot 中，对 PixelProbe 采样 RGB 颜色。

        - 若 snapshot 内有对应 monitor 的帧，则在该帧内按 ROI 相对坐标采样。
        - 否则，回退到 ScreenCapture 单点抓取。
        """
        mk = (probe.monitor or "primary").strip().lower() or "primary"
        mf = snap.frames.get(mk)
        if mf is None:
            # 回退：老方式单点抓取
            return self._cap.get_rgb_scoped_abs(
                x_abs=int(probe.vx),
                y_abs=int(probe.vy),
                sample=probe.sample,
                monitor_key=mk,
                require_inside=False,
            )

        # 绝对坐标 -> 帧内相对坐标（考虑 ROI 偏移）
        x_abs = int(probe.vx)
        y_abs = int(probe.vy)

        x_rel = x_abs - mf.left
        y_rel = y_abs - mf.top

        # clamp 到帧内
        if x_rel < 0:
            x_rel = 0
        if x_rel >= mf.width:
            x_rel = mf.width - 1
        if y_rel < 0:
            y_rel = 0
        if y_rel >= mf.height:
            y_rel = mf.height - 1

        if probe.sample.mode == "mean_square" and int(probe.sample.radius) > 0:
            return self._mean_square_in_frame(
                mf,
                x_rel=x_rel,
                y_rel=y_rel,
                radius=int(probe.sample.radius),
            )
        return self._single_in_frame(mf, x_rel=x_rel, y_rel=y_rel)

    # ---------- 内部：从完整帧中采样 ----------

    @staticmethod
    def _single_in_frame(mf: MonitorFrame, x_rel: int, y_rel: int) -> Tuple[int, int, int]:
        """
        从完整帧中采样单个像素（BGRA -> RGB）。
        """
        w = mf.width
        h = mf.height
        if w <= 0 or h <= 0:
            return (0, 0, 0)

        if x_rel < 0:
            x_rel = 0
        if x_rel >= w:
            x_rel = w - 1
        if y_rel < 0:
            y_rel = 0
        if y_rel >= h:
            y_rel = h - 1

        idx = (y_rel * w + x_rel) * 4
        raw = mf.raw
        if idx + 3 >= len(raw):
            return (0, 0, 0)

        b = raw[idx + 0]
        g = raw[idx + 1]
        r = raw[idx + 2]
        return (int(r), int(g), int(b))

    @staticmethod
    def _mean_square_in_frame(
        mf: MonitorFrame,
        *,
        x_rel: int,
        y_rel: int,
        radius: int,
    ) -> Tuple[int, int, int]:
        """
        在完整帧中，以 (x_rel, y_rel) 为中心，对半径 r 的正方形区域做均值采样。
        """
        w = mf.width
        h = mf.height
        if w <= 0 or h <= 0:
            return (0, 0, 0)

        r = int(max(1, min(50, radius)))

        x0 = x_rel - r
        x1 = x_rel + r
        y0 = y_rel - r
        y1 = y_rel + r

        if x0 < 0:
            x0 = 0
        if x1 >= w:
            x1 = w - 1
        if y0 < 0:
            y0 = 0
        if y1 >= h:
            y1 = h - 1

        raw = mf.raw
        sum_r = 0
        sum_g = 0
        sum_b = 0
        count = 0

        for yy in range(y0, y1 + 1):
            base_row = yy * w
            for xx in range(x0, x1 + 1):
                idx = (base_row + xx) * 4
                if idx + 3 >= len(raw):
                    continue
                b = raw[idx + 0]
                g = raw[idx + 1]
                r = raw[idx + 2]
                sum_b += b
                sum_g += g
                sum_r += r
                count += 1

        if count <= 0:
            return (0, 0, 0)

        return (
            int(sum_r / count),
            int(sum_g / count),
            int(sum_b / count),
        )