# qtui/pick/coordinator.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Tuple, List

from PySide6.QtCore import QObject, QPoint
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QMainWindow, QApplication

from core.pick.engine import PickEngine, PickCallbacks
from core.pick.models import PickSessionConfig, PickPreview, PickConfirmed

from qtui.dispatcher import QtDispatcher
from qtui.status_bar import StatusController
from qtui.pick.preview_window import PickPreviewWindow


@dataclass(frozen=True)
class UiPickPolicySnapshot:
    avoid_mode: str           # "hide_main" | "minimize" | "move_aside" | "none"
    preview_follow: bool
    preview_offset: tuple[int, int]
    preview_anchor: str       # "bottom_right" | "bottom_left" | "top_right" | "top_left"


class QtPickCoordinator(QObject):
    """
    - 拥有 PickEngine
    - 拥有 PickPreviewWindow
    - 负责主窗口避让/恢复
    - 将 confirm 回调传递给调用者（SkillsPage / PointsPage）
    """

    def __init__(
        self,
        *,
        root: QMainWindow,
        dispatcher: QtDispatcher,
        status: StatusController,
        ui_policy_provider: Callable[[], UiPickPolicySnapshot],
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._root = root
        self._dispatcher = dispatcher
        self._status = status
        self._ui_policy_provider = ui_policy_provider

        self._engine = PickEngine(scheduler=dispatcher)
        self._preview: Optional[PickPreviewWindow] = None

        self._prev_geo = None
        self._prev_state = None
        self._avoid_mode_applied: Optional[str] = None

        self._policy: Optional[UiPickPolicySnapshot] = None
        self._on_confirm_user: Optional[Callable[[PickConfirmed], None]] = None

    # ---------- 外部 API ----------

    def close(self) -> None:
        try:
            self.cancel()
        except Exception:
            pass
        try:
            self._engine.close()
        except Exception:
            pass
        self._destroy_preview()
        self._restore_after_exit()

    def cancel(self) -> None:
        self._engine.cancel()

    def request_pick(self, *, cfg: PickSessionConfig, on_confirm: Callable[[PickConfirmed], None]) -> None:
        """
        由 SkillsPage / PointsPage 调用，发起取色。
        """
        self._on_confirm_user = on_confirm
        self._policy = self._ui_policy_provider()

        cbs = PickCallbacks(
            on_enter=self._on_enter,
            on_preview=self._on_preview,
            on_confirm=self._on_confirm,
            on_cancel=self._on_cancel,
            on_exit=self._on_exit,
            on_error=self._on_error,
        )
        self._engine.start(cfg, cbs)

        # 提示信息
        self._status.status_msg(
            f"取色模式：移动鼠标预览，按 {cfg.confirm_hotkey} 确认，Esc 取消",
            ttl_ms=4000,
        )

    # ---------- 内部：preview 窗管理 ----------

    def _ensure_preview(self) -> None:
        if self._preview is None:
            self._preview = PickPreviewWindow(on_cancel=self.cancel, parent=self._root)

    def _destroy_preview(self) -> None:
        if self._preview is not None:
            try:
                self._preview.close()
            except Exception:
                pass
            self._preview = None

    # ---------- 内部：主窗口避让/恢复 ----------

    def _apply_avoidance_on_enter(self) -> None:
        pol = self._policy or self._ui_policy_provider()
        mode = pol.avoid_mode
        self._avoid_mode_applied = mode

        try:
            self._prev_geo = self._root.geometry()
        except Exception:
            self._prev_geo = None
        try:
            self._prev_state = self._root.windowState()
        except Exception:
            self._prev_state = None

        if mode == "hide_main":
            try:
                self._root.hide()
            except Exception:
                pass
        elif mode == "minimize":
            try:
                self._root.showMinimized()
            except Exception:
                pass
        elif mode == "move_aside":
            try:
                screen = self._root.screen()
                if screen is None:
                    screen = QApplication.primaryScreen()
                if screen is not None:
                    geo = screen.availableGeometry()
                    self._root.resize(self._root.width(), self._root.height())
                    x = max(0, geo.right() - self._root.width() - 10)
                    y = geo.top() + 10
                    self._root.move(x, y)
            except Exception:
                pass

    def _restore_after_exit(self) -> None:
        mode = self._avoid_mode_applied
        self._avoid_mode_applied = None

        # 恢复显示
        try:
            if mode in ("hide_main", "minimize"):
                self._root.showNormal()
        except Exception:
            pass

        # 恢复位置
        if self._prev_geo is not None:
            try:
                self._root.setGeometry(self._prev_geo)
            except Exception:
                pass

        # 恢复最大化状态
        if self._prev_state is not None:
            try:
                self._root.setWindowState(self._prev_state)
            except Exception:
                pass

        # 前置
        try:
            self._root.raise_()
            self._root.activateWindow()
        except Exception:
            pass

    def _virtual_bounds(self) -> Tuple[int, int, int, int]:
        """
        计算所有屏幕的虚拟边界。
        """
        app = QApplication.instance()
        if app is None:
            return 0, 0, 1920, 1080

        screens = app.screens()
        if not screens:
            return 0, 0, 1920, 1080

        xs: List[int] = []
        ys: List[int] = []
        rs: List[int] = []
        bs: List[int] = []

        for s in screens:
            g = s.geometry()
            xs.append(g.left())
            ys.append(g.top())
            rs.append(g.right())
            bs.append(g.bottom())

        return min(xs), min(ys), max(rs), max(bs)

    @staticmethod
    def _clamp(v: int, lo: int, hi: int) -> int:
        if v < lo:
            return lo
        if v > hi:
            return hi
        return v

    # ---------- PickEngine 回调（已在 UI 线程） ----------

    def _on_enter(self, _cfg: PickSessionConfig) -> None:
        self._apply_avoidance_on_enter()
        self._ensure_preview()
        if self._preview is not None:
            self._preview.hide_preview()

    def _on_cancel(self) -> None:
        self._status.info("取色已取消", ttl_ms=2500)

    def _on_exit(self, _reason: str) -> None:
        self._destroy_preview()
        self._restore_after_exit()
        self._status.status_msg("取色模式已退出", ttl_ms=2000)

    def _on_error(self, msg: str) -> None:
        self._status.status_msg(msg, ttl_ms=3000)

    def _on_preview(self, p: PickPreview) -> None:
        self._ensure_preview()
        if self._preview is None:
            return

        self._preview.update_preview(x=p.x, y=p.y, r=p.r, g=p.g, b=p.b)
        self._preview.show_preview()

        pol = self._policy or self._ui_policy_provider()
        follow = bool(pol.preview_follow)
        anchor = str(pol.preview_anchor or "bottom_right")

        try:
            ox, oy = int(pol.preview_offset[0]), int(pol.preview_offset[1])
        except Exception:
            ox, oy = 30, 30

        # 获取鼠标位置
        try:
            pos = QCursor.pos()
            px, py = pos.x(), pos.y()
        except Exception:
            px, py = p.vx, p.vy

        pw, ph = self._preview.size_tuple

        if not follow:
            nx, ny = 20, 20
        else:
            if anchor == "bottom_right":
                nx, ny = px + ox, py + oy
            elif anchor == "bottom_left":
                nx, ny = px - ox - pw, py + oy
            elif anchor == "top_right":
                nx, ny = px + ox, py - oy - ph
            elif anchor == "top_left":
                nx, ny = px - ox - pw, py - oy - ph
            else:
                nx, ny = px + ox, py + oy

        L, T, R, B = self._virtual_bounds()
        nx = self._clamp(int(nx), L, R - pw)
        ny = self._clamp(int(ny), T, B - ph)

        self._preview.move_to(nx, ny)

    def _on_confirm(self, c: PickConfirmed) -> None:
        fn = self._on_confirm_user
        if fn is None:
            return
        fn(c)