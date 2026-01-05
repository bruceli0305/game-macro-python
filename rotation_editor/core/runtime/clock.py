from __future__ import annotations

import time
import threading
from typing import Optional


def mono_ms() -> int:
    return int(time.monotonic() * 1000)


def wait_ms(stop_evt: Optional[threading.Event], ms: int) -> bool:
    """
    等待 ms 毫秒；若 stop_evt 在等待期间被 set，则提前返回 True。
    """
    ms = int(ms)
    if ms <= 0:
        return bool(stop_evt and stop_evt.is_set())
    if stop_evt is None:
        time.sleep(ms / 1000.0)
        return False
    return bool(stop_evt.wait(ms / 1000.0))