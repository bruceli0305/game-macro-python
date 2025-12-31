# qtui/icons.py
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QPalette
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication, QStyle


def _tint_svg(path: Path, color: QColor, size: int = 16) -> Optional[QIcon]:
    """
    将给定 SVG 渲染为指定颜色的单色 QIcon。
    SVG 本身可以是黑色线条或填充。
    """
    if not path.exists():
        return None

    app = QApplication.instance()
    if app is None:
        return None

    renderer = QSvgRenderer(str(path))
    if not renderer.isValid():
        return None

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    p = QPainter(pixmap)
    renderer.render(p)
    p.setCompositionMode(QPainter.CompositionMode_SourceIn)
    p.fillRect(pixmap.rect(), color)
    p.end()

    return QIcon(pixmap)


def load_icon(
    name: str,
    style: Optional[QStyle] = None,
    fallback: Optional[QStyle.StandardPixmap] = None,
    size: int = 16,
) -> QIcon:
    """
    按当前主题颜色加载一个着色后的 SVG 图标：

    - 从 assets/icons/{name}.svg 读取
    - 使用当前调色板的 WindowText 颜色着色
    - 如果文件不存在或失败，则返回 Qt 标准图标（fallback），或空图标
    """
    base = Path("assets/icons") / f"{name}.svg"
    app = QApplication.instance()

    if app is not None and base.exists():
        pal = app.palette()
        color = pal.color(QPalette.WindowText)
        icon = _tint_svg(base, color, size=size)
        if icon is not None:
            return icon

    if style is not None and fallback is not None:
        return style.standardIcon(fallback)

    return QIcon()