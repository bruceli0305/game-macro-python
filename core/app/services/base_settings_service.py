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

    # 执行策略：启停热键 + 技能间默认间隔
    exec_toggle_enabled: bool
    exec_toggle_hotkey: str
    exec_skill_gap_ms: int


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
        _ = clamp_int(int(patch.mouse_avoid_offset_y), 0, 500)
        _ = clamp_int(int(patch.mouse_avoid_settle_ms), 0, 500)

        # 施法完成模式 / 容差校验
        mode = (patch.cast_mode or "timer").strip().lower()
        if mode not in ("timer", "bar"):
            raise ValueError("施法完成模式只能是 'timer' 或 'bar'")
        _ = clamp_int(int(patch.cast_bar_tolerance), 0, 255)

        # 执行启停热键校验
        if patch.exec_toggle_enabled:
            hk_exec = normalize(patch.exec_toggle_hotkey)
            if hk_exec:
                _mods2, main2 = parse(hk_exec)
                if main2 == "esc":
                    raise ValueError("执行启停热键不能使用 Esc")
            # hk_exec 允许为空（视为未配置），后面会按 enabled & hotkey 决定是否生效

        # 技能间默认间隔
        _ = clamp_int(int(patch.exec_skill_gap_ms), 0, 10**6)

    def _apply_to_basefile(self, b: BaseFile, patch: BaseSettingsPatch) -> None:
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
        b.pick.mouse_avoid_offset_y = clamp_int(int(patch.mouse_avoid_offset_y), 0, 500)
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

        # 执行策略：启停热键
        if patch.exec_toggle_enabled:
            hk_exec = normalize(patch.exec_toggle_hotkey)
        else:
            hk_exec = ""
        enabled = bool(patch.exec_toggle_enabled and hk_exec)
        b.exec.enabled = enabled
        b.exec.toggle_hotkey = hk_exec if enabled else ""

        # 执行策略：技能间默认间隔
        gap = clamp_int(int(patch.exec_skill_gap_ms), 0, 10**6)
        b.exec.default_skill_gap_ms = gap
        
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
        """
        应用 patch 并保存到磁盘。
        """
        changed = self.apply_patch(patch)

        base_dirty = "base" in self._session.dirty_parts()
        if not changed and not base_dirty:
            return False

        backup = bool(getattr(self.profile.base.io, "backup_on_save", True))
        self._session.commit(parts={"base"}, backup=backup, touch_meta=True)
        self._notify_dirty()
        return True

    def reload_cmd(self) -> None:
        """
        从 profile.json 重新加载 base 部分。
        """
        try:
            self._session.reload_parts({"base"})
        except Exception:
            # 出错时交给上层 UI 处理，这里只尽量保证不崩
            pass
        self._notify_dirty()