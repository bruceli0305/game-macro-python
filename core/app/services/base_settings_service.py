from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from core.app.uow import ProfileUnitOfWork
from core.event_bus import EventBus
from core.event_types import EventType
from core.input.hotkey_strings import to_pynput_hotkey
from core.models.base import BaseFile
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

    Key property:
    - apply_patch() is idempotent: if patch doesn't change model, it will NOT mark dirty.
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

        Conventions:
          - "enter_pick_mode: <msg>"
          - "cancel_pick: <msg>"
          - "hotkeys: <msg>" (conflict etc.)
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

    def _apply_to_basefile(self, b: BaseFile, patch: BaseSettingsPatch) -> None:
        theme = (patch.theme or "").strip()
        if theme == "---" or not theme:
            theme = "darkly"
        b.ui.theme = theme

        b.capture.monitor_policy = (patch.monitor_policy or "primary").strip() or "primary"

        b.hotkeys.enter_pick_mode = (patch.hotkey_enter_pick or "").strip()
        b.hotkeys.cancel_pick = (patch.hotkey_cancel_pick or "").strip()

        av = b.pick.avoidance
        av.mode = (patch.avoid_mode or "hide_main").strip() or "hide_main"
        av.delay_ms = clamp_int(int(patch.avoid_delay_ms), 0, 5000)
        av.preview_follow_cursor = bool(patch.preview_follow)
        av.preview_offset = (int(patch.preview_offset_x), int(patch.preview_offset_y))
        av.preview_anchor = (patch.preview_anchor or "bottom_right").strip() or "bottom_right"

        b.io.auto_save = bool(patch.auto_save)
        b.io.backup_on_save = bool(patch.backup_on_save)

    def apply_patch(self, patch: BaseSettingsPatch) -> bool:
        """
        Apply patch to in-memory model.
        Returns changed(bool). If unchanged, does NOT mark dirty.
        """
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
        """
        Manual save:
        - If patch is unchanged AND base is not dirty -> no-op.
        - If base is already dirty (from previous apply/flush), still commit.
        """
        changed = self.apply_patch(patch)

        # Important: base might already be dirty even if patch matches current model.
        try:
            base_dirty = "base" in self._uow.dirty_parts()
        except Exception:
            base_dirty = False

        if not changed and not base_dirty:
            if self._bus is not None:
                self._bus.post(EventType.STATUS, msg="未检测到更改")
            return

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