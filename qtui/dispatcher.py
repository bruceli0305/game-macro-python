# qtui/dispatcher.py
from __future__ import annotations

from typing import Callable
from PySide6.QtCore import QObject, Signal, Slot


class QtDispatcher(QObject):
    """
    简单的 UI 线程调度器：
    - 其他线程调用 call_soon(fn)
    - fn 会被排队到 Qt 主线程执行
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
            # 不让异常终止事件循环
            pass