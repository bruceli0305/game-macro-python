# File: ui/app/pick_coordinator.py
from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from typing import Callable, Optional

from core.pick.engine import PickEngine, PickCallbacks
from core.pick.models import PickSessionConfig, PickPreview, PickConfirmed
from ui.pick_preview_window import PickPreviewWindow
from ui.app.status import StatusController
from ui.runtime.ui_dispatcher import UiDispatcher


@dataclass(frozen=True)
class _UiPolicySnapshot:
    avoid_mode: str
    preview_follow: bool
    preview_offset: tuple[int, int]
    preview_anchor: str


class PickCoordinator:
    """
    - Owns PickEngine
    - Owns PickPreviewWindow
    - Applies main window avoidance/restore
    - Routes confirm callback to caller
    """

    def __init__(
        self,
        *,
        root: tk.Misc,
        dispatcher: UiDispatcher,
        status: StatusController,
        ui_policy_provider: Callable[[], _UiPolicySnapshot],
    ) -> None:
        self._root = root
        self._dispatcher = dispatcher
        self._status = status
        self._ui_policy_provider = ui_policy_provider

        self._engine = PickEngine(scheduler=dispatcher)
        self._preview: Optional[PickPreviewWindow] = None

        self._prev_geo: str | None = None
        self._prev_state: str | None = None
        self._avoid_mode_applied: str | None = None

        self._policy: Optional[_UiPolicySnapshot] = None
        self._on_confirm_user: Optional[Callable[[PickConfirmed], None]] = None

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

        # canonical instruction message
        self._status.status(f"取色模式：移动鼠标预览，按 {cfg.confirm_hotkey} 确认，Esc 取消", ttl_ms=4000)

    # ---------- UI helpers ----------
    def _ensure_preview(self) -> None:
        if self._preview is None:
            self._preview = PickPreviewWindow(self._root, on_cancel=self.cancel)

    def _destroy_preview(self) -> None:
        if self._preview is not None:
            try:
                self._preview.destroy()
            except Exception:
                pass
            self._preview = None

    def _apply_avoidance_on_enter(self) -> None:
        pol = self._policy or self._ui_policy_provider()
        mode = pol.avoid_mode
        self._avoid_mode_applied = mode

        try:
            self._prev_geo = self._root.geometry()
        except Exception:
            self._prev_geo = None
        try:
            self._prev_state = self._root.state()
        except Exception:
            self._prev_state = None

        if mode == "hide_main":
            try:
                self._root.withdraw()
            except Exception:
                pass
        elif mode == "minimize":
            try:
                self._root.iconify()
            except Exception:
                pass
        elif mode == "move_aside":
            try:
                self._root.update_idletasks()
                sw = int(self._root.winfo_screenwidth())
                w = int(self._root.winfo_width())
                self._root.geometry(f"+{max(0, sw - w - 10)}+10")
            except Exception:
                pass

    def _restore_after_exit(self) -> None:
        mode = self._avoid_mode_applied
        self._avoid_mode_applied = None

        try:
            if mode in ("hide_main", "minimize"):
                self._root.deiconify()
        except Exception:
            pass

        if self._prev_geo:
            try:
                self._root.geometry(self._prev_geo)
            except Exception:
                pass

        if self._prev_state:
            try:
                if self._prev_state in ("normal", "zoomed"):
                    self._root.state(self._prev_state)
            except Exception:
                pass

        try:
            self._root.lift()
            self._root.focus_force()
        except Exception:
            pass

    def _get_virtual_screen_bounds(self) -> tuple[int, int, int, int]:
        try:
            import ctypes

            user32 = ctypes.windll.user32
            SM_XVIRTUALSCREEN = 76
            SM_YVIRTUALSCREEN = 77
            SM_CXVIRTUALSCREEN = 78
            SM_CYVIRTUALSCREEN = 79
            l = int(user32.GetSystemMetrics(SM_XVIRTUALSCREEN))
            t = int(user32.GetSystemMetrics(SM_YVIRTUALSCREEN))
            w = int(user32.GetSystemMetrics(SM_CXVIRTUALSCREEN))
            h = int(user32.GetSystemMetrics(SM_CYVIRTUALSCREEN))
            return l, t, l + w, t + h
        except Exception:
            return 0, 0, int(self._root.winfo_screenwidth()), int(self._root.winfo_screenheight())

    @staticmethod
    def _clamp(v: int, lo: int, hi: int) -> int:
        if v < lo:
            return lo
        if v > hi:
            return hi
        return v

    # ---------- engine callbacks (already in UI thread via dispatcher) ----------
    def _on_enter(self, _cfg: PickSessionConfig) -> None:
        self._apply_avoidance_on_enter()
        self._ensure_preview()
        if self._preview is not None:
            self._preview.hide()

    def _on_cancel(self) -> None:
        self._status.info("取色已取消", ttl_ms=2500)

    def _on_exit(self, _reason: str) -> None:
        self._destroy_preview()
        self._restore_after_exit()
        self._status.status("取色模式已退出", ttl_ms=2000)

    def _on_error(self, msg: str) -> None:
        self._status.status(msg, ttl_ms=3000)

    def _on_preview(self, p: PickPreview) -> None:
        self._ensure_preview()
        if self._preview is None:
            return

        self._preview.update_preview(x=p.x, y=p.y, r=p.r, g=p.g, b=p.b)
        self._preview.show()

        pol = self._policy or self._ui_policy_provider()
        follow = bool(pol.preview_follow)
        anchor = str(pol.preview_anchor or "bottom_right")

        try:
            ox, oy = int(pol.preview_offset[0]), int(pol.preview_offset[1])
        except Exception:
            ox, oy = 30, 30

        try:
            px = int(self._root.winfo_pointerx())
            py = int(self._root.winfo_pointery())
        except Exception:
            px, py = p.vx, p.vy

        try:
            pw, ph = self._preview.size
        except Exception:
            pw, ph = (180, 74)

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

        L, T, R, B = self._get_virtual_screen_bounds()
        nx = self._clamp(int(nx), L, R - pw)
        ny = self._clamp(int(ny), T, B - ph)

        self._preview.move_to(nx, ny)

    def _on_confirm(self, c: PickConfirmed) -> None:
        fn = self._on_confirm_user
        if fn is None:
            return
        fn(c)