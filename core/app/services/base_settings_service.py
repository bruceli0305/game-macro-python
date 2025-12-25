from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from core.app.uow import ProfileUnitOfWork
from core.event_bus import EventBus
from core.event_types import EventType
from core.input.hotkey_strings import to_pynput_hotkey
from core.models.common import clamp_int


@dataclass(frozen=True)
class BaseSettingsPatch:
    theme: str
    monitor_policy: str

    hotkey_enter_pick: str
    hotkey_cancel_pick: str

    avoid_mode: str
    avoid_delay_ms: int
    preview_follow: bool
    preview_offset_x: int
    preview_offset_y: int
    preview_anchor: str

    auto_save: bool
    backup_on_save: bool


class BaseSettingsService:
    """
    Application service for base.json settings.
    - validate input (hotkeys etc.)
    - apply to model
    - commit via UoW
    - publish UI refresh events (theme/hotkeys/config_saved)
    """

    def __init__(
        self,
        *,
        uow: ProfileUnitOfWork,
        bus: Optional[EventBus] = None,
        notify_dirty: Optional[Callable[[], None]] = None,
    ) -> None:
        self._uow = uow
        self._bus = bus
        self._notify_dirty = notify_dirty or (lambda: None)

    @property
    def ctx(self):
        return self._uow.ctx

    def validate_patch(self, patch: BaseSettingsPatch) -> None:
        """
        Validate patch and raise ValueError with FIELD-PREFIXED messages.

        Error message conventions:
          - "enter_pick_mode: <msg>"
          - "cancel_pick: <msg>"
          - "hotkeys: <msg>" (conflict etc.)
          - "base: <msg>" (generic)
        """
        enter_raw = (patch.hotkey_enter_pick or "").strip()
        cancel_raw = (patch.hotkey_cancel_pick or "").strip()

        if not enter_raw:
            raise ValueError("enter_pick_mode: 热键不能为空")
        if not cancel_raw:
            raise ValueError("cancel_pick: 热键不能为空")

        try:
            enter_pp = to_pynput_hotkey(enter_raw)
        except Exception as e:
            raise ValueError(f"enter_pick_mode: 热键格式错误: {e}") from e

        try:
            cancel_pp = to_pynput_hotkey(cancel_raw)
        except Exception as e:
            raise ValueError(f"cancel_pick: 热键格式错误: {e}") from e

        if enter_pp == cancel_pp:
            raise ValueError("hotkeys: 热键冲突：进入取色 与 取消取色 不能相同")

    def apply_patch(self, patch: BaseSettingsPatch) -> None:
        # validate first
        self.validate_patch(patch)

        b = self.ctx.base

        theme = (patch.theme or "").strip()
        if theme == "---" or not theme:
            theme = "darkly"
        b.ui.theme = theme

        b.capture.monitor_policy = (patch.monitor_policy or "primary").strip() or "primary"

        # hotkeys (already validated)
        b.hotkeys.enter_pick_mode = (patch.hotkey_enter_pick or "").strip()
        b.hotkeys.cancel_pick = (patch.hotkey_cancel_pick or "").strip()

        # avoidance
        av = b.pick.avoidance
        av.mode = (patch.avoid_mode or "hide_main").strip() or "hide_main"
        av.delay_ms = clamp_int(int(patch.avoid_delay_ms), 0, 5000)
        av.preview_follow_cursor = bool(patch.preview_follow)
        av.preview_offset = (int(patch.preview_offset_x), int(patch.preview_offset_y))
        av.preview_anchor = (patch.preview_anchor or "bottom_right").strip() or "bottom_right"

        # io
        b.io.auto_save = bool(patch.auto_save)
        b.io.backup_on_save = bool(patch.backup_on_save)

        self._uow.mark_dirty("base")
        self._notify_dirty()

    def save_cmd(self, patch: BaseSettingsPatch) -> None:
        """
        Apply + commit base settings (manual save).
        Always touch meta.
        """
        self.apply_patch(patch)

        backup = bool(getattr(self.ctx.base.io, "backup_on_save", True))
        self._uow.commit(parts={"base"}, backup=backup, touch_meta=True)
        self._notify_dirty()

        if self._bus is not None:
            self._bus.post(EventType.UI_THEME_CHANGE, theme=self.ctx.base.ui.theme)
            self._bus.post(EventType.HOTKEYS_CHANGED)
            self._bus.post(EventType.CONFIG_SAVED, section="base", source="manual_save", saved=True)
            self._bus.post(EventType.INFO, msg="base.json 已保存")

    def reload_cmd(self) -> None:
        """
        Reload base.json from disk and reset dirty state for base.
        """
        self.ctx.base = self.ctx.base_repo.load_or_create()

        self._uow.clear_dirty("base")
        self._uow.refresh_snapshot(parts={"base"})
        self._notify_dirty()

        if self._bus is not None:
            self._bus.post(EventType.CONFIG_SAVED, section="base", source="reload", saved=False)
            self._bus.post(EventType.INFO, msg="已重新加载 base.json")
            self._bus.post(EventType.UI_THEME_CHANGE, theme=self.ctx.base.ui.theme)
            self._bus.post(EventType.HOTKEYS_CHANGED)