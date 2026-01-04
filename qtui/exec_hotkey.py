from __future__ import annotations

import threading
from typing import Callable, Optional, Set

from pynput import keyboard

from core.profiles import ProfileContext
from core.input.hotkey import normalize, parse, key_to_name  # 复用已有工具
from qtui.dispatcher import QtDispatcher


class ExecHotkeyController:
    """
    执行启停热键控制器（全局）：

    - 从 ProfileContext.base.exec 读取：
        * enabled: 是否启用
        * toggle_hotkey: 字符串热键，如 "f9" / "ctrl+f9" / "alt+shift+1"
      解析规则复用 core.input.hotkey.normalize/parse。

    - 使用 pynput.keyboard.Listener 全局监听键盘：
        * on_press / on_release 中维护当前按下的修饰键集合 + 主键；
        * 当当前按键状态与配置的 (mods, main) 完全一致时，
          通过 QtDispatcher 在 UI 线程调用 toggle_cb()。

    注意：
    - 允许组合键（ctrl+f9 等），也允许只有主键（"f9"）。
    - Esc 禁止作为主键（在 BaseSettingsService.validate_patch 中已校验）。
    """

    def __init__(
        self,
        *,
        dispatcher: QtDispatcher,
        get_ctx: Callable[[], ProfileContext],
        toggle_cb: Callable[[], None],
    ) -> None:
        self._dispatcher = dispatcher
        self._get_ctx = get_ctx
        self._toggle_cb = toggle_cb

        self._listener: Optional[keyboard.Listener] = None
        self._lock = threading.Lock()

        # 配置解析后的结果
        self._enabled: bool = False
        self._mods_cfg: Set[str] = set()
        self._main_cfg: str = ""

        # 当前按下状态
        self._pressed_mods: Set[str] = set()
        self._pressed_main: Optional[str] = None
        self._fired: bool = False  # 当前组合按住期间是否已经触发过一次，防止连发

        self.refresh_from_ctx()
        self._start_listener()

    # ---------- 公共 API ----------

    def refresh_from_ctx(self) -> None:
        """
        从当前 ProfileContext.base.exec 刷新配置：
        - enabled & toggle_hotkey。
        """
        enabled = False
        mods_cfg: Set[str] = set()
        main_cfg = ""

        try:
            ctx = self._get_ctx()
        except Exception:
            ctx = None

        if ctx is not None:
            try:
                ex = ctx.base.exec
            except Exception:
                ex = None

            if ex is not None:
                try:
                    enabled_flag = bool(getattr(ex, "enabled", False))
                    hk_raw = (getattr(ex, "toggle_hotkey", "") or "").strip()
                    if enabled_flag and hk_raw:
                        # 规范化并解析，例如 "ctrl+f9"
                        hk_norm = normalize(hk_raw)
                        mods, main = parse(hk_norm)
                        enabled = True
                        mods_cfg = set(mods)
                        main_cfg = main
                    else:
                        enabled = False
                except Exception:
                    enabled = False
                    mods_cfg = set()
                    main_cfg = ""

        with self._lock:
            self._enabled = enabled
            self._mods_cfg = mods_cfg
            self._main_cfg = main_cfg
            # 配置变化后重置当前按键状态
            self._pressed_mods.clear()
            self._pressed_main = None
            self._fired = False

    def close(self) -> None:
        """
        停止监听器；关闭应用时调用。
        """
        lst = self._listener
        self._listener = None
        if lst is not None:
            try:
                lst.stop()
            except Exception:
                pass

    # ---------- 内部：pynput 监听 ----------

    def _start_listener(self) -> None:
        if self._listener is not None:
            return

        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.daemon = True
        self._listener.start()

    def _on_press(self, key) -> None:
        name = key_to_name(key)
        if not name:
            return

        with self._lock:
            if not self._enabled or not self._main_cfg:
                return

            # 更新当前按键状态
            # 修饰键：ctrl / alt / shift / cmd
            if name in ("ctrl", "alt", "shift", "cmd"):
                self._pressed_mods.add(name)
            else:
                # 普通键或功能键：作为主键
                self._pressed_main = name

            # 比较是否与配置匹配
            if self._pressed_main == self._main_cfg and self._pressed_mods == self._mods_cfg:
                if not self._fired:
                    self._fired = True
                    # 在 Qt 主线程执行 toggle_cb
                    self._dispatcher.call_soon(self._toggle_cb)

    def _on_release(self, key) -> None:
        name = key_to_name(key)
        if not name:
            return

        with self._lock:
            if name in ("ctrl", "alt", "shift", "cmd"):
                self._pressed_mods.discard(name)
            else:
                if self._pressed_main == name:
                    self._pressed_main = None

            # 组合完全释放后，允许下一次触发
            if not self._pressed_mods and self._pressed_main is None:
                self._fired = False