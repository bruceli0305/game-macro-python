from __future__ import annotations

import logging
import tkinter as tk
from tkinter import messagebox

from core.app.services.app_services import AppServices

log = logging.getLogger(__name__)


class UnsavedChangesGuard:
    def __init__(self, *, root: tk.Misc, services: AppServices, pages, backup_provider) -> None:
        self._root = root
        self._services = services
        self._pages = pages
        self._backup_provider = backup_provider  # callable -> bool

    def _dirty_names(self) -> list[str]:
        try:
            parts = self._services.uow.dirty_parts()
        except Exception:
            log.exception("read uow dirty_parts failed")
            return []
        mapping = {
            "base": "基础配置",
            "skills": "技能配置",
            "points": "取色点位配置",
            "meta": "Profile 元信息",
        }
        out: list[str] = []
        for p in ["base", "skills", "points", "meta"]:
            if p in parts:
                out.append(mapping.get(p, p))
        return out

    def confirm(self, *, action_name: str, ctx) -> bool:
        """
        Returns True if allowed to proceed, False if cancelled.
        """
        try:
            self._pages.flush_all()
        except Exception:
            log.exception("pages.flush_all failed (action=%s)", action_name)

        dirty = self._dirty_names()
        if not dirty:
            return True

        msg = (
            f"{action_name} 前检测到未保存更改：\n"
            + "\n".join([f" - {x}" for x in dirty])
            + "\n\n选择：\n"
              "【是】保存后继续\n"
              "【否】不保存继续\n"
              "【取消】返回"
        )
        res = messagebox.askyesnocancel("未保存更改", msg, parent=self._root)
        if res is None:
            return False

        if res is False:
            try:
                self._services.uow.rollback()
                self._services.notify_dirty()
            except Exception:
                log.exception("uow.rollback failed (action=%s)", action_name)

            try:
                self._pages.set_context(ctx)
            except Exception:
                log.exception("pages.set_context failed after rollback (action=%s)", action_name)

            return True

        # Yes -> save dirty parts
        try:
            parts = self._services.uow.dirty_parts()
            if parts:
                self._services.uow.commit(
                    parts=set(parts),
                    backup=bool(self._backup_provider()),
                    touch_meta=True,
                )
            self._services.notify_dirty()
            return True
        except Exception as e:
            log.exception("uow.commit failed (action=%s)", action_name)
            messagebox.showerror("保存失败", f"保存失败：{e}", parent=self._root)
            return False