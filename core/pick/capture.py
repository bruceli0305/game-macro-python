from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple, Dict
import threading

import mss


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
    - 每线程一个 mss.mss()（避免 Windows thread-local handle 问题）
    - 支持 monitor_key 解析屏幕矩形（Rect）
      key:
        "all"      -> monitors[0] 虚拟屏幕
        "primary"  -> monitors[1]（通常是主屏）
        "monitor_1"-> monitors[1], "monitor_2"-> monitors[2] ...
    - 提供绝对<->相对坐标转换（相对坐标以该 monitor 左上角为原点）
    """

    def __init__(self) -> None:
        self._local = threading.local()
        self._lock = threading.Lock()
        self._instances: Dict[int, mss.mss] = {}

    def _get_sct(self) -> mss.mss:
        tid = threading.get_ident()
        sct = getattr(self._local, "sct", None)
        if sct is None:
            sct = mss.mss()
            self._local.sct = sct
            with self._lock:
                self._instances[tid] = sct
        return sct

    def close(self) -> None:
        with self._lock:
            items = list(self._instances.items())
            self._instances.clear()
        for _tid, sct in items:
            try:
                sct.close()
            except Exception:
                pass

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
        """
        在指定 monitor_key 的屏幕矩形内，用绝对坐标采样。
        """
        rect = self.get_monitor_rect(monitor_key)
        x_abs = int(x_abs)
        y_abs = int(y_abs)

        if require_inside and not rect.contains_abs(x_abs, y_abs):
            raise ValueError(f"cursor outside monitor: {monitor_key}")

        # clamp inside rect
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