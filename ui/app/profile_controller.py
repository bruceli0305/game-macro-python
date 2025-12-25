from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog
from typing import Callable

from core.event_bus import EventBus
from core.event_types import EventType
from core.app.services.profile_service import ProfileService
from core.profiles import ProfileContext
from core.events.payloads import InfoPayload, ErrorPayload

class ProfileController:
    def __init__(
        self,
        *,
        root: tk.Misc,
        bus: EventBus,
        profile_service: ProfileService,
        apply_ctx_to_ui: Callable[[ProfileContext], None],
        refresh_profiles_ui: Callable[[str], None],
        guard_confirm: Callable[[str], bool],
    ) -> None:
        self._root = root
        self._bus = bus
        self._svc = profile_service
        self._apply_ctx_to_ui = apply_ctx_to_ui
        self._refresh_profiles_ui = refresh_profiles_ui
        self._guard_confirm = guard_confirm

    def on_select(self, name: str, current_ctx: ProfileContext) -> None:
        if not self._guard_confirm("切换 Profile"):
            self._refresh_profiles_ui(current_ctx.profile_name)
            return
        self._bus.post_payload(EventType.PICK_CANCEL_REQUEST, None)
        try:
            res = self._svc.open_and_bind(name)
            self._apply_ctx_to_ui(res.ctx)
            self._bus.post_payload(EventType.INFO, InfoPayload(msg=f"已切换 profile: {res.ctx.profile_name}"))
        except Exception as e:
            self._bus.post_payload(
                EventType.ERROR,
                ErrorPayload(msg="打开 profile 失败", detail=str(e)),
            )
            self._refresh_profiles_ui(current_ctx.profile_name)

    def on_action(self, action: str, current_ctx: ProfileContext) -> None:
        if action in ("new", "copy", "rename", "delete"):
            if not self._guard_confirm("Profile 操作"):
                self._refresh_profiles_ui(current_ctx.profile_name)
                return

        cur = current_ctx.profile_name

        if action == "new":
            name = simpledialog.askstring("新建 Profile", "请输入 Profile 名称：", parent=self._root)
            if not name:
                return
            try:
                res = self._svc.create_and_bind(name)
                self._apply_ctx_to_ui(res.ctx)
                self._bus.post_payload(EventType.INFO, InfoPayload(msg=f"已新建 profile: {res.ctx.profile_name}"))
            except Exception as e:
                self._bus.post_payload(
                    EventType.ERROR,
                    ErrorPayload(msg="新建失败", detail=str(e)),
                )
            return

        if action == "copy":
            name = simpledialog.askstring("复制 Profile", f"复制 {cur} 到新名称：", parent=self._root)
            if not name:
                return
            try:
                res = self._svc.copy_and_bind(cur, name)
                self._apply_ctx_to_ui(res.ctx)
                self._bus.post_payload(EventType.INFO, InfoPayload(msg=f"已复制 profile 并切换到: {res.ctx.profile_name}"))
            except Exception as e:
                self._bus.post_payload(
                    EventType.ERROR,
                    ErrorPayload(msg="复制失败", detail=str(e)),
                )
            return

        if action == "rename":
            name = simpledialog.askstring("重命名 Profile", f"{cur} 重命名为：", parent=self._root)
            if not name:
                return
            try:
                res = self._svc.rename_and_bind(cur, name)
                self._apply_ctx_to_ui(res.ctx)
                self._bus.post_payload(EventType.INFO, InfoPayload(msg=f"已重命名并切换到: {res.ctx.profile_name}"))
            except Exception as e:
                self._bus.post_payload(
                    EventType.ERROR,
                    ErrorPayload(msg="重命名失败", detail=str(e)),
                )
            return

        if action == "delete":
            if cur == "Default":
                messagebox.showinfo("提示", "不建议删除 Default（可重命名/另建）。", parent=self._root)
                return
            ok = messagebox.askyesno(
                "删除 Profile",
                f"确认删除 profile：{cur} ？\n\n（将删除该目录下所有 JSON）",
                parent=self._root,
            )
            if not ok:
                return
            try:
                res = self._svc.delete_and_bind_fallback(cur)
                self._apply_ctx_to_ui(res.ctx)
                self._bus.post_payload(EventType.INFO, InfoPayload(msg=f"已删除 profile 并切换到 {res.ctx.profile_name}"))
            except Exception as e:
                self._bus.post_payload(
                    EventType.ERROR,
                    ErrorPayload(msg="删除失败", detail=str(e)),
                )
            return