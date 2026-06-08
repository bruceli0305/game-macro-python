from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple
import time

from core.pick.capture import ScreenCapture, SampleSpec


@dataclass
class MonitorCapturePlan:
    monitor: str
    mode: str
    roi_left: int
    roi_top: int
    roi_width: int
    roi_height: int


@dataclass
class CapturePlan:
    plans: Dict[str, MonitorCapturePlan]


@dataclass
class MonitorFrame:
    monitor_key: str
    left: int
    top: int
    width: int
    height: int
    raw: bytes


@dataclass
class FrameSnapshot:
    frames: Dict[str, MonitorFrame]
    ts: float


@dataclass(frozen=True)
class PixelProbe:
    monitor: str
    vx: int
    vy: int
    sample: SampleSpec


class PixelScanner:
    def __init__(self, capture: ScreenCapture) -> None:
        self._cap = capture

    def capture_with_plan(self, plan: CapturePlan) -> FrameSnapshot:
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

            box = {"left": left, "top": top, "width": width, "height": height}
            img = sct.grab(box)

            frames[mon] = MonitorFrame(
                monitor_key=mon,
                left=left,
                top=top,
                width=width,
                height=height,
                raw=bytes(img.raw),  # BGRA
            )

        return FrameSnapshot(frames=frames, ts=ts)

    def sample_rgb(self, snap: FrameSnapshot, probe: PixelProbe) -> Tuple[int, int, int]:
        mk = (probe.monitor or "primary").strip().lower() or "primary"
        mf = snap.frames.get(mk)
        if mf is None:
            return self._cap.get_rgb_scoped_abs(
                x_abs=int(probe.vx),
                y_abs=int(probe.vy),
                sample=probe.sample,
                monitor_key=mk,
                require_inside=False,
            )

        x_abs = int(probe.vx)
        y_abs = int(probe.vy)

        x_rel = x_abs - mf.left
        y_rel = y_abs - mf.top

        # 关键改动：不在 ROI 帧内，直接 fallback，禁止 clamp（避免 silent wrong）
        if x_rel < 0 or x_rel >= mf.width or y_rel < 0 or y_rel >= mf.height:
            return self._cap.get_rgb_scoped_abs(
                x_abs=int(probe.vx),
                y_abs=int(probe.vy),
                sample=probe.sample,
                monitor_key=mk,
                require_inside=False,
            )

        if probe.sample.mode == "mean_square" and int(probe.sample.radius) > 0:
            return self._mean_square_in_frame(mf, x_rel=x_rel, y_rel=y_rel, radius=int(probe.sample.radius))

        return self._single_in_frame(mf, x_rel=x_rel, y_rel=y_rel)

    @staticmethod
    def _single_in_frame(mf: MonitorFrame, x_rel: int, y_rel: int) -> Tuple[int, int, int]:
        w = mf.width
        h = mf.height
        if w <= 0 or h <= 0:
            return (0, 0, 0)

        idx = (int(y_rel) * int(w) + int(x_rel)) * 4
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
        sum_r = sum_g = sum_b = 0
        count = 0

        for yy in range(y0, y1 + 1):
            base_row = yy * w
            for xx in range(x0, x1 + 1):
                idx = (base_row + xx) * 4
                if idx + 3 >= len(raw):
                    continue
                b = raw[idx + 0]
                g = raw[idx + 1]
                rr = raw[idx + 2]
                sum_b += b
                sum_g += g
                sum_r += rr
                count += 1

        if count <= 0:
            return (0, 0, 0)

        return (int(sum_r / count), int(sum_g / count), int(sum_b / count))