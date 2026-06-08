from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QTabBar

from rotation_editor.core.models import Mode


class ModeTabBar(QTabBar):
    """
    只负责根据 Mode 列表管理 Tab 显示：
    - set_modes(modes, current_id)
    - current_mode_id()
    - modeChanged(mode_id) 信号
    """

    modeChanged = Signal(str)  # 当前模式 ID（空串表示“无选中”）

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMovable(False)
        self.setTabsClosable(False)
        # 不填充整行，按内容宽度 + 最小宽度
        self.setExpanding(False)
        self.setUsesScrollButtons(True)
        self.setStyleSheet("QTabBar::tab { min-width: 80px; }")

        self.currentChanged.connect(self._on_current_changed)

    # ---------- 外部 API ----------

    def set_modes(self, modes: List[Mode], current_id: Optional[str]) -> None:
        """
        用给定的 modes 重建标签，并尽量选中 current_id（若不存在则选第一个）。
        """
        self.blockSignals(True)
        try:
            while self.count() > 0:
                self.removeTab(0)

            cur = (current_id or "").strip()
            cur_index = -1

            for i, m in enumerate(modes or []):
                mid = m.id or ""
                text = m.name or "(未命名)"
                idx = self.addTab(text)
                self.setTabData(idx, mid)
                if mid == cur:
                    cur_index = idx

            if self.count() > 0:
                if cur_index < 0:
                    cur_index = 0
                self.setCurrentIndex(cur_index)
            # 如果没有模式，就保持无选中状态
        finally:
            self.blockSignals(False)

    def current_mode_id(self) -> str:
        """
        返回当前标签对应的模式 ID，若无选中则返回空串。
        """
        idx = self.currentIndex()
        if idx < 0:
            return ""
        data = self.tabData(idx)
        return data if isinstance(data, str) else ""

    # ---------- 内部 ----------

    def _on_current_changed(self, index: int) -> None:
        if index < 0:
            self.modeChanged.emit("")
            return
        data = self.tabData(index)
        mid = data if isinstance(data, str) else ""
        self.modeChanged.emit(mid)