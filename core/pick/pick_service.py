# File: core/pick/pick_service.py
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional, Tuple

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
)
from core.pick.capture import ScreenCapture, SampleSpec
from core.input.hotkey import MOD_KEYS, MOD_NAME, normalize, compose, key_to_name


def _clamp(v: int, lo: int, hi: int) -> int:
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


@dataclass(frozen=True)
class PickConfig:
    delay_ms: int = 120
    preview_throttle_ms: int = 30
    error_throttle_ms: int = 800

    confirm_hotkey: str = "f8"  # e.g. "ctrl+alt+f8"
    mouse_avoid: bool = True
    mouse_avoid_offset_y: int = 80
    mouse_avoid_settle_ms: int = 80


@dataclass(frozen=True)
class _SessionSnapshot:
    """
    Immutable per-session snapshot.
    Background threads will ONLY use this snapshot (no ctx reads).
    """
    context: PickContextRef
    cfg: PickConfig
    sample: SampleSpec
    monitor_requested: str


class PickService:
    """
    大刀阔斧版（仍保留 EventBus 事件协议，避免你一次重写所有 UI）：

    - start() 时生成 _SessionSnapshot（confirm_hotkey / mouse_avoid / sample / monitor 等一次性固化）
    - preview 线程 & keyboard listener 线程不再调用 provider（避免切 profile 时读到一半 ctx 被替换）
    - stop() 会 join preview 线程（短 timeout），减少竞态窗口
    - Esc 固定取消；确认按 session.confirm_hotkey
    """

    def __init__(
        self,
        *,
        bus: EventBus,
        pick_config_provider: Callable[[], PickConfig],
        capture_spec_provider: Callable[[PickContextRef], Tuple[SampleSpec, str]],
    ) -> None:
        self._bus = bus
        self._pick_config_provider = pick_config_provider
        self._capture_spec_provider = capture_spec_provider

        self._cap = ScreenCapture()

        self._lock = threading.RLock()

        self._active = False
        self._session: Optional[_SessionSnapshot] = None

        self._kbd_listener: Optional[keyboard.Listener] = None
        self._preview_thread: Optional[threading.Thread] = None
        self._stop_evt = threading.Event()

        self._start_t = 0.0
        self._last_err_t = 0.0
        self._announced_preview = False

        # pressed modifiers tracked by keyboard listener thread
        self._mods: set[str] = set()

        self._bus.subscribe(EventType.PICK_REQUEST, self._on_pick_request)
        self._bus.subscribe(EventType.PICK_CANCEL_REQUEST, self._on_pick_cancel)

    # ---------- public ----------
    def close(self) -> None:
        self.stop(reason="shutdown")
        try:
            self._cap.close()
        except Exception:
            pass

    def cancel(self) -> None:
        with self._lock:
            if not self._active:
                return
            sess = self._session
        if sess is not None:
            self._bus.post_payload(EventType.PICK_CANCELED, PickCanceledPayload(context=sess.context))
        self.stop(reason="canceled")

    def start(self, context: PickContextRef) -> None:
        # 同步重启
        self.stop(reason="restart")

        # 生成会话快照（一次性固化）
        try:
            cfg = self._pick_config_provider()
        except Exception:
            cfg = PickConfig()

        try:
            sample, mon_req = self._capture_spec_provider(context)
        except Exception:
            sample, mon_req = SampleSpec(mode="single", radius=0), "primary"

        hk = normalize(getattr(cfg, "confirm_hotkey", "") or "f8") or "f8"
        cfg2 = PickConfig(
            delay_ms=int(getattr(cfg, "delay_ms", 120) or 120),
            preview_throttle_ms=int(getattr(cfg, "preview_throttle_ms", 30) or 30),
            error_throttle_ms=int(getattr(cfg, "error_throttle_ms", 800) or 800),
            confirm_hotkey=hk,
            mouse_avoid=bool(getattr(cfg, "mouse_avoid", True)),
            mouse_avoid_offset_y=int(getattr(cfg, "mouse_avoid_offset_y", 80) or 80),
            mouse_avoid_settle_ms=int(getattr(cfg, "mouse_avoid_settle_ms", 80) or 80),
        )

        sess = _SessionSnapshot(
            context=context,
            cfg=cfg2,
            sample=sample,
            monitor_requested=(mon_req or "primary").strip().lower() or "primary",
        )

        with self._lock:
            self._active = True
            self._session = sess
            self._start_t = time.monotonic()
            self._stop_evt.clear()
            self._last_err_t = 0.0
            self._announced_preview = False
            self._mods.clear()

        self._bus.post_payload(EventType.PICK_MODE_ENTERED, PickModeEnteredPayload(context=context))

        try:
            self._kbd_listener = keyboard.Listener(on_press=self._on_key_press, on_release=self._on_key_release)
            self._kbd_listener.start()
        except Exception as e:
            from core.events.payloads import ErrorPayload
            self._bus.post_payload(EventType.ERROR, ErrorPayload(msg="键盘监听启动失败", detail=str(e)))
            self.stop(reason="kbd_listener_failed")
            return

        self._preview_thread = threading.Thread(target=self._preview_loop, daemon=True)
        self._preview_thread.start()

        from core.events.payloads import StatusPayload
        self._bus.post_payload(
            EventType.STATUS,
            StatusPayload(msg=f"取色模式：移动鼠标预览，按 {sess.cfg.confirm_hotkey} 确认，Esc 取消"),
        )

    def stop(self, *, reason: str) -> None:
        with self._lock:
            if not self._active:
                return
            sess = self._session
            self._active = False
            self._session = None
            self._mods.clear()
            self._stop_evt.set()

            kbd = self._kbd_listener
            self._kbd_listener = None

            th = self._preview_thread
            self._preview_thread = None

        if kbd is not None:
            try:
                kbd.stop()
            except Exception:
                pass

        # join preview thread（短超时，避免 UI 卡死）
        if th is not None:
            try:
                th.join(timeout=0.25)
            except Exception:
                pass

        if sess is not None:
            self._bus.post_payload(EventType.PICK_MODE_EXITED, PickModeExitedPayload(context=sess.context, reason=reason))

    # ---------- bus handlers ----------
    def _on_pick_request(self, ev: Event) -> None:
        p = ev.payload
        if not isinstance(p, PickRequestPayload):
            from core.events.payloads import ErrorPayload
            self._bus.post_payload(EventType.ERROR, ErrorPayload(msg="PICK_REQUEST payload 类型错误"))
            return
        if not p.context.id or not p.context.type:
            from core.events.payloads import ErrorPayload
            self._bus.post_payload(EventType.ERROR, ErrorPayload(msg="PICK_REQUEST 缺少有效 context"))
            return
        self.start(p.context)

    def _on_pick_cancel(self, _ev: Event) -> None:
        self.cancel()

    # ---------- keyboard listener thread ----------
    def _on_key_press(self, key) -> None:
        try:
            with self._lock:
                if not self._active:
                    return
                sess = self._session
            if sess is None:
                return

            if key == keyboard.Key.esc:
                self.cancel()
                return

            if key in MOD_KEYS:
                name = MOD_NAME.get(key, "")
                if name:
                    self._mods.add(name)
                return

            main = key_to_name(key)
            if not main:
                return

            got = compose(self._mods, main)
            if normalize(got) == sess.cfg.confirm_hotkey:
                self._confirm_at_current_mouse(sess)
                return

        except Exception:
            # 不崩监听线程
            pass

    def _on_key_release(self, key) -> None:
        try:
            with self._lock:
                if not self._active:
                    return
            if key in MOD_KEYS:
                name = MOD_NAME.get(key, "")
                if name and name in self._mods:
                    self._mods.remove(name)
        except Exception:
            pass

    def _confirm_at_current_mouse(self, sess: _SessionSnapshot) -> None:
        """
        在 keyboard listener 线程里执行确认：
        - 读取当前鼠标位置作为原点 (x0,y0)
        - 可选鼠标避让（只移动 y）
        - 对原点采样并发 PICK_CONFIRMED
        """
        ctrl = mouse.Controller()

        try:
            x0, y0 = ctrl.position
            x0 = int(x0)
            y0 = int(y0)

            mon_used, inside = self._resolve_monitor(x0, y0, sess.monitor_requested)

            # 鼠标避让（best-effort）
            if sess.cfg.mouse_avoid:
                dy = int(sess.cfg.mouse_avoid_offset_y)
                if dy != 0:
                    try:
                        rect = self._cap.get_monitor_rect(mon_used)
                        y1 = y0 + dy
                        if not (rect.top <= y1 < rect.bottom):
                            y1 = y0 - dy
                        y1 = _clamp(int(y1), int(rect.top), int(rect.bottom) - 1)
                        try:
                            ctrl.position = (int(x0), int(y1))
                        except Exception:
                            pass

                        settle = int(sess.cfg.mouse_avoid_settle_ms)
                        if settle > 0:
                            time.sleep(float(settle) / 1000.0)
                    except Exception:
                        pass

            r, g, b = self._cap.get_rgb_scoped_abs(x0, y0, sess.sample, mon_used, require_inside=False)
            rel_x, rel_y = self._cap.abs_to_rel(x0, y0, mon_used)
            hx = f"#{r:02X}{g:02X}{b:02X}"

            payload = PickConfirmedPayload(
                context=sess.context,
                monitor_requested=sess.monitor_requested,
                monitor=mon_used,
                inside=bool(inside),
                x=int(rel_x),
                y=int(rel_y),
                vx=int(x0),
                vy=int(y0),
                abs_x=int(x0),
                abs_y=int(y0),
                r=int(r),
                g=int(g),
                b=int(b),
                hex=hx,
            )
            self._bus.post_payload(EventType.PICK_CONFIRMED, payload)
            self.stop(reason="confirmed")

        except Exception as e:
            now = time.monotonic()
            throttle_ms = float(sess.cfg.error_throttle_ms)
            if (now - self._last_err_t) * 1000.0 >= throttle_ms:
                self._last_err_t = now
                from core.events.payloads import ErrorPayload
                self._bus.post_payload(EventType.ERROR, ErrorPayload(msg="取色确认失败", detail=str(e)))
        finally:
            # 释放本线程的 mss
            try:
                self._cap.close_current_thread()
            except Exception:
                pass

    # ---------- preview thread ----------
    def _preview_loop(self) -> None:
        ctrl = mouse.Controller()
        try:
            while True:
                with self._lock:
                    if (not self._active) or self._stop_evt.is_set():
                        break
                    sess = self._session
                    start_t = self._start_t
                if sess is None:
                    time.sleep(0.02)
                    continue

                now = time.monotonic()
                if (now - start_t) * 1000.0 < float(sess.cfg.delay_ms):
                    time.sleep(0.01)
                    continue

                try:
                    abs_x, abs_y = ctrl.position
                    abs_x = int(abs_x)
                    abs_y = int(abs_y)

                    mon_used, inside = self._resolve_monitor(abs_x, abs_y, sess.monitor_requested)
                    r, g, b = self._cap.get_rgb_scoped_abs(abs_x, abs_y, sess.sample, mon_used, require_inside=False)
                    rel_x, rel_y = self._cap.abs_to_rel(abs_x, abs_y, mon_used)
                    hx = f"#{r:02X}{g:02X}{b:02X}"

                    if not self._announced_preview:
                        self._announced_preview = True
                        from core.events.payloads import InfoPayload
                        self._bus.post_payload(EventType.INFO, InfoPayload(msg="取色预览已开始"))

                    payload = PickPreviewPayload(
                        context=sess.context,
                        monitor_requested=sess.monitor_requested,
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
                    if (now - self._last_err_t) * 1000.0 >= float(sess.cfg.error_throttle_ms):
                        self._last_err_t = now
                        from core.events.payloads import StatusPayload
                        self._bus.post_payload(EventType.STATUS, StatusPayload(msg=f"取色预览异常: {e}"))

                time.sleep(max(0.005, float(sess.cfg.preview_throttle_ms) / 1000.0))

        finally:
            try:
                self._cap.close_current_thread()
            except Exception:
                pass

    # ---------- monitor selection ----------
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