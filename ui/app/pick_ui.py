from __future__ import annotations

import tkinter as tk
from typing import Callable, Optional

from core.event_bus import EventBus, Event
from core.event_types import EventType
from core.events.payloads import PickPreviewPayload, PickModeEnteredPayload, PickModeExitedPayload, PickCanceledPayload, InfoPayload, StatusPayload
from ui.pick_preview_window import PickPreviewWindow


class PickUiController:
    """
    Handles only the UI/UX part of pick mode:
    - avoidance (hide/minimize/move_aside/none)
    - preview window show/move/update
    STRICT typed event payloads.
    """

    def __init__(self, *, root: tk.Misc, bus: EventBus, ctx_provider: Callable[[], object]) -> None:
        self._root = root
        self._bus = bus
        self._ctx_provider = ctx_provider

        self._preview: Optional[PickPreviewWindow] = None
        self._prev_geo: str | None = None
        self._prev_state: str | None = None
        self._avoid_mode_applied: str | None = None

        self._bus.subscribe(EventType.PICK_MODE_ENTERED, self._on_pick_mode_entered)
        self._bus.subscribe(EventType.PICK_PREVIEW, self._on_pick_preview)
        self._bus.subscribe(EventType.PICK_MODE_EXITED, self._on_pick_mode_exited)
        self._bus.subscribe(EventType.PICK_CANCELED, self._on_pick_canceled)

    def close(self) -> None:
        self._destroy_preview()
        self._restore_after_exit()

    def _ctx(self):
        return self._ctx_provider()

    def _ensure_preview(self) -> None:
        if self._preview is None:
            try:
                self._preview = PickPreviewWindow(self._root)
            except Exception:
                self._preview = None

    def _destroy_preview(self) -> None:
        if self._preview is not None:
            try:
                self._preview.destroy()
            except Exception:
                pass
            self._preview = None

    def _apply_avoidance_on_enter(self) -> None:
        av = getattr(getattr(getattr(self._ctx(), "base", None), "pick", None), "avoidance", None)
        mode = getattr(av, "mode", "hide_main")
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

    def _on_pick_mode_entered(self, ev: Event) -> None:
        if not isinstance(ev.payload, PickModeEnteredPayload):
            return
        self._apply_avoidance_on_enter()
        self._ensure_preview()
        if self._preview is not None:
            try:
                self._preview.hide()
            except Exception:
                pass
        self._bus.post_payload(EventType.STATUS, StatusPayload(msg="取色模式已进入"))

    def _on_pick_canceled(self, ev: Event) -> None:
        if not isinstance(ev.payload, PickCanceledPayload):
            return
        self._bus.post_payload(EventType.INFO, InfoPayload(msg="取色已取消"))

    def _on_pick_mode_exited(self, ev: Event) -> None:
        if not isinstance(ev.payload, PickModeExitedPayload):
            return
        self._destroy_preview()
        self._restore_after_exit()
        self._bus.post_payload(EventType.STATUS, StatusPayload(msg="取色模式已退出"))

    def _on_pick_preview(self, ev: Event) -> None:
        p = ev.payload
        if not isinstance(p, PickPreviewPayload):
            return

        self._ensure_preview()
        if self._preview is None:
            return

        try:
            self._preview.update_preview(x=p.x, y=p.y, r=p.r, g=p.g, b=p.b)
        except Exception:
            pass

        try:
            self._preview.show()
        except Exception:
            pass

        av = getattr(getattr(getattr(self._ctx(), "base", None), "pick", None), "avoidance", None)
        follow = bool(getattr(av, "preview_follow_cursor", True))
        anchor = str(getattr(av, "preview_anchor", "bottom_right") or "bottom_right")
        try:
            off = getattr(av, "preview_offset", (30, 30))
            ox, oy = int(off[0]), int(off[1])
        except Exception:
            ox, oy = 30, 30

        try:
            px = int(self._root.winfo_pointerx())
            py = int(self._root.winfo_pointery())
        except Exception:
            px, py = p.x, p.y

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

        try:
            self._preview.move_to(nx, ny)
        except Exception:
            pass