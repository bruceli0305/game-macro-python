# qtui/theme.py
from __future__ import annotations

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPalette, QColor


DARK_THEMES = ["darkly", "superhero", "cyborg", "solar", "vapor"]
LIGHT_THEMES = [
    "flatly", "litera", "cosmo", "journal", "minty",
    "lumen", "pulse", "sandstone", "simplex", "yeti",
]


def _apply_dark_palette(app: QApplication) -> None:
    palette = QPalette()

    palette.setColor(QPalette.Window, QColor(53, 53, 53))
    palette.setColor(QPalette.WindowText, QColor(220, 220, 220))
    palette.setColor(QPalette.Base, QColor(42, 42, 42))
    palette.setColor(QPalette.AlternateBase, QColor(66, 66, 66))
    palette.setColor(QPalette.ToolTipBase, QColor(255, 255, 220))
    palette.setColor(QPalette.ToolTipText, QColor(0, 0, 0))
    palette.setColor(QPalette.Text, QColor(220, 220, 220))
    palette.setColor(QPalette.Button, QColor(53, 53, 53))
    palette.setColor(QPalette.ButtonText, QColor(220, 220, 220))
    palette.setColor(QPalette.BrightText, QColor(255, 0, 0))
    palette.setColor(QPalette.Link, QColor(42, 130, 218))
    palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))

    app.setPalette(palette)


def _apply_light_palette(app: QApplication) -> None:
    app.setPalette(app.style().standardPalette())


def apply_theme(app: QApplication, theme_name: str) -> None:
    """
    根据 base.ui.theme 里的字符串，切换暗/亮主题：
    - DARK_THEMES 列表内的一律按“暗色”处理
    - 其他走“亮色”主题
    """
    name = (theme_name or "").strip().lower()
    app.setStyle("Fusion")  # 先统一 Fusion 风格，方便调色板生效

    if name in [t.lower() for t in DARK_THEMES]:
        _apply_dark_palette(app)
    else:
        _apply_light_palette(app)