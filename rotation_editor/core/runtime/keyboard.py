# rotation_editor/core/runtime/keyboard.py
from __future__ import annotations

from typing import Protocol, Optional, Dict
import logging

from pynput import keyboard

log = logging.getLogger(__name__)


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


# -----------------------------
# HID DLL KeySender（QMK Raw HID）
# -----------------------------

class HidDllKeySender:
    """
    基于 C++ DLL (InitDevice / CloseDevice / SendKeyOp) 的 KeySender 实现。

    - 构造时加载 DLL，调用 InitDevice；
    - send_key("a") -> SendKeyOp(1, HID_CODE_A), SendKeyOp(2, HID_CODE_A)
    - HID 键码表使用标准 USB HID Usage ID（QMK 通常也是用这个）。

    DLL 查找策略（dll_path 可为绝对或相对路径）：
    - 若为绝对路径且存在，直接使用；
    - 若为相对路径，则依次尝试：
        1) 当前工作目录下；
        2) exe 目录（打包后，sys.executable 所在目录） + 相对路径；
        3) 项目根目录（从本文件往上若干级） + 相对路径；
        4) 上述各目录下的 "assets/lib/KeyDispenserDLL.dll" 作为兜底。

    日志策略：
    - 加载 DLL / InitDevice 成功：INFO 级别；
    - DLL 加载失败 / 缺少导出 / InitDevice 返回非 0：ERROR 级别；
    - SendKeyOp 返回非 0：WARNING 级别。
    """

    def __init__(self, dll_path: str = "assets/lib/KeyDispenserDLL.dll") -> None:
        self._dll_path = dll_path
        self._dll = None
        self._init = None
        self._close = None
        self._send = None

        self._load_dll()

    def _resolve_dll_path(self, dll_path: str) -> str:
        from pathlib import Path
        import sys
        import os

        default_rel = Path("assets") / "lib" / "KeyDispenserDLL.dll"
        raw_path = Path(dll_path) if dll_path else default_rel

        # 绝对路径且存在
        if raw_path.is_absolute() and raw_path.is_file():
            return str(raw_path)

        # 相对当前工作目录
        if raw_path.is_file():
            return str(raw_path.resolve())

        candidates = []

        # exe 目录
        try:
            exe_dir = Path(sys.executable).resolve().parent
            candidates.append(exe_dir / raw_path)
            candidates.append(exe_dir / default_rel)
        except Exception:
            pass

        # 项目根目录（向上多走几级，适配当前目录结构）
        try:
            here = Path(__file__).resolve()
            # parents[0] = 当前文件，parents[1] = runtime, parents[2] = core, parents[3] = rotation_editor, parents[4] = project_root
            proj_root = here.parents[4]
            candidates.append(proj_root / raw_path)
            candidates.append(proj_root / default_rel)
        except Exception:
            pass

        # 当前工作目录
        try:
            cwd = Path(os.getcwd()).resolve()
            candidates.append(cwd / raw_path)
            candidates.append(cwd / default_rel)
        except Exception:
            pass

        for c in candidates:
            try:
                if c.is_file():
                    return str(c)
            except Exception:
                continue

        # 找不到就返回原字符串，让 WinDLL 尝试（也会记日志）
        return str(raw_path)

    def _load_dll(self) -> None:
        import ctypes
        import os

        if os.name != "nt":
            raise RuntimeError("HidDllKeySender only supports Windows (os.name == 'nt')")

        dll_full_path = self._resolve_dll_path(self._dll_path)
        log.info("HidDllKeySender: 尝试从路径加载 HID DLL: %s", dll_full_path)

        try:
            dll = ctypes.WinDLL(dll_full_path)
        except OSError as e:
            log.error("HidDllKeySender: 加载 HID DLL 失败: %s (%s)", dll_full_path, e)
            raise RuntimeError(f"Failed to load HID DLL: {dll_full_path} ({e})") from e

        self._dll = dll

        # InitDevice
        try:
            init_func = dll.InitDevice
        except AttributeError as e:
            log.error("HidDllKeySender: HID DLL 缺少 InitDevice 导出函数")
            raise RuntimeError("HID DLL missing InitDevice export") from e
        init_func.restype = ctypes.c_int

        # CloseDevice
        try:
            close_func = dll.CloseDevice
        except AttributeError as e:
            log.error("HidDllKeySender: HID DLL 缺少 CloseDevice 导出函数")
            raise RuntimeError("HID DLL missing CloseDevice export") from e
        close_func.restype = ctypes.c_int

        # SendKeyOp
        try:
            send_func = dll.SendKeyOp
        except AttributeError as e:
            log.error("HidDllKeySender: HID DLL 缺少 SendKeyOp 导出函数")
            raise RuntimeError("HID DLL missing SendKeyOp export") from e
        send_func.argtypes = [ctypes.c_ubyte, ctypes.c_ubyte]
        send_func.restype = ctypes.c_int

        self._init = init_func
        self._close = close_func
        self._send = send_func

        # 初始化设备
        res = self._init()
        if res != 0:
            log.error("HidDllKeySender: InitDevice 返回错误代码 %d (DLL=%s)", res, dll_full_path)
            raise RuntimeError(f"InitDevice failed with code {res}")

        log.info("HidDllKeySender: HID DLL 加载并初始化成功: %s", dll_full_path)

    def __del__(self) -> None:
        try:
            if self._close is not None:
                self._close()
                log.info("HidDllKeySender: CloseDevice 已调用")
        except Exception:
            # 析构期不要抛异常
            pass

    # --- HID 键码映射 ---

    _HID_KEYCODES: Dict[str, int] = {
        # 字母（USB HID Usage Table）
        "a": 0x04,
        "b": 0x05,
        "c": 0x06,
        "d": 0x07,
        "e": 0x08,
        "f": 0x09,
        "g": 0x0A,
        "h": 0x0B,
        "i": 0x0C,
        "j": 0x0D,
        "k": 0x0E,
        "l": 0x0F,
        "m": 0x10,
        "n": 0x11,
        "o": 0x12,
        "p": 0x13,
        "q": 0x14,
        "r": 0x15,
        "s": 0x16,
        "t": 0x17,
        "u": 0x18,
        "v": 0x19,
        "w": 0x1A,
        "x": 0x1B,
        "y": 0x1C,
        "z": 0x1D,
        # 数字
        "1": 0x1E,
        "2": 0x1F,
        "3": 0x20,
        "4": 0x21,
        "5": 0x22,
        "6": 0x23,
        "7": 0x24,
        "8": 0x25,
        "9": 0x26,
        "0": 0x27,
        # 常用功能键
        "enter": 0x28,
        "esc": 0x29,
        "escape": 0x29,
        "space": 0x2C,
        " ": 0x2C,
        # F1..F12
        "f1": 0x3A,
        "f2": 0x3B,
        "f3": 0x3C,
        "f4": 0x3D,
        "f5": 0x3E,
        "f6": 0x3F,
        "f7": 0x40,
        "f8": 0x41,
        "f9": 0x42,
        "f10": 0x43,
        "f11": 0x44,
        "f12": 0x45,
    }

    def _key_to_hid(self, key: str) -> Optional[int]:
        ks = (key or "").strip().lower()
        if not ks:
            return None
        return self._HID_KEYCODES.get(ks)

    def send_key(self, key: str) -> None:
        """
        发送一次“按下+松开”：
        - op=1 按下
        - op=2 松开
        """
        if self._send is None:
            return
        code = self._key_to_hid(key)
        if code is None:
            # 当前未映射的键直接忽略（不抛异常）
            log.warning("HidDllKeySender: 未映射的键 '%s'，忽略本次发键", key)
            return
        try:
            # 按下
            r1 = self._send(1, code)
            if r1 != 0:
                log.warning("HidDllKeySender: SendKeyOp(op=1,key=%d) 返回错误码 %d", code, r1)
                return
            # 松开
            r2 = self._send(2, code)
            if r2 != 0:
                log.warning("HidDllKeySender: SendKeyOp(op=2,key=%d) 返回错误码 %d", code, r2)
        except Exception as e:
            log.warning("HidDllKeySender: 调用 SendKeyOp 时出现异常: %s", e)
            return