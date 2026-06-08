from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional


DiagnosticLevel = Literal["error", "warning", "info"]


@dataclass(frozen=True)
class Diagnostic:
    """
    统一诊断信息：
    - code: 机器可读错误码（便于 UI 分类/过滤）
    - level: error/warning/info
    - path: 指向 expr JSON 的路径（建议用类 JSON Pointer 的风格）
    - message: 人类可读简述
    - detail: 可选详细信息
    """
    code: str
    level: DiagnosticLevel
    path: str
    message: str
    detail: str = ""

    def is_error(self) -> bool:
        return self.level == "error"


def pjoin(base: str, frag: str) -> str:
    """
    拼接 path 片段（非常轻量，避免引入 JSON Pointer 复杂度）。
    约定：
    - base: "$" 或 "$.a[0].b"
    - frag: ".x" 或 "[3]"
    """
    if not base:
        base = "$"
    if not frag:
        return base
    return f"{base}{frag}"


def err(code: str, path: str, message: str, detail: str = "") -> Diagnostic:
    return Diagnostic(code=code, level="error", path=path or "$", message=message, detail=detail)


def warn(code: str, path: str, message: str, detail: str = "") -> Diagnostic:
    return Diagnostic(code=code, level="warning", path=path or "$", message=message, detail=detail)


def info(code: str, path: str, message: str, detail: str = "") -> Diagnostic:
    return Diagnostic(code=code, level="info", path=path or "$", message=message, detail=detail)