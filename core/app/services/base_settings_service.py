# File: core/app/services/base_settings_service.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from core.app.uow import ProfileUnitOfWork
from core.event_bus import EventBus
from core.event_types import EventType
from core.events.payloads import (
    ConfigSavedPayload,
    InfoPayload,
    StatusPayload,
    ThemeChangePayload,
)
from core.models.base import BaseFile
from core.models.common import clamp_int


@dataclass(frozen=True)
class BaseSettingsPatch:
    theme: str
    monitor_policy: str

    # Step 5: remove global pick hotkeys; add confirm hotkey for pick
    pick_confirm_hotkey: str

    avoid_mode: str
    avoid_delay_ms: int
    preview_follow: bool
    preview_offset_x: int
    preview_offset_y: int
    preview_anchor: str

    # Step 5: mouse avoidance for hover highlight problem
    mouse_avoid: bool
    mouse_avoid_offset_y: int
    mouse_avoid_settle_ms: int

    auto_save: bool
    backup_on_save: bool


_MODS = {"ctrl", "alt", "shift", "cmd"}


def _normalize_hotkey_string(s: str) -> str:
    """
    Normalize hotkey string to the same style HotkeyEntry records:
    - lower-case
    - '+' separated
    - strip spaces
    - collapse duplicated '+'
    Examples:
      ' Ctrl + Alt + F8 ' -> 'ctrl+alt+f8'
      'esc' -> 'esc'
    """
    s = (s or "").strip().lower()
    s = s.replace(" ", "")
    s = s.replace("-", "+")
    s = s.replace("_", "+")
    while "++" in s:
        s = s.replace("++", "+")
    return s.strip("+")


def _parse_hotkey(s: str) -> tuple[set[str], str]:
    """
    Parse normalized hotkey string into (mods, main_key).
    main_key is the last non-mod part. Raises ValueError if invalid.
    """
    s = _normalize_hotkey_string(s)
    if not s:
        raise ValueError("confirm_hotkey: 热键不能为空")

    parts = [p for p in s.split("+") if p]
    if not parts:
        raise ValueError("confirm_hotkey: 热键不能为空")

    mods: set[str] = set()
    main: str | None = None

    for p in parts:
        if p in _MODS:
            mods.add(p)
        else:
            main = p

    if main is None:
        # only modifiers
        raise ValueError("confirm_hotkey: 热键必须包含一个主键（不能只有 ctrl/alt/shift/cmd）")

    return mods, main


class BaseSettingsService:
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
        hk = _normalize_hotkey_string(patch.pick_confirm_hotkey)

        mods, main = _parse_hotkey(hk)

        # Esc is fixed cancel; any hotkey with main key 'esc' will conflict
        if main == "esc":
            raise ValueError("confirm_hotkey: 确认热键不能使用 Esc（Esc 固定为取消）")

        # Optional: disallow empty/non-sense key name
        if not main:
            raise ValueError("confirm_hotkey: 热键格式错误")

        # sanity: avoid_delay_ms etc
        _ = clamp_int(int(patch.avoid_delay_ms), 0, 5000)
        _ = clamp_int(int(patch.mouse_avoid_offset_y), 0, 500)
        _ = clamp_int(int(patch.mouse_avoid_settle_ms), 0, 500)

    def _apply_to_basefile(self, b: BaseFile, patch: BaseSettingsPatch) -> None:
        theme = (patch.theme or "").strip()
        if theme == "---" or not theme:
            theme = "darkly"
        b.ui.theme = theme

        b.capture.monitor_policy = (patch.monitor_policy or "primary").strip() or "primary"

        # pick avoidance (keep existing nesting: b.pick.avoidance.*)
        av = b.pick.avoidance
        av.mode = (patch.avoid_mode or "hide_main").strip() or "hide_main"
        av.delay_ms = clamp_int(int(patch.avoid_delay_ms), 0, 5000)
        av.preview_follow_cursor = bool(patch.preview_follow)
        av.preview_offset = (int(patch.preview_offset_x), int(patch.preview_offset_y))
        av.preview_anchor = (patch.preview_anchor or "bottom_right").strip() or "bottom_right"

        # Step 5: confirm hotkey + mouse avoidance
        b.pick.confirm_hotkey = _normalize_hotkey_string(patch.pick_confirm_hotkey) or "f8"
        b.pick.mouse_avoid = bool(patch.mouse_avoid)
        b.pick.mouse_avoid_offset_y = clamp_int(int(patch.mouse_avoid_offset_y), 0, 500)
        b.pick.mouse_avoid_settle_ms = clamp_int(int(patch.mouse_avoid_settle_ms), 0, 500)

        # io
        b.io.auto_save = bool(patch.auto_save)
        b.io.backup_on_save = bool(patch.backup_on_save)

    def apply_patch(self, patch: BaseSettingsPatch) -> bool:
        self.validate_patch(patch)

        before = self.ctx.base.to_dict()
        tmp = BaseFile.from_dict(before)
        self._apply_to_basefile(tmp, patch)
        after = tmp.to_dict()

        if after == before:
            return False

        self._apply_to_basefile(self.ctx.base, patch)
        self._uow.mark_dirty("base")
        self._notify_dirty()
        return True

    def save_cmd(self, patch: BaseSettingsPatch) -> None:
        changed = self.apply_patch(patch)

        try:
            base_dirty = "base" in self._uow.dirty_parts()
        except Exception:
            base_dirty = False

        if not changed and not base_dirty:
            if self._bus is not None:
                self._bus.post_payload(EventType.STATUS, StatusPayload(msg="未检测到更改"))
            return

        backup = bool(getattr(self.ctx.base.io, "backup_on_save", True))
        self._uow.commit(parts={"base"}, backup=backup, touch_meta=True)
        self._notify_dirty()

        if self._bus is not None:
            self._bus.post_payload(EventType.UI_THEME_CHANGE, ThemeChangePayload(theme=self.ctx.base.ui.theme))

            self._bus.post_payload(
                EventType.CONFIG_SAVED,
                ConfigSavedPayload(section="base", source="manual_save", saved=True),
            )
            self._bus.post_payload(EventType.INFO, InfoPayload(msg="base.json 已保存"))

    def reload_cmd(self) -> None:
        self.ctx.base = self.ctx.base_repo.load_or_create()

        self._uow.clear_dirty("base")
        self._uow.refresh_snapshot(parts={"base"})
        self._notify_dirty()

        if self._bus is not None:
            self._bus.post_payload(
                EventType.CONFIG_SAVED,
                ConfigSavedPayload(section="base", source="reload", saved=False),
            )
            self._bus.post_payload(EventType.INFO, InfoPayload(msg="已重新加载 base.json"))
            self._bus.post_payload(EventType.UI_THEME_CHANGE, ThemeChangePayload(theme=self.ctx.base.ui.theme))