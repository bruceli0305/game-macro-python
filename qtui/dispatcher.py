# qtui/dispatcher.py
from __future__ import annotations

import logging
from typing import Callable

from PySide6.QtCore import QObject, Signal, Slot


log = logging.getLogger(__name__)


class QtDispatcher(QObject):
    """
    简单的 UI 线程调度器：
    - 其他线程调用 call_soon(fn)
    - fn 会被排队到 Qt 主线程执行

    任何在回调中抛出的异常：
    - 会被捕获并记录到日志（不让异常终止事件循环）
    """

    _sig_call = Signal(object)  # fn: Callable[[], None]

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._sig_call.connect(self._on_call)

    def call_soon(self, fn: Callable[[], None]) -> None:
        if fn is None:
            return
        # 任意线程都可以发这个信号
        self._sig_call.emit(fn)

    @Slot(object)
    def _on_call(self, fn: Callable[[], None]) -> None:
        try:
            fn()
        except Exception:
            # 记录异常，但不让 Qt 事件循环崩溃
            log.exception("QtDispatcher call failed")