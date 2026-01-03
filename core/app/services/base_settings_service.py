# core/app/services/base_settings_service.py
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


class BaseSettingsService:
    """
    基础配置（base.json / Profile.base）编辑服务：

    - 不负责 UI 提示，只做验证 / 应用 / 提交 / 重新加载 + 标记 dirty
    - 通过 ProfileSession 管理脏状态与持久化
    """

    def __init__(
        self,
        *,
        session: ProfileSession,
        notify_dirty: Optional[Callable[[], None]] = None,
    ) -> None:
        self._session = session
        self._notify_dirty = notify_dirty or (lambda: None)

    # ---------- 便捷属性 ----------

    @property
    def ctx(self):
        return self._session.ctx

    @property
    def profile(self):
        return self._session.profile

    # ---------- 验证 ----------

    def validate_patch(self, patch: BaseSettingsPatch) -> None:
        hk = normalize(patch.pick_confirm_hotkey)
        _mods, main = parse(hk)

        if main == "esc":
            raise ValueError("confirm_hotkey: 确认热键不能使用 Esc（Esc 固定为取消）")

        _ = clamp_int(int(patch.avoid_delay_ms), 0, 5000)
        _ = clamp_int(int(patch.mouse_avoid_offset_y), 0, 500)
        _ = clamp_int(int(patch.mouse_avoid_settle_ms), 0, 500)

    # ---------- 应用到 BaseFile ----------

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

    # ---------- 应用 & 标记脏 ----------

    def apply_patch(self, patch: BaseSettingsPatch) -> bool:
        """
        仅应用到内存模型，并标记 dirty，不立即写盘。
        返回值：是否实际有变更。
        """
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

    # ---------- 保存 ----------

    def save_cmd(self, patch: BaseSettingsPatch) -> bool:
        """
        应用 patch 并保存到磁盘。
        返回：
        - True : 有变更或之前已有未保存变更，并成功保存
        - False: 没有任何需要保存的变更
        """
        changed = self.apply_patch(patch)

        base_dirty = "base" in self._session.dirty_parts()
        if not changed and not base_dirty:
            return False

        backup = bool(getattr(self.profile.base.io, "backup_on_save", True))
        self._session.commit(parts={"base"}, backup=backup, touch_meta=True)
        self._notify_dirty()
        return True

    # ---------- 重新加载 ----------

    def reload_cmd(self) -> None:
        """
        从磁盘重新加载 base.json / Profile.base：
        - 直接调用旧的 BaseRepo.load_or_create
        - 清除 base 部分 dirty 标记
        - 刷新 snapshot
        """
        # 仍通过旧的 repo 读取；后续会统一走 ProfileRepository
        self.profile.base = self.ctx.base_repo.load_or_create()  # type: ignore[attr-defined]

        try:
            self._session.clear_dirty("base")
        except Exception:
            pass
        try:
            self._session.refresh_snapshot(parts={"base"})
        except Exception:
            pass
        self._notify_dirty()