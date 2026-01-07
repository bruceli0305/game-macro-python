from __future__ import annotations

import logging

from PySide6.QtWidgets import QMainWindow, QApplication
from PySide6.QtCore import QRect, QPoint

from core.models.app_state import AppState
from core.repos.app_state_repo import AppStateRepo

log = logging.getLogger(__name__)


class WindowStateController:
    """
    负责窗口几何状态的恢复/保存：
    - apply_initial_geometry: 从 AppState.window 恢复大小和位置，
      若无有效数据或数据已超出当前屏幕范围，则使用居中默认布局。
    - persist_current_geometry: 将当前几何写回 AppState 并保存
    """

    def __init__(self, *, root: QMainWindow, repo: AppStateRepo, state: AppState) -> None:
        self._root = root
        self._repo = repo
        self._state = state

    # ---------- 内部辅助 ----------

    def _current_screen_available_rect(self) -> QRect:
        """
        返回当前窗口所在屏幕（或主屏）的 availableGeometry。
        """
        try:
            screen = self._root.screen()
            if screen is None:
                screen = QApplication.primaryScreen()
            if screen is not None:
                return screen.availableGeometry()
        except Exception:
            pass

        # 兜底：构造一个 1920x1080 的虚拟可用区域
        return QRect(0, 0, 1920, 1080)

    def _all_screen_rects(self) -> list[QRect]:
        """
        返回所有屏幕的 availableGeometry 列表，用于判断一个矩形是否在任一屏幕内。
        """
        out: list[QRect] = []
        try:
            app = QApplication.instance()
            if app is not None:
                for s in app.screens():
                    try:
                        out.append(s.availableGeometry())
                    except Exception:
                        continue
        except Exception:
            pass
        if not out:
            out.append(self._current_screen_available_rect())
        return out

    def _rect_is_reasonable(self, r: QRect) -> bool:
        """
        判断一个矩形是否在任一屏幕的可用区域内有交集，
        且宽高为正（避免 width/height=0 的情况）。
        """
        if not r.isValid() or r.width() <= 0 or r.height() <= 0:
            return False

        for sr in self._all_screen_rects():
            if sr.intersects(r):
                return True
        return False

    # ---------- 对外接口 ----------

    def apply_initial_geometry(self) -> None:
        """
        恢复或初始化窗口几何：

        逻辑：
        - 从 AppState.window 读取 width/height/x/y；
        - 若 x,y 为有效 int 且矩形在当前屏幕范围内 -> 使用该几何；
        - 否则按当前屏幕 availableGeometry 居中，并裁剪宽高不超过屏幕。
        """
        try:
            # 目标宽高先按配置读取，再裁剪到当前屏幕
            scr = self._current_screen_available_rect()
            scr_w = max(400, scr.width())
            scr_h = max(300, scr.height())

            # 默认期望大小（不超过屏幕的 90%）
            default_w = min(int(getattr(self._state.window, "width", 1100) or 1100), int(scr_w * 0.9))
            default_h = min(int(getattr(self._state.window, "height", 720) or 720), int(scr_h * 0.9))

            if default_w <= 0:
                default_w = min(1100, scr_w)
            if default_h <= 0:
                default_h = min(720, scr_h)

            # 从状态中读取 x,y
            x = getattr(self._state.window, "x", None)
            y = getattr(self._state.window, "y", None)

            use_saved_pos = isinstance(x, int) and isinstance(y, int)

            if use_saved_pos:
                rect_saved = QRect(int(x), int(y), int(default_w), int(default_h))
                if self._rect_is_reasonable(rect_saved):
                    # 使用保存的位置
                    self._root.resize(default_w, default_h)
                    self._root.move(int(x), int(y))
                    return
                else:
                    # 保存的位置已无效（例如换屏幕/分辨率），回退为居中
                    log.info(
                        "WindowStateController: saved geometry out of screen, fallback to centered "
                        "(x=%s, y=%s, w=%s, h=%s)",
                        x,
                        y,
                        default_w,
                        default_h,
                    )

            # 计算居中位置
            new_w = min(default_w, scr_w)
            new_h = min(default_h, scr_h)
            cx = scr.x() + (scr_w - new_w) // 2
            cy = scr.y() + (scr_h - new_h) // 2

            self._root.resize(new_w, new_h)
            self._root.move(cx, cy)
        except Exception:
            log.exception("apply_initial_geometry failed")

    def persist_current_geometry(self) -> None:
        try:
            g = self._root.geometry()
            self._state.window.width = int(g.width())
            self._state.window.height = int(g.height())
            self._state.window.x = int(g.x())
            self._state.window.y = int(g.y())
            self._repo.save(self._state)
        except Exception:
            log.exception("persist_current_geometry failed")