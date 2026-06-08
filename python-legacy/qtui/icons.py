from __future__ import annotations

from pathlib import Path
from typing import Optional
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QPalette
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication, QStyle


def resource_path(relative: str) -> Path:
    """
    返回打包/源码环境下统一可用的资源路径：
    - 打包为 exe (PyInstaller) 时：
        * onefile: sys._MEIPASS 指向临时解包目录
        * onedir : __file__ 在 dist/... 下面，父目录就是 exe 目录
    - 源码运行时：
        * __file__ 在项目的 qtui/ 目录下，父目录即项目根，assets/ 在此之下
    """
    base: Path
    if hasattr(sys, "_MEIPASS"):
        # PyInstaller onefile 模式：所有资源解包在 _MEIPASS 下
        base = Path(getattr(sys, "_MEIPASS") or ".").resolve()
    else:
        # 源码/onedir 模式：qtui/ 的父目录作为项目根/运行根
        base = Path(__file__).resolve().parents[1]
    return base / relative


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

    - 从 assets/icons/{name}.svg 读取（使用 resource_path 解析）
    - 使用当前调色板的 WindowText 颜色着色
    - 如果文件不存在或失败，则返回 Qt 标准图标（fallback），或空图标
    """
    app = QApplication.instance()

    if app is not None:
        svg_path = resource_path(f"assets/icons/{name}.svg")
        if svg_path.exists():
            pal = app.palette()
            color = pal.color(QPalette.WindowText)
            icon = _tint_svg(svg_path, color, size=size)
            if icon is not None:
                return icon

    if style is not None and fallback is not None:
        return style.standardIcon(fallback)

    return QIcon()