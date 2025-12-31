# qtui/pick/preview_window.py
from __future__ import annotations

from typing import Callable

from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QMouseEvent

from qtui.widgets.color_swatch import ColorSwatch


class PickPreviewWindow(QDialog):
    """
    无边框置顶的小预览窗：
    - 显示当前坐标和颜色
    - 左键/右键点击会调用 on_cancel 回调
    """

    def __init__(self, *, on_cancel: Callable[[], None], parent=None) -> None:
        super().__init__(parent)

        self._on_cancel = on_cancel

        # 窗口标志：无边框、置顶、小工具窗
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self._lbl_xy = QLabel("x=0  y=0", self)
        layout.addWidget(self._lbl_xy)

        self._swatch = ColorSwatch(self, width=84, height=22)
        layout.addWidget(self._swatch)

        self.resize(180, 74)
        # 初始隐藏
        self.hide()

    # 封装尺寸，方便计算
    @property
    def size_tuple(self) -> tuple[int, int]:
        sz = self.size()
        return sz.width(), sz.height()

    def show_preview(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    def hide_preview(self) -> None:
        self.hide()

    def update_preview(self, *, x: int, y: int, r: int, g: int, b: int) -> None:
        self._lbl_xy.setText(f"x={int(x)}  y={int(y)}")
        self._swatch.set_rgb(int(r), int(g), int(b))

    def move_to(self, x: int, y: int) -> None:
        self.move(QPoint(int(x), int(y)))

    # 点击取消
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() in (Qt.LeftButton, Qt.RightButton):
            try:
                self._on_cancel()
            except Exception:
                pass
        super().mousePressEvent(event)