# qtui/profile_controller.py
from __future__ import annotations

import logging
from typing import Callable

from PySide6.QtWidgets import QMainWindow, QInputDialog, QMessageBox

from core.app.services.profile_service import ProfileService
from core.profiles import ProfileContext
from qtui.notify import UiNotify

log = logging.getLogger(__name__)


class ProfileController:
    """
    负责调用 ProfileService 完成：
    - 打开 / 切换 profile
    - 新建 / 复制 / 重命名 / 删除

    UI 交互用 QInputDialog / QMessageBox 完成。
    未保存变更通过 guard_confirm 回调处理。
    """

    def __init__(
        self,
        *,
        window: QMainWindow,
        profile_service: ProfileService,
        apply_ctx_to_ui: Callable[[ProfileContext], None],
        refresh_profiles_ui: Callable[[str | None], None],
        guard_confirm: Callable[[str, ProfileContext], bool],
        notify: UiNotify,
    ) -> None:
        self._win = window
        self._svc = profile_service
        self._apply_ctx_to_ui = apply_ctx_to_ui
        self._refresh_profiles_ui = refresh_profiles_ui
        self._guard_confirm = guard_confirm
        self._notify = notify

    # ---------- 切换 ----------

    def on_select(self, name: str, current_ctx: ProfileContext) -> None:
        # 先检查未保存变更
        if not self._guard_confirm("切换 Profile", current_ctx):
            # 用户取消时，恢复下拉选中
            self._refresh_profiles_ui(current_ctx.profile_name)
            return

        try:
            res = self._svc.open_and_bind(name)
            self._apply_ctx_to_ui(res.ctx)
            self._notify.info(f"已切换 profile: {res.ctx.profile_name}")
        except Exception as e:
            log.exception("profile switch failed (target=%s)", name)
            self._notify.error("打开 profile 失败", detail=str(e))
            self._refresh_profiles_ui(current_ctx.profile_name)

    # ---------- 操作 ----------

    def on_action(self, action: str, current_ctx: ProfileContext) -> None:
        # 只有真正会改变 Profile 列表的操作才需要守卫
        if action in ("new", "copy", "rename", "delete"):
            if not self._guard_confirm("Profile 操作", current_ctx):
                self._refresh_profiles_ui(current_ctx.profile_name)
                return

        cur = current_ctx.profile_name

        if action == "new":
            name, ok = QInputDialog.getText(self._win, "新建 Profile", "请输入 Profile 名称：")
            if not ok or not name:
                return
            try:
                res = self._svc.create_and_bind(name)
                self._apply_ctx_to_ui(res.ctx)
                self._notify.info(f"已新建 profile: {res.ctx.profile_name}")
            except Exception as e:
                log.exception("profile create failed (name=%s)", name)
                self._notify.error("新建失败", detail=str(e))
            return

        if action == "copy":
            name, ok = QInputDialog.getText(self._win, "复制 Profile", f"复制 {cur} 到新名称：")
            if not ok or not name:
                return
            try:
                res = self._svc.copy_and_bind(cur, name)
                self._apply_ctx_to_ui(res.ctx)
                self._notify.info(f"已复制 profile 并切换到: {res.ctx.profile_name}")
            except Exception as e:
                log.exception("profile copy failed (src=%s dst=%s)", cur, name)
                self._notify.error("复制失败", detail=str(e))
            return

        if action == "rename":
            name, ok = QInputDialog.getText(self._win, "重命名 Profile", f"{cur} 重命名为：")
            if not ok or not name:
                return
            try:
                res = self._svc.rename_and_bind(cur, name)
                self._apply_ctx_to_ui(res.ctx)
                self._notify.info(f"已重命名并切换到: {res.ctx.profile_name}")
            except Exception as e:
                log.exception("profile rename failed (old=%s new=%s)", cur, name)
                self._notify.error("重命名失败", detail=str(e))
            return

        if action == "delete":
            if cur == "Default":
                QMessageBox.information(
                    self._win,
                    "提示",
                    "不建议删除 Default（可重命名/另建）。",
                )
                return

            ok = QMessageBox.question(
                self._win,
                "删除 Profile",
                f"确认删除 profile：{cur} ？\n\n（将删除该目录下所有 JSON）",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if ok != QMessageBox.Yes:
                return

            try:
                res = self._svc.delete_and_bind_fallback(cur)
                self._apply_ctx_to_ui(res.ctx)
                self._notify.info(f"已删除 profile 并切换到 {res.ctx.profile_name}")
            except Exception as e:
                log.exception("profile delete failed (name=%s)", cur)
                self._notify.error("删除失败", detail=str(e))
            return