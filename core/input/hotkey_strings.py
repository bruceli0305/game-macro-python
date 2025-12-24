from __future__ import annotations

import re

# 将 "ctrl+alt+p" 转为 pynput GlobalHotKeys 需要的 "<ctrl>+<alt>+p" 格式
# 参考 pynput GlobalHotKeys 的组合键字符串格式（<ctrl>、<alt> 等）。:
# https://pynput.readthedocs.io/en/latest/keyboard.html#monitoring-the-keyboard


_MOD_ALIASES = {
    "ctrl": "<ctrl>",
    "control": "<ctrl>",
    "alt": "<alt>",
    "shift": "<shift>",
    "cmd": "<cmd>",
    "command": "<cmd>",
    "win": "<cmd>",      # Windows 键在 pynput 里常用 <cmd>
    "super": "<cmd>",
}

_SPECIAL_KEYS = {
    "esc": "<esc>",
    "escape": "<esc>",
    "enter": "<enter>",
    "return": "<enter>",
    "tab": "<tab>",
    "space": "<space>",
    "backspace": "<backspace>",
    "delete": "<delete>",
    "del": "<delete>",
    "insert": "<insert>",
    "home": "<home>",
    "end": "<end>",
    "pageup": "<page_up>",
    "pagedown": "<page_down>",
    "up": "<up>",
    "down": "<down>",
    "left": "<left>",
    "right": "<right>",
}

_FKEY_RE = re.compile(r"^f([1-9]|1[0-2])$")  # f1..f12


def normalize_hotkey_string(s: str) -> str:
    """
    Normalize to 'ctrl+alt+p' lower-case style (still plain string).
    """
    s = (s or "").strip()
    s = s.replace(" ", "")
    s = s.replace("-", "+")
    s = s.replace("_", "+")
    s = s.lower()
    # collapse multiple plus
    while "++" in s:
        s = s.replace("++", "+")
    return s.strip("+")


def to_pynput_hotkey(s: str) -> str:
    """
    Convert 'ctrl+alt+p' into pynput GlobalHotKeys format '<ctrl>+<alt>+p'.
    Accepts single key like 'esc' => '<esc>'.
    """
    s = normalize_hotkey_string(s)
    if not s:
        raise ValueError("empty hotkey")

    parts = [p for p in s.split("+") if p]
    out_parts: list[str] = []

    for p in parts:
        if p in _MOD_ALIASES:
            out_parts.append(_MOD_ALIASES[p])
            continue

        if p in _SPECIAL_KEYS:
            out_parts.append(_SPECIAL_KEYS[p])
            continue

        m = _FKEY_RE.match(p)
        if m:
            out_parts.append(f"<f{m.group(1)}>")
            continue

        # 普通字符键：a-z 0-9 等，pynput 允许直接写
        if len(p) == 1:
            out_parts.append(p)
            continue

        # 其它：尝试包裹成 <xxx>
        out_parts.append(f"<{p}>")

    # 去重但保持顺序（尤其 ctrl/alt/shift）
    seen = set()
    dedup: list[str] = []
    for x in out_parts:
        if x not in seen:
            seen.add(x)
            dedup.append(x)

    return "+".join(dedup)