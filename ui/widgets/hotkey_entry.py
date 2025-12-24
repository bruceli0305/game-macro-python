from __future__ import annotations

import tkinter as tk
import ttkbootstrap as tb
from ttkbootstrap.constants import LEFT, X

from pynput import keyboard


_MOD_KEYS = {
    keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r,
    keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r,
    keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r,
    keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r,
}

_MOD_NAME = {
    keyboard.Key.shift: "shift",
    keyboard.Key.shift_l: "shift",
    keyboard.Key.shift_r: "shift",
    keyboard.Key.ctrl: "ctrl",
    keyboard.Key.ctrl_l: "ctrl",
    keyboard.Key.ctrl_r: "ctrl",
    keyboard.Key.alt: "alt",
    keyboard.Key.alt_l: "alt",
    keyboard.Key.alt_r: "alt",
    keyboard.Key.cmd: "cmd",
    keyboard.Key.cmd_l: "cmd",
    keyboard.Key.cmd_r: "cmd",
}

_SPECIAL_NAME = {
    keyboard.Key.esc: "esc",
    keyboard.Key.enter: "enter",
    keyboard.Key.tab: "tab",
    keyboard.Key.space: "space",
    keyboard.Key.backspace: "backspace",
    keyboard.Key.delete: "delete",
    keyboard.Key.insert: "insert",
    keyboard.Key.home: "home",
    keyboard.Key.end: "end",
    keyboard.Key.page_up: "pageup",
    keyboard.Key.page_down: "pagedown",
    keyboard.Key.up: "up",
    keyboard.Key.down: "down",
    keyboard.Key.left: "left",
    keyboard.Key.right: "right",
}


def _key_to_name(k) -> str | None:
    # modifiers handled separately
    if isinstance(k, keyboard.KeyCode):
        if k.char:
            return k.char.lower()
        return None

    if k in _SPECIAL_NAME:
        return _SPECIAL_NAME[k]

    # function keys
    try:
        # e.g. keyboard.Key.f1
        name = getattr(k, "name", None)
        if isinstance(name, str) and name.startswith("f") and name[1:].isdigit():
            return name.lower()
    except Exception:
        pass

    # fallback
    try:
        name = getattr(k, "name", None)
        if isinstance(name, str) and name:
            return name.lower()
    except Exception:
        pass
    return None


class HotkeyEntry(tb.Frame):
    """
    Hotkey recorder:
    - shows a readonly entry bound to a StringVar (e.g. 'ctrl+alt+p')
    - '录制' starts a pynput keyboard.Listener
    - press modifiers + a key to finish
    - Esc cancels recording
    """

    def __init__(
        self,
        master: tk.Misc,
        *,
        textvariable: tk.StringVar,
        width: int = 18,
    ) -> None:
        super().__init__(master)

        self._var = textvariable
        self._listener: keyboard.Listener | None = None
        self._recording = False

        self._mods: set[str] = set()
        self._timeout_after_id: str | None = None

        self._entry = tb.Entry(self, textvariable=self._var, width=width, state="readonly")
        self._entry.pack(side=LEFT, fill=X, expand=True)

        self._btn = tb.Button(self, text="录制", command=self.start_record, width=6)
        self._btn.pack(side=LEFT, padx=(8, 0))

    def start_record(self) -> None:
        if self._recording:
            return

        self._recording = True
        self._mods.clear()
        self._btn.configure(text="录制中")

        # timeout: 5s auto-cancel
        self._set_timeout(5000)

        # start listener (background thread inside pynput)
        self._listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        try:
            self._listener.start()
        except Exception:
            self._stop_recording_ui(cancel=True)

    def _set_timeout(self, ms: int) -> None:
        if self._timeout_after_id is not None:
            try:
                self.after_cancel(self._timeout_after_id)
            except Exception:
                pass
            self._timeout_after_id = None

        self._timeout_after_id = self.after(ms, lambda: self._stop_recording_ui(cancel=True))

    def _clear_timeout(self) -> None:
        if self._timeout_after_id is not None:
            try:
                self.after_cancel(self._timeout_after_id)
            except Exception:
                pass
            self._timeout_after_id = None

    def _stop_listener(self) -> None:
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None

    def _stop_recording_ui(self, *, cancel: bool) -> None:
        # must run on Tk thread
        self._clear_timeout()
        self._stop_listener()
        self._recording = False
        self._mods.clear()
        self._btn.configure(text="录制")
        # cancel=True 不改原值

    def _finish(self, hotkey: str) -> None:
        # Tk thread update
        def _apply():
            self._var.set(hotkey)
            self._stop_recording_ui(cancel=False)

        self.after(0, _apply)

    # ----- pynput callbacks (NOT Tk thread) -----

    def _on_press(self, k) -> None:
        try:
            if not self._recording:
                return

            # Esc cancels recording
            if k == keyboard.Key.esc:
                self.after(0, lambda: self._stop_recording_ui(cancel=True))
                return

            # modifiers
            if k in _MOD_KEYS:
                self._mods.add(_MOD_NAME.get(k, ""))
                return

            key_name = _key_to_name(k)
            if not key_name:
                return

            mods = [m for m in ("ctrl", "alt", "shift", "cmd") if m in self._mods]
            parts = mods + [key_name]
            hotkey = "+".join([p for p in parts if p])

            self._finish(hotkey)

        except Exception:
            # swallow all exceptions in listener callback
            pass

    def _on_release(self, k) -> None:
        try:
            if not self._recording:
                return
            if k in _MOD_KEYS:
                name = _MOD_NAME.get(k, "")
                if name and name in self._mods:
                    self._mods.remove(name)
        except Exception:
            pass