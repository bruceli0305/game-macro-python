# rotation_editor/core/runtime/keyboard.py
from __future__ import annotations

from typing import Protocol

from pynput import keyboard


class KeySender(Protocol):
    """
    抽象的键盘发送接口：
    - 目前只定义 send_key(key: str)
    - 便于后续替换为其他输入库或做单元测试 mock
    """

    def send_key(self, key: str) -> None: ...


class PynputKeySender:
    """
    基于 pynput 的简单键盘发送实现：

    - 目前支持：
        * 单字符键："a" / "b" / "1" 等
        * F 键："f1".."f12"
    - 组合键、特殊键可在后续扩展
    """

    def __init__(self) -> None:
        self._ctl = keyboard.Controller()

    def send_key(self, key: str) -> None:
        ks = (key or "").strip().lower()
        if not ks:
            return

        # F1..F12
        if ks.startswith("f") and ks[1:].isdigit():
            try:
                n = int(ks[1:])
            except ValueError:
                return
            try:
                k = getattr(keyboard.Key, f"f{n}")
            except AttributeError:
                return
            self._ctl.press(k)
            self._ctl.release(k)
            return

        # 单字符
        if len(ks) == 1:
            self._ctl.press(ks)
            self._ctl.release(ks)
            return

        # 其他未处理情况：暂时忽略
        return