from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from core.app.session import ProfileSession
from core.models.base import BaseFile
from core.models.common import clamp_int
from core.input.hotkey import normalize, parse


@dataclass(frozen=True)
class BaseSettingsPatch:
    theme: str
    monitor_policy: str

    pick_confirm_hotkey: str

    avoid_mode: str
    avoid_delay_ms: int
    preview_follow: bool
    preview_offset_x: int
    preview_offset_y: int
    preview_anchor: str

    mouse_avoid: bool
    mouse_avoid_offset_y: int
    mouse_avoid_settle_ms: int

    auto_save: bool
    backup_on_save: bool

    # 施法完成策略
    cast_mode: str              # "timer" | "bar"
    cast_bar_point_id: str
    cast_bar_tolerance: int
    cast_bar_poll_interval_ms: int
    cast_bar_max_wait_factor: float

    # 执行策略：启停热键 + 技能间隔
    exec_toggle_enabled: bool
    exec_toggle_hotkey: str
    exec_skill_gap_ms: int

    # 执行策略：轮询/开始信号/重试（新增）
    exec_poll_not_ready_ms: int
    exec_start_signal_mode: str     # "pixel" | "cast_bar" | "none"
    exec_start_timeout_ms: int
    exec_start_poll_ms: int
    exec_max_retries: int
    exec_retry_gap_ms: int

    # 执行策略：发键模式（pynput / hid）+ HID DLL 路径
    exec_key_sender_mode: str       # "pynput" | "hid"
    exec_hid_dll_path: str


