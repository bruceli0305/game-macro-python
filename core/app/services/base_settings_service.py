# File: core/app/services/base_settings_service.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from core.store.app_store import AppStore
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


class BaseSettingsService:
    """
    Step 3-3-3-3-3:
    - 不再发 EventBus 的 INFO/STATUS/ERROR/UI_THEME_CHANGE/CONFIG_SAVED
    - 只负责：validate/apply/commit/reload + 标记 dirty
    - UI 提示与主题应用由页面/UiNotify负责
    """

    def __init__(
        self,
        *,
        store: AppStore,
        notify_dirty: Optional[Callable[[], None]] = None,
    ) -> None:
        self._store = store
        self._notify_dirty = notify_dirty or (lambda: None)

    @property
    def ctx(self):
        return self._store.ctx

    def validate_patch(self, patch: BaseSettingsPatch) -> None:
        hk = normalize(patch.pick_confirm_hotkey)
        _mods, main = parse(hk)

        if main == "esc":
            raise ValueError("confirm_hotkey: 确认热键不能使用 Esc（Esc 固定为取消）")

        _ = clamp_int(int(patch.avoid_delay_ms), 0, 5000)
        _ = clamp_int(int(patch.mouse_avoid_offset_y), 0, 500)
        _ = clamp_int(int(patch.mouse_avoid_settle_ms), 0, 500)

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

    def apply_patch(self, patch: BaseSettingsPatch) -> bool:
        self.validate_patch(patch)

        before = self.ctx.base.to_dict()
        tmp = BaseFile.from_dict(before)
        self._apply_to_basefile(tmp, patch)
        after = tmp.to_dict()

        if after == before:
            return False

        self._apply_to_basefile(self.ctx.base, patch)
        self._store.mark_dirty("base")
        self._notify_dirty()
        return True

    def save_cmd(self, patch: BaseSettingsPatch) -> bool:
        """
        Returns True if saved; False if nothing to save.
        """
        changed = self.apply_patch(patch)

        base_dirty = "base" in self._store.dirty_parts()
        if not changed and not base_dirty:
            return False

        backup = bool(getattr(self.ctx.base.io, "backup_on_save", True))
        self._store.commit(parts={"base"}, backup=backup, touch_meta=True)
        self._notify_dirty()
        return True

    def reload_cmd(self) -> None:
        self.ctx.base = self.ctx.base_repo.load_or_create()

        try:
            self._store.clear_dirty("base")
        except Exception:
            pass
        try:
            self._store.refresh_snapshot(parts={"base"})
        except Exception:
            pass
        self._notify_dirty()