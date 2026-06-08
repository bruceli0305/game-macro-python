from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple
import threading

import mss


# 模块级 TLS：同一线程内所有 ScreenCapture 实例共享一个 mss.mss()
_TLS = threading.local()


@dataclass(frozen=True)
class SampleSpec:
    mode: str = "single"      # "single" | "mean_square"
    radius: int = 0           # mean_square 时有效


@dataclass(frozen=True)
class Rect:
    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    def contains_abs(self, x: int, y: int) -> bool:
        return self.left <= x < self.right and self.top <= y < self.bottom


class ScreenCapture:
    """
    Screen capture helper (mss), now using MODULE-LEVEL thread-local storage.

    Why:
    - Avoid creating multiple mss.mss() instances per thread when different parts
      of the app instantiate ScreenCapture independently.
    - All ScreenCapture objects in the same thread reuse one shared mss.mss().

    APIs:
    - _get_sct(): get thread-local mss instance (created lazily)
    - close_current_thread(): close only this thread's mss instance
    - close(): alias of close_current_thread()
    """

    def __init__(self) -> None:
        # no per-instance TLS anymore
        pass

    def _get_sct(self) -> mss.mss:
        sct = getattr(_TLS, "sct", None)
        if sct is None:
            sct = mss.mss()
            _TLS.sct = sct
        return sct

    def close_current_thread(self) -> None:
        sct = getattr(_TLS, "sct", None)
        if sct is not None:
            try:
                sct.close()
            except Exception:
                pass
            try:
                delattr(_TLS, "sct")
            except Exception:
                _TLS.sct = None  # type: ignore[attr-defined]

    def close(self) -> None:
        self.close_current_thread()

    @staticmethod
    def _clamp(v: int, lo: int, hi: int) -> int:
        if v < lo:
            return lo
        if v > hi:
            return hi
        return v

    def get_monitor_rect(self, monitor_key: str) -> Rect:
        sct = self._get_sct()
        key = (monitor_key or "all").strip().lower()
        monitors = sct.monitors  # type: ignore[attr-defined]

        if key == "all":
            idx = 0
        elif key == "primary":
            idx = 1 if len(monitors) > 1 else 0
        elif key.startswith("monitor_"):
            try:
                n = int(key.split("_", 1)[1])
                idx = n if n >= 1 else 0
            except Exception:
                idx = 0
        else:
            idx = 0

        if idx >= len(monitors):
            idx = 0

        m = monitors[idx]
        return Rect(
            left=int(m["left"]),
            top=int(m["top"]),
            width=int(m["width"]),
            height=int(m["height"]),
        )

    def find_monitor_key_for_abs(self, x_abs: int, y_abs: int, *, default: str = "primary") -> str:
        sct = self._get_sct()
        monitors = sct.monitors  # type: ignore[attr-defined]
        x_abs = int(x_abs)
        y_abs = int(y_abs)

        for idx in range(1, len(monitors)):
            m = monitors[idx]
            rect = Rect(
                left=int(m["left"]),
                top=int(m["top"]),
                width=int(m["width"]),
                height=int(m["height"]),
            )
            if rect.contains_abs(x_abs, y_abs):
                if idx == 1:
                    return "primary"
                return f"monitor_{idx}"

        return (default or "primary").strip() or "primary"

    # -------- coordinate conversion --------

    def abs_to_rel(self, x_abs: int, y_abs: int, monitor_key: str) -> Tuple[int, int]:
        rect = self.get_monitor_rect(monitor_key)
        return int(x_abs) - rect.left, int(y_abs) - rect.top

    def rel_to_abs(self, x_rel: int, y_rel: int, monitor_key: str) -> Tuple[int, int]:
        rect = self.get_monitor_rect(monitor_key)
        return rect.left + int(x_rel), rect.top + int(y_rel)

    # -------- sampling --------

    def get_rgb_scoped_abs(
        self,
        x_abs: int,
        y_abs: int,
        sample: SampleSpec,
        monitor_key: str,
        *,
        require_inside: bool = True,
    ) -> Tuple[int, int, int]:
        rect = self.get_monitor_rect(monitor_key)
        x_abs = int(x_abs)
        y_abs = int(y_abs)

        if require_inside and not rect.contains_abs(x_abs, y_abs):
            raise ValueError(f"cursor outside monitor: {monitor_key}")

        x_abs = self._clamp(x_abs, rect.left, rect.right - 1)
        y_abs = self._clamp(y_abs, rect.top, rect.bottom - 1)

        if sample.mode == "mean_square" and int(sample.radius) > 0:
            return self._mean_square_in_rect(x_abs, y_abs, int(sample.radius), rect)
        return self._single(x_abs, y_abs)

    def _single(self, x_abs: int, y_abs: int) -> Tuple[int, int, int]:
        sct = self._get_sct()
        box = {"left": int(x_abs), "top": int(y_abs), "width": 1, "height": 1}
        img = sct.grab(box)
        # BGRA
        b = img.raw[0]
        g = img.raw[1]
        r = img.raw[2]
        return int(r), int(g), int(b)

    def _mean_square_in_rect(self, x_abs: int, y_abs: int, r: int, rect: Rect) -> Tuple[int, int, int]:
        sct = self._get_sct()
        r = int(max(1, min(50, r)))
        size = 2 * r + 1

        max_left = rect.right - size
        max_top = rect.bottom - size

        left = self._clamp(int(x_abs - r), rect.left, max_left)
        top = self._clamp(int(y_abs - r), rect.top, max_top)

        box = {"left": left, "top": top, "width": size, "height": size}
        img = sct.grab(box)

        raw = img.raw  # BGRA
        n = size * size
        sum_r = sum_g = sum_b = 0
        for i in range(0, len(raw), 4):
            sum_b += raw[i + 0]
            sum_g += raw[i + 1]
            sum_r += raw[i + 2]
        return int(sum_r / n), int(sum_g / n), int(sum_b / n)