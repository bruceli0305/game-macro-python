from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple

from pynput import keyboard, mouse

from core.event_bus import EventBus, Event
from core.event_types import EventType
from core.events.payloads import (
    PickContextRef,
    PickRequestPayload,
    PickModeEnteredPayload,
    PickModeExitedPayload,
    PickCanceledPayload,
    PickPreviewPayload,
    PickConfirmedPayload,
    InfoPayload,
    StatusPayload,
    ErrorPayload,
)
from core.pick.capture import ScreenCapture, SampleSpec


PickContext = Dict[str, Any]  # {"type":"skill_pixel"|"point", "id":"..."}


@dataclass
class PickConfig:
    delay_ms: int = 120
    preview_throttle_ms: int = 30
    error_throttle_ms: int = 800


class PickService:
    """
    Strict typed events version.

    Inputs:
      - PICK_REQUEST payload must be PickRequestPayload (from EventBus builder or post_payload)
      - PICK_START_LAST / PICK_CANCEL_REQUEST payload is None

    Outputs:
      - PICK_MODE_ENTERED -> PickModeEnteredPayload
      - PICK_PREVIEW -> PickPreviewPayload
      - PICK_CONFIRMED -> PickConfirmedPayload
      - PICK_CANCELED -> PickCanceledPayload
      - PICK_MODE_EXITED -> PickModeExitedPayload
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
        self._context_ref: Optional[PickContextRef] = None
        self._last_context_ref: Optional[PickContextRef] = None

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

    def _ctx_dict(self, ref: PickContextRef) -> PickContext:
        # keep old capture_spec_provider signature
        return {"type": ref.type, "id": ref.id}

    def _on_pick_request(self, ev: Event) -> None:
        p = ev.payload
        if not isinstance(p, PickRequestPayload):
            self._bus.post_payload(EventType.ERROR, ErrorPayload(msg="PICK_REQUEST payload 类型错误"))
            return
        if not p.context.id or not p.context.type:
            self._bus.post_payload(EventType.ERROR, ErrorPayload(msg="PICK_REQUEST 缺少有效 context"))
            return
        self.start(p.context)

    def _on_pick_start_last(self, _ev: Event) -> None:
        if self._last_context_ref is None:
            self._bus.post_payload(EventType.INFO, InfoPayload(msg="未设置取色目标：请在技能/点位页点击“从屏幕取色”"))
            return
        self.start(self._last_context_ref)

    def _on_pick_cancel(self, _ev: Event) -> None:
        if self._active:
            self.cancel()

    def start(self, context: PickContextRef) -> None:
        if self._active:
            self.stop(reason="restart")

        self._active = True
        self._context_ref = context
        self._last_context_ref = context

        self._start_t = time.monotonic()
        self._stop_evt.clear()
        self._last_err_t = 0.0
        self._announced_preview = False

        # typed enter event
        self._bus.post_payload(EventType.PICK_MODE_ENTERED, PickModeEnteredPayload(context=context))

        try:
            self._mouse_listener = mouse.Listener(on_click=self._on_click)
            self._mouse_listener.start()
        except Exception as e:
            self._bus.post_payload(EventType.ERROR, ErrorPayload(msg=f"鼠标监听启动失败", detail=str(e)))
            self.stop(reason="mouse_listener_failed")
            return

        try:
            self._kbd_listener = keyboard.Listener(on_press=self._on_key_press)
            self._kbd_listener.start()
        except Exception as e:
            self._bus.post_payload(EventType.ERROR, ErrorPayload(msg=f"键盘监听启动失败", detail=str(e)))
            self.stop(reason="kbd_listener_failed")
            return

        self._preview_thread = threading.Thread(target=self._preview_loop, daemon=True)
        self._preview_thread.start()

        self._bus.post_payload(EventType.STATUS, StatusPayload(msg="取色模式：移动鼠标预览，左键确认，Esc/右键取消"))

    def cancel(self) -> None:
        if not self._active:
            return
        ctx = self._context_ref
        if ctx is not None:
            self._bus.post_payload(EventType.PICK_CANCELED, PickCanceledPayload(context=ctx))
        self.stop(reason="canceled")

    def stop(self, *, reason: str) -> None:
        if not self._active:
            return

        ctx = self._context_ref
        self._active = False
        self._context_ref = None

        self._stop_evt.set()

        for lst in (self._mouse_listener, self._kbd_listener):
            if lst is not None:
                try:
                    lst.stop()
                except Exception:
                    pass
        self._mouse_listener = None
        self._kbd_listener = None

        if ctx is not None:
            self._bus.post_payload(EventType.PICK_MODE_EXITED, PickModeExitedPayload(context=ctx, reason=reason))
        else:
            # should not happen, but keep registry happy
            self._bus.post_payload(EventType.ERROR, ErrorPayload(msg=f"PICK_MODE_EXITED missing context; reason={reason}"))

    def _on_key_press(self, key) -> None:
        try:
            if key == keyboard.Key.esc:
                self.cancel()
        except Exception:
            pass

    def _resolve_monitor(self, abs_x: int, abs_y: int, requested: str) -> tuple[str, bool]:
        req = (requested or "primary").strip().lower() or "primary"
        try:
            rect_req = self._cap.get_monitor_rect(req)
            inside = rect_req.contains_abs(int(abs_x), int(abs_y))
        except Exception:
            inside = True

        if req == "all":
            return "all", inside

        if inside:
            return req, True

        used = self._cap.find_monitor_key_for_abs(int(abs_x), int(abs_y), default=req)
        return used, False

    def _on_click(self, abs_x: int, abs_y: int, button, pressed: bool) -> None:
        try:
            if not self._active or not pressed:
                return

            if button == mouse.Button.right:
                self.cancel()
                return

            if button != mouse.Button.left:
                return

            ctx_ref = self._context_ref
            if ctx_ref is None:
                self._bus.post_payload(EventType.ERROR, ErrorPayload(msg="取色确认失败: context 为空"))
                return

            ctx_dict = self._ctx_dict(ctx_ref)
            sample, mon_req = self._capture_spec_provider(ctx_dict)

            mon_used, inside = self._resolve_monitor(int(abs_x), int(abs_y), mon_req)

            r, g, b = self._cap.get_rgb_scoped_abs(abs_x, abs_y, sample, mon_used, require_inside=False)

            rel_x, rel_y = self._cap.abs_to_rel(abs_x, abs_y, mon_used)
            hx = f"#{r:02X}{g:02X}{b:02X}"

            payload = PickConfirmedPayload(
                context=ctx_ref,
                monitor_requested=mon_req,
                monitor=mon_used,
                inside=bool(inside),
                x=int(rel_x),
                y=int(rel_y),
                vx=int(abs_x),
                vy=int(abs_y),
                abs_x=int(abs_x),
                abs_y=int(abs_y),
                r=int(r),
                g=int(g),
                b=int(b),
                hex=hx,
            )
            self._bus.post_payload(EventType.PICK_CONFIRMED, payload)
            self.stop(reason="confirmed")

        except Exception as e:
            now = time.monotonic()
            cfg = self._pick_config_provider()
            if (now - self._last_err_t) * 1000.0 >= float(cfg.error_throttle_ms):
                self._last_err_t = now
                self._bus.post_payload(EventType.ERROR, ErrorPayload(msg=f"取色确认失败", detail=str(e)))

    def _preview_loop(self) -> None:
        ctrl = mouse.Controller()

        while self._active and not self._stop_evt.is_set():
            cfg = self._pick_config_provider()
            now = time.monotonic()

            if (now - self._start_t) * 1000.0 < float(cfg.delay_ms):
                time.sleep(0.01)
                continue

            try:
                ctx_ref = self._context_ref
                if ctx_ref is None:
                    time.sleep(0.02)
                    continue

                abs_x, abs_y = ctrl.position
                abs_x = int(abs_x)
                abs_y = int(abs_y)

                ctx_dict = self._ctx_dict(ctx_ref)
                sample, mon_req = self._capture_spec_provider(ctx_dict)
                mon_used, inside = self._resolve_monitor(abs_x, abs_y, mon_req)

                r, g, b = self._cap.get_rgb_scoped_abs(abs_x, abs_y, sample, mon_used, require_inside=False)
                rel_x, rel_y = self._cap.abs_to_rel(abs_x, abs_y, mon_used)
                hx = f"#{r:02X}{g:02X}{b:02X}"

                if not self._announced_preview:
                    self._announced_preview = True
                    self._bus.post_payload(EventType.INFO, InfoPayload(msg="取色预览已开始"))

                payload = PickPreviewPayload(
                    context=ctx_ref,
                    monitor_requested=mon_req,
                    monitor=mon_used,
                    inside=bool(inside),
                    x=int(rel_x),
                    y=int(rel_y),
                    vx=int(abs_x),
                    vy=int(abs_y),
                    abs_x=int(abs_x),
                    abs_y=int(abs_y),
                    r=int(r),
                    g=int(g),
                    b=int(b),
                    hex=hx,
                )
                self._bus.post_payload(EventType.PICK_PREVIEW, payload)

            except Exception as e:
                if (now - self._last_err_t) * 1000.0 >= float(cfg.error_throttle_ms):
                    self._last_err_t = now
                    self._bus.post_payload(EventType.STATUS, StatusPayload(msg=f"取色预览异常: {e}"))

            time.sleep(max(0.005, float(cfg.preview_throttle_ms) / 1000.0))