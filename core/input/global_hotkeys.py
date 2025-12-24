from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Callable

from pynput import keyboard

from core.event_bus import EventBus
from core.input.hotkey_strings import to_pynput_hotkey


@dataclass
class HotkeyConfig:
    enter_pick_mode: str
    cancel_pick: str


class GlobalHotkeyService:
    """
    Global hotkeys (pynput.keyboard.GlobalHotKeys).
    start() 可重复调用：用于运行时重载热键。
    """

    def __init__(self, *, bus: EventBus, config_provider: Callable[[], HotkeyConfig]) -> None:
        self._bus = bus
        self._config_provider = config_provider
        self._listener: Optional[keyboard.GlobalHotKeys] = None

    def start(self) -> None:
        self.stop()

        cfg = self._config_provider()

        try:
            hk_enter = to_pynput_hotkey(cfg.enter_pick_mode)
            hk_cancel = to_pynput_hotkey(cfg.cancel_pick)
        except Exception as e:
            self._bus.post("ERROR", msg=f"热键格式错误: {e}")
            return

        # 冲突检测：相同组合会导致映射覆盖/行为异常
        if hk_enter == hk_cancel:
            self._bus.post("ERROR", msg="热键冲突：进入取色 与 取消取色 不能相同")
            return

        mapping = {
            hk_enter: lambda: self._bus.post("PICK_START_LAST"),
            hk_cancel: lambda: self._bus.post("PICK_CANCEL_REQUEST"),
        }

        try:
            self._listener = keyboard.GlobalHotKeys(mapping)
            self._listener.start()
            self._bus.post("INFO", msg=f"全局热键已启用: enter={hk_enter}, cancel={hk_cancel}")
        except Exception as e:
            self._listener = None
            self._bus.post("ERROR", msg=f"全局热键启动失败: {e}")

    def stop(self) -> None:
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None