class BaseSettingsService:
    """
    基础配置（BaseFile）编辑服务：
    - 通过 ProfileSession 管理脏状态 / 提交 / 重载
    """

    def __init__(
        self,
        *,
        session: ProfileSession,
        notify_dirty: Optional[Callable[[], None]] = None,
    ) -> None:
        self._session = session
        self._notify_dirty = notify_dirty or (lambda: None)

    @property
    def ctx(self):
        return self._session.ctx

    @property
    def profile(self):
        return self._session.profile

    def validate_patch(self, patch: BaseSettingsPatch) -> None:
        # 取色确认热键
        hk = normalize(patch.pick_confirm_hotkey)
        _mods, main = parse(hk)
        if main == "esc":
            raise ValueError("confirm_hotkey: 确认热键不能使用 Esc（Esc 固定为取消）")

        _ = clamp_int(int(patch.avoid_delay_ms), 0, 5000)
        # 鼠标避让 Y 偏移允许负数：向上为负，向下为正
        _ = clamp_int(int(patch.mouse_avoid_offset_y), -500, 500)
        _ = clamp_int(int(patch.mouse_avoid_settle_ms), 0, 500)

        # 施法完成模式 / 容差校验
        mode = (patch.cast_mode or "timer").strip().lower()
        if mode not in ("timer", "bar"):
            raise ValueError("施法完成模式只能是 'timer' 或 'bar'")
        _ = clamp_int(int(patch.cast_bar_tolerance), 0, 255)

        _ = clamp_int(int(patch.cast_bar_poll_interval_ms), 10, 1000)
        try:
            f = float(patch.cast_bar_max_wait_factor)
        except Exception:
            raise ValueError("施法条最长等待倍数必须是数字")
        if f <= 0:
            raise ValueError("施法条最长等待倍数必须大于 0")

        # 执行启停热键校验
        if patch.exec_toggle_enabled:
            hk_exec = normalize(patch.exec_toggle_hotkey)
            if hk_exec:
                _mods2, main2 = parse(hk_exec)
                if main2 == "esc":
                    raise ValueError("执行启停热键不能使用 Esc")

        _ = clamp_int(int(patch.exec_skill_gap_ms), 0, 10**6)

        # 新增：轮询/开始信号/重试
        _ = clamp_int(int(patch.exec_poll_not_ready_ms), 10, 10**6)

        smode = (patch.exec_start_signal_mode or "pixel").strip().lower()
        if smode not in ("pixel", "cast_bar", "none"):
            raise ValueError("开始施法信号模式只能是 'pixel' / 'cast_bar' / 'none'")

        _ = clamp_int(int(patch.exec_start_timeout_ms), 1, 10**6)
        _ = clamp_int(int(patch.exec_start_poll_ms), 5, 10**6)
        _ = clamp_int(int(patch.exec_max_retries), 0, 1000)
        _ = clamp_int(int(patch.exec_retry_gap_ms), 0, 10**6)

        # 如果 start_signal_mode=cast_bar，必须配置 cast_bar_point_id
        if smode == "cast_bar":
            if not (patch.cast_bar_point_id or "").strip():
                raise ValueError("开始施法信号=施法条变化(cast_bar) 时，必须设置“施法条点位 ID”")

        # 发键模式校验
        ksm = (patch.exec_key_sender_mode or "pynput").strip().lower()
        if ksm not in ("pynput", "hid"):
            raise ValueError("发键模式只能是 'pynput' 或 'hid'")

        hid_path = (patch.exec_hid_dll_path or "").strip()
        if ksm == "hid":
            if not hid_path:
                raise ValueError("发键模式为 HID 时，必须设置 HID DLL 路径")

            # 运行期检测：尝试加载 DLL 并 InitDevice，一切错误只记日志，不阻止保存
            try:
                from rotation_editor.core.runtime.keyboard import HidDllKeySender
                try:
                    sender = HidDllKeySender(dll_path=hid_path)
                except Exception as e:
                    log = logging.getLogger(__name__)
                    log.warning("保存基础配置时，HID DLL 初始化失败：%s (%s)", hid_path, e)
                else:
                    # 立即释放，避免占用设备
                    del sender
            except Exception:
                # 导入失败等，最多记个 debug，不影响保存
                log = logging.getLogger(__name__)
                log.debug("validate_patch: 无法导入 HidDllKeySender 进行 HID 检测", exc_info=True)

    def _apply_to_basefile(self, b: BaseFile, patch: BaseSettingsPatch) -> None:
        # UI & capture
        theme = (patch.theme or "").strip()
        if theme == "---" or not theme:
            theme = "darkly"
        b.ui.theme = theme

        b.capture.monitor_policy = (patch.monitor_policy or "primary").strip() or "primary"

        av = b.pick.avoidance
        av.mode = (patch.avoid_mode or "hide_main").strip() or "hide_main"
        av.delay_ms = clamp_int(int(patch.avoid_delay_ms), 0, 5000)
        av.preview_follow_cursor = bool(patch.preview_follow)
        av.preview_offset = (int(patch.preview_offset_x), int(patch.preview_offset_y))
        av.preview_anchor = (patch.preview_anchor or "bottom_right").strip() or "bottom_right"

        b.pick.confirm_hotkey = normalize(patch.pick_confirm_hotkey) or "f8"
        b.pick.mouse_avoid = bool(patch.mouse_avoid)
        # 这里允许 -500..500
        b.pick.mouse_avoid_offset_y = clamp_int(int(patch.mouse_avoid_offset_y), -500, 500)
        b.pick.mouse_avoid_settle_ms = clamp_int(int(patch.mouse_avoid_settle_ms), 0, 500)

        b.io.auto_save = bool(patch.auto_save)
        b.io.backup_on_save = bool(patch.backup_on_save)

        # 施法完成策略
        cmode = (patch.cast_mode or "timer").strip().lower()
        if cmode not in ("timer", "bar"):
            cmode = "timer"
        b.cast_bar.mode = cmode
        b.cast_bar.point_id = (patch.cast_bar_point_id or "").strip()
        b.cast_bar.tolerance = clamp_int(int(patch.cast_bar_tolerance), 0, 255)
        b.cast_bar.poll_interval_ms = clamp_int(int(patch.cast_bar_poll_interval_ms), 10, 1000)

        try:
            factor = float(patch.cast_bar_max_wait_factor)
        except Exception:
            factor = 1.5
        if factor < 0.1:
            factor = 0.1
        if factor > 10.0:
            factor = 10.0
        b.cast_bar.max_wait_factor = factor

        # 执行策略：启停热键
        if patch.exec_toggle_enabled:
            hk_exec = normalize(patch.exec_toggle_hotkey)
        else:
            hk_exec = ""
        enabled = bool(patch.exec_toggle_enabled and hk_exec)
        b.exec.enabled = enabled
        b.exec.toggle_hotkey = hk_exec if enabled else ""

        # 执行策略：技能间隔
        b.exec.default_skill_gap_ms = clamp_int(int(patch.exec_skill_gap_ms), 0, 10**6)

        # 轮询/开始信号/重试
        b.exec.poll_not_ready_ms = clamp_int(int(patch.exec_poll_not_ready_ms), 10, 10**6)
        smode = (patch.exec_start_signal_mode or "pixel").strip().lower()
        if smode not in ("pixel", "cast_bar", "none"):
            smode = "pixel"
        b.exec.start_signal_mode = smode
        b.exec.start_timeout_ms = clamp_int(int(patch.exec_start_timeout_ms), 1, 10**6)
        b.exec.start_poll_ms = clamp_int(int(patch.exec_start_poll_ms), 5, 10**6)
        b.exec.max_retries = clamp_int(int(patch.exec_max_retries), 0, 1000)
        b.exec.retry_gap_ms = clamp_int(int(patch.exec_retry_gap_ms), 0, 10**6)

        # 发键模式
        ksm = (patch.exec_key_sender_mode or "pynput").strip().lower()
        if ksm not in ("pynput", "hid"):
            ksm = "pynput"
        b.exec.key_sender_mode = ksm

        path = (patch.exec_hid_dll_path or "").strip()
        if not path:
            path = "assets/lib/KeyDispenserDLL.dll"
        b.exec.hid_dll_path = path

    def apply_patch(self, patch: BaseSettingsPatch) -> bool:
        self.validate_patch(patch)

        before = self.profile.base.to_dict()
        tmp = BaseFile.from_dict(before)
        self._apply_to_basefile(tmp, patch)
        after = tmp.to_dict()

        if after == before:
            return False

        self._apply_to_basefile(self.profile.base, patch)
        self._session.mark_dirty("base")
        self._notify_dirty()
        return True

    def save_cmd(self, patch: BaseSettingsPatch) -> bool:
        changed = self.apply_patch(patch)

        base_dirty = "base" in self._session.dirty_parts()
        if not changed and not base_dirty:
            return False

        backup = bool(getattr(self.profile.base.io, "backup_on_save", True))
        self._session.commit(parts={"base"}, backup=backup, touch_meta=True)
        self._notify_dirty()
        return True

    def reload_cmd(self) -> None:
        try:
            self._session.reload_parts({"base"})
        except Exception:
            pass
        self._notify_dirty()