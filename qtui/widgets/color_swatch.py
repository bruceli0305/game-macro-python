# qtui/widgets/color_swatch.py
from __future__ import annotations

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QFrame
from PySide6.QtGui import QColor, QPalette
from PySide6.QtCore import Qt


class ColorSwatch(QWidget):
    """
    简单颜色预览控件：
    - 左侧一块有背景色的矩形
    - 右侧显示 #RRGGBB 文本
    """

    def __init__(self, parent: QWidget | None = None, *, width: int = 64, height: int = 24) -> None:
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._frame = QFrame(self)
        self._frame.setFixedSize(width, height)
        self._frame.setFrameShape(QFrame.Box)
        self._frame.setFrameShadow(QFrame.Sunken)

        layout.addWidget(self._frame)

        self._label = QLabel("#000000", self)
        self._label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addWidget(self._label)

        self.set_rgb(0, 0, 0)

    @staticmethod
    def _rgb_to_qcolor(r: int, g: int, b: int) -> QColor:
        r = max(0, min(255, int(r)))
        g = max(0, min(255, int(g)))
        b = max(0, min(255, int(b)))
        return QColor(r, g, b)

    def set_rgb(self, r: int, g: int, b: int) -> None:
        color = self._rgb_to_qcolor(r, g, b)
        pal = self._frame.palette()
        pal.setColor(QPalette.Window, color)
        self._frame.setAutoFillBackground(True)
        self._frame.setPalette(pal)

        hx = f"#{color.red():02X}{color.green():02X}{color.blue():02X}"
        self._label.setText(hx)

    def set_hex(self, hx: str) -> None:
        s = (hx or "").strip()
        if not s.startswith("#"):
            s = "#" + s
        if len(s) != 7:
            return
        try:
            color = QColor(s)
            if not color.isValid():
                return
        except Exception:
            return

        pal = self._frame.palette()
        pal.setColor(QPalette.Window, color)
        self._frame.setAutoFillBackground(True)
        self._frame.setPalette(pal)
        self._label.setText(s.upper())

    def get_hex(self) -> str:
        return self._label.text()