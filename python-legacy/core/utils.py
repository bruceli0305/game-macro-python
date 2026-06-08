from __future__ import annotations

"""
core.utils — 跨模块共享的工具函数。
"""

import re

_ILLEGAL_FS_CHARS = r'<>:"/\\|?*'
_ILLEGAL_FS_RE = re.compile(f"[{re.escape(_ILLEGAL_FS_CHARS)}]")


def sanitize_profile_name(name: str) -> str:
    """Windows 友好的目录名清洗。

    - 去除首尾空白
    - 替换非法文件系统字符为下划线
    - 合并连续空白
    - 截断至 64 字符
    - 空名称回退为 "Default"
    """
    name = (name or "").strip()
    if not name:
        return "Default"
    name = _ILLEGAL_FS_RE.sub("_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:64] if len(name) > 64 else name
