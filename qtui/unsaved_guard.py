# qtui/unsaved_guard.py
from __future__ import annotations

import logging
from typing import Callable

from PySide6.QtWidgets import QMainWindow, QMessageBox

from core.app.services.app_services import AppServices
from core.profiles import ProfileContext

log = logging.getLogger(__name__)


class UnsavedChangesGuard:
    """
    未保存变更守卫（Qt 版）：

    confirm(action_name, ctx) -> bool
      - True  : 可以继续执行后续操作
      - False : 取消当前操作

    行为：
    1) 调用 pages_flush_all() 把当前表单写入模型
    2) 检查 services.dirty_parts() 是否有脏数据
    3) 若有脏数据，弹出对话框：
       - 是：保存后继续
       - 否：不保存，回滚到上次快照后继续
       - 取消：中断当前操作
    """

    def __init__(
        self,
        *,
        window: QMainWindow,
        services: AppServices,
        pages_flush_all: Callable[[], None],
        pages_set_context: Callable[[ProfileContext], None],
        backup_provider: Callable[[], bool],
    ) -> None:
        self._win = window
        self._services = services
        self._pages_flush_all = pages_flush_all
        self._pages_set_context = pages_set_context
        self._backup_provider = backup_provider

    # ---------- 内部：读取脏部分名称 ----------

    def _dirty_names(self) -> list[str]:
        try:
            parts = self._services.dirty_parts()
        except Exception:
            log.exception("read services.dirty_parts failed")
            return []

        mapping = {
            "base": "基础配置",
            "skills": "技能配置",
            "points": "取色点位配置",
            "meta": "Profile 元信息",
            "rotations": "循环/轨道配置",
        }

        out: list[str] = []
        for p in ["base", "skills", "points", "meta", "rotations"]:
            if p in parts:
                out.append(mapping.get(p, p))
        return out

    # ---------- 对外：确认 ----------

    def confirm(self, action_name: str, ctx: ProfileContext) -> bool:
        """
        弹出确认框处理未保存变更。

        action_name: 用于提示内容，比如 "切换 Profile"、"Profile 操作"、"退出程序"
        ctx: 当前 ProfileContext，用于回滚后重建页面视图
        """
        # 先将 UI 表单刷入内存模型
        try:
            self._pages_flush_all()
        except Exception:
            log.exception("pages_flush_all failed (action=%s)", action_name)

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

        box = QMessageBox(self._win)
        box.setWindowTitle("未保存更改")
        box.setIcon(QMessageBox.Warning)
        box.setText(msg)
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
        box.setDefaultButton(QMessageBox.Yes)

        res = box.exec()
        if res == QMessageBox.Cancel:
            return False

        if res == QMessageBox.No:
            # 放弃更改：回滚内存状态
            try:
                self._services.rollback_cmd()
            except Exception:
                log.exception("services.rollback_cmd failed (action=%s)", action_name)

            # 回滚后刷新页面（对象引用已被替换）
            try:
                self._pages_set_context(ctx)
                self._pages_flush_all()
            except Exception:
                pass

            return True

        if res == QMessageBox.Yes:
            # 保存后继续
            try:
                backup = bool(self._backup_provider())
            except Exception:
                backup = True

            try:
                self._services.save_dirty_cmd(backup=backup, touch_meta=True)
                return True
            except Exception as e:
                log.exception("services.save_dirty_cmd failed (action=%s)", action_name)
                QMessageBox.critical(self._win, "保存失败", f"保存失败：{e}", QMessageBox.Ok)
                return False

        # 理论上不会到这里
        return False