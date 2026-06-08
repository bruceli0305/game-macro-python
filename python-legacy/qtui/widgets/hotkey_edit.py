# qtui/widgets/hotkey_edit.py
from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QKeySequenceEdit
from PySide6.QtGui import QKeySequence
from PySide6.QtCore import Signal

from core.input.hotkey import normalize


class HotkeyEdit(QWidget):
    """
    热键录制控件（Qt 版）：
    - 使用 QKeySequenceEdit 捕获组合键
    - 将 Qt 的 QKeySequence 转为项目内部的 'ctrl+alt+p' 风格字符串
    - 支持 set_error/clear_error 显示验证错误
    """

    hotkeyChanged = Signal(str)

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        initial: str = "",
    ) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._edit = QKeySequenceEdit(self)
        layout.addWidget(self._edit)

        self._lbl_err = QLabel("", self)
        self._lbl_err.setStyleSheet("color: red;")
        layout.addWidget(self._lbl_err)

        self._edit.keySequenceChanged.connect(self._on_seq_changed)

        # 初始值
        if initial:
            self.set_hotkey(initial)

    # ---------- 公共 API ----------

    def set_hotkey(self, s: str) -> None:
        """
        设置当前热键显示；s 使用内部字符串格式，如 'ctrl+alt+p'。
        """
        s = (s or "").strip()
        if not s:
            self._edit.clear()
            return

        # 简单将 'ctrl+alt+p' 还原成 Qt 能理解的字符串（区分大小写不重要）
        txt = s.replace("+", "+").upper()
        seq = QKeySequence(txt)
        self._edit.setKeySequence(seq)

    def get_hotkey(self) -> str:
        """
        获取当前热键，返回内部字符串格式，如 'ctrl+alt+p'。
        若为空则返回空字符串。
        """
        seq = self._edit.keySequence()
        if seq.isEmpty():
            return ""
        return self._seq_to_internal(seq)

    def set_error(self, msg: Optional[str]) -> None:
        """
        显示/清除错误信息，并高亮 QKeySequenceEdit。
        """
        m = (msg or "").strip()
        self._lbl_err.setText(m)
        if m:
            self._edit.setStyleSheet("border: 1px solid red;")
        else:
            self._edit.setStyleSheet("")

    def clear_error(self) -> None:
        self.set_error(None)

    # ---------- 内部 ----------

    def _on_seq_changed(self, seq: QKeySequence) -> None:
        s = ""
        if not seq.isEmpty():
            s = self._seq_to_internal(seq)
        self.hotkeyChanged.emit(s)

    @staticmethod
    def _seq_to_internal(seq: QKeySequence) -> str:
        """
        将 Qt 的 QKeySequence 转为内部 'ctrl+alt+p' 风格字符串，
        然后用 core.input.hotkey.normalize 进一步标准化。
        """
        # PortableText 形式，如 "Ctrl+Alt+P"
        txt = seq.toString(QKeySequence.PortableText)
        s = (txt or "").strip()

        # 简单规范化
        s = s.replace(" ", "")   # 移除空格
        s = s.replace("Ctrl", "ctrl")
        s = s.replace("Alt", "alt")
        s = s.replace("Shift", "shift")
        # Qt 里 Win/Meta/Command 相关的名字，这里统一归并到 cmd
        s = s.replace("Meta", "cmd")
        s = s.replace("Win", "cmd")
        s = s.replace("Command", "cmd")
        s = s.lower()

        # 再走一次项目的 normalize 逻辑（去重/连字符等）
        return normalize(s)