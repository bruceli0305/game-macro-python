from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple

from pynput import keyboard, mouse

from core.event_bus import EventBus
from core.event_types import EventType
from core.pick.capture import ScreenCapture, SampleSpec


PickContext = Dict[str, Any]  # {"type":"skill_pixel"|"point", "id":"..."}


@dataclass
class PickConfig:
    delay_ms: int = 120
    preview_throttle_ms: int = 30
    error_throttle_ms: int = 800


class PickService:
    """
    坐标策略（本版本）：
    - 鼠标回调拿到的是绝对坐标 (abs_x, abs_y)
    - 对外事件里提供：
        x,y -> 相对坐标（相对 monitor_key 左上角）
        abs_x, abs_y -> 绝对坐标（调试用）
    """

    def __init__(
        self,
        *,
        bus: EventBus,
        pick_config_provider: Callable[[], PickConfig],
        capture_spec_provider: Callable[[PickContext], Tuple[SampleSpec, str]],
    ) -> None:
        self._bus = bus
        self._pick_config_provider = pick_config_provider
        self._capture_spec_provider = capture_spec_provider

        self._cap = ScreenCapture()

        self._active = False
        self._context: Optional[PickContext] = None
        self._last_context: Optional[PickContext] = None

        self._mouse_listener: Optional[mouse.Listener] = None
        self._kbd_listener: Optional[keyboard.Listener] = None

        self._start_t = 0.0

        self._preview_thread: Optional[threading.Thread] = None
        self._stop_evt = threading.Event()
        self._last_err_t = 0.0
        self._announced_preview = False

        self._bus.subscribe(EventType.PICK_REQUEST, self._on_pick_request)
        self._bus.subscribe(EventType.PICK_START_LAST, self._on_pick_start_last)
        self._bus.subscribe(EventType.PICK_CANCEL_REQUEST, self._on_pick_cancel)

    def close(self) -> None:
        self.stop(reason="shutdown")
        self._cap.close()

    def _on_pick_request(self, ev) -> None:
        ctx = ev.payload.get("context")
        if not isinstance(ctx, dict) or not ctx.get("id") or not ctx.get("type"):
            self._bus.post(EventType.ERROR, msg="PICK_REQUEST 缺少有效 context")
            return
        self.start(ctx)

    def _on_pick_start_last(self, _ev) -> None:
        if self._last_context is None:
            self._bus.post(EventType.INFO, msg="未设置取色目标：请在技能/点位页点击“从屏幕取色”")
            return
        self.start(self._last_context)

    def _on_pick_cancel(self, _ev) -> None:
        if self._active:
            self.cancel()

    def start(self, context: PickContext) -> None:
        if self._active:
            self.stop(reason="restart")

        self._active = True
        self._context = dict(context)
        self._last_context = dict(context)

        self._start_t = time.monotonic()
        self._stop_evt.clear()
        self._last_err_t = 0.0
        self._announced_preview = False

        self._bus.post(EventType.PICK_MODE_ENTERED, context=self._context)

        try:
            self._mouse_listener = mouse.Listener(on_click=self._on_click)
            self._mouse_listener.start()
        except Exception as e:
            self._bus.post(EventType.ERROR, msg=f"鼠标监听启动失败: {e}")
            self.stop(reason="mouse_listener_failed")
            return

        try:
            self._kbd_listener = keyboard.Listener(on_press=self._on_key_press)
            self._kbd_listener.start()
        except Exception as e:
            self._bus.post(EventType.ERROR, msg=f"键盘监听启动失败: {e}")
            self.stop(reason="kbd_listener_failed")
            return

        self._preview_thread = threading.Thread(target=self._preview_loop, daemon=True)
        self._preview_thread.start()

        self._bus.post(EventType.STATUS, msg="取色模式：移动鼠标预览，左键确认，Esc/右键取消")

    def cancel(self) -> None:
        if not self._active:
            return
        self._bus.post(EventType.PICK_CANCELED, context=self._context or {})
        self.stop(reason="canceled")

    def stop(self, *, reason: str) -> None:
        if not self._active:
            return

        ctx = self._context or {}
        self._active = False
        self._context = None

        self._stop_evt.set()

        for lst in (self._mouse_listener, self._kbd_listener):
            if lst is not None:
                try:
                    lst.stop()
                except Exception:
                    pass
        self._mouse_listener = None
        self._kbd_listener = None

        self._bus.post(EventType.PICK_MODE_EXITED, context=ctx, reason=reason)

    def _on_key_press(self, key) -> None:
        try:
            if key == keyboard.Key.esc:
                self.cancel()
        except Exception:
            pass

    def _on_click(self, abs_x: int, abs_y: int, button, pressed: bool) -> None:
        try:
            if not self._active or not pressed:
                return

            if button == mouse.Button.right:
                self.cancel()
                return

            if button != mouse.Button.left:
                return

            ctx = self._context or {}
            sample, mon = self._capture_spec_provider(ctx)

            r, g, b = self._cap.get_rgb_scoped_abs(abs_x, abs_y, sample, mon, require_inside=True)

            rel_x, rel_y = self._cap.abs_to_rel(abs_x, abs_y, mon)
            hx = f"#{r:02X}{g:02X}{b:02X}"

            self._bus.post(
                EventType.PICK_CONFIRMED,
                context=ctx,
                monitor=mon,
                x=int(rel_x),
                y=int(rel_y),
                abs_x=int(abs_x),
                abs_y=int(abs_y),
                r=r,
                g=g,
                b=b,
                hex=hx,
            )
            self.stop(reason="confirmed")

        except Exception as e:
            now = time.monotonic()
            cfg = self._pick_config_provider()
            if (now - self._last_err_t) * 1000.0 >= float(cfg.error_throttle_ms):
                self._last_err_t = now
                self._bus.post(EventType.ERROR, msg=f"取色确认失败: {e}")

    def _preview_loop(self) -> None:
        ctrl = mouse.Controller()

        while self._active and not self._stop_evt.is_set():
            cfg = self._pick_config_provider()
            now = time.monotonic()

            if (now - self._start_t) * 1000.0 < float(cfg.delay_ms):
                time.sleep(0.01)
                continue

            try:
                abs_x, abs_y = ctrl.position
                ctx = self._context or {}
                sample, mon = self._capture_spec_provider(ctx)

                r, g, b = self._cap.get_rgb_scoped_abs(abs_x, abs_y, sample, mon, require_inside=True)
                rel_x, rel_y = self._cap.abs_to_rel(abs_x, abs_y, mon)
                hx = f"#{r:02X}{g:02X}{b:02X}"

                if not self._announced_preview:
                    self._announced_preview = True
                    self._bus.post(EventType.INFO, msg="取色预览已开始")

                self._bus.post(
                    EventType.PICK_PREVIEW,
                    context=ctx,
                    monitor=mon,
                    x=int(rel_x),
                    y=int(rel_y),
                    abs_x=int(abs_x),
                    abs_y=int(abs_y),
                    r=r,
                    g=g,
                    b=b,
                    hex=hx,
                )

            except Exception as e:
                if (now - self._last_err_t) * 1000.0 >= float(cfg.error_throttle_ms):
                    self._last_err_t = now
                    self._bus.post(EventType.STATUS, msg=f"取色预览暂停: {e}")

            time.sleep(max(0.005, float(cfg.preview_throttle_ms) / 1000.0))