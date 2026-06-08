# File: core/input/hotkey.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Set, Tuple

from pynput import keyboard

MOD_ORDER = ("ctrl", "alt", "shift", "cmd")

MOD_KEYS = {
    keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r,
    keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r,
    keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r,
    keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r,
}

MOD_NAME = {
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

SPECIAL_NAME = {
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


def normalize(s: str) -> str:
    s = (s or "").strip().lower()
    s = s.replace(" ", "")
    s = s.replace("-", "+")
    s = s.replace("_", "+")
    while "++" in s:
        s = s.replace("++", "+")
    return s.strip("+")


def parse(s: str) -> Tuple[Set[str], str]:
    s = normalize(s)
    if not s:
        raise ValueError("hotkey: empty")

    parts = [p for p in s.split("+") if p]
    mods: Set[str] = set()
    main: Optional[str] = None

    for p in parts:
        if p in MOD_ORDER:
            mods.add(p)
        else:
            main = p

    if main is None:
        raise ValueError("hotkey: missing main key")
    return mods, main


def compose(mods: Set[str], main: str) -> str:
    ordered = [m for m in MOD_ORDER if m in mods]
    return "+".join([*ordered, main])


def key_to_name(k) -> Optional[str]:
    # KeyCode: a-z/0-9/...
    if isinstance(k, keyboard.KeyCode):
        try:
            ch = getattr(k, "char", None)
            if isinstance(ch, str) and ch:
                return ch.lower()
        except Exception:
            return None
        return None

    if k in SPECIAL_NAME:
        return SPECIAL_NAME[k]

    # function keys: f1..f24 etc
    try:
        name = getattr(k, "name", None)
        if isinstance(name, str) and name:
            return name.lower()
    except Exception:
        pass
    return None