# File: core/pick/engine.py
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional, Protocol

from pynput import keyboard, mouse

from core.input.hotkey import MOD_KEYS, MOD_NAME, normalize, compose, key_to_name
from core.pick.capture import ScreenCapture
from core.pick.models import PickSessionConfig, PickPreview, PickConfirmed


class Scheduler(Protocol):
    def call_soon(self, fn: Callable[[], None]) -> None: ...


def _clamp(v: int, lo: int, hi: int) -> int:
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


@dataclass(frozen=True)
class PickCallbacks:
    on_enter: Callable[[PickSessionConfig], None]
    on_preview: Callable[[PickPreview], None]
    on_confirm: Callable[[PickConfirmed], None]
    on_cancel: Callable[[], None]
    on_exit: Callable[[str], None]
    on_error: Callable[[str], None]


class PickEngine:
    """
    Pick engine:
    - no EventBus
    - background threads schedule UI callbacks via Scheduler.call_soon
    - config is per-session immutable snapshot (PickSessionConfig)
    """

    def __init__(self, *, scheduler: Scheduler) -> None:
        self._sch = scheduler
        self._cap = ScreenCapture()

        self._lock = threading.RLock()
        self._active = False
        self._cfg: Optional[PickSessionConfig] = None
        self._cbs: Optional[PickCallbacks] = None

        self._stop_evt = threading.Event()
        self._kbd_listener: Optional[keyboard.Listener] = None
        self._preview_thread: Optional[threading.Thread] = None

        self._mods: set[str] = set()
        self._start_t = 0.0
        self._last_err_t = 0.0

    def close(self) -> None:
        self.stop(reason="shutdown")
        try:
            self._cap.close()
        except Exception:
            pass

    def is_active(self) -> bool:
        with self._lock:
            return bool(self._active)

    def start(self, cfg: PickSessionConfig, cbs: PickCallbacks) -> None:
        self.stop(reason="restart")

        cfg2 = PickSessionConfig(
            record_type=cfg.record_type,
            record_id=cfg.record_id,
            monitor_requested=(cfg.monitor_requested or "primary").strip().lower() or "primary",
            sample=cfg.sample,
            delay_ms=int(cfg.delay_ms),
            preview_throttle_ms=int(cfg.preview_throttle_ms),
            error_throttle_ms=int(cfg.error_throttle_ms),
            confirm_hotkey=normalize(cfg.confirm_hotkey) or "f8",
            mouse_avoid=bool(cfg.mouse_avoid),
            mouse_avoid_offset_y=int(cfg.mouse_avoid_offset_y),
            mouse_avoid_settle_ms=int(cfg.mouse_avoid_settle_ms),
        )

        with self._lock:
            self._active = True
            self._cfg = cfg2
            self._cbs = cbs
            self._stop_evt.clear()
            self._mods.clear()
            self._start_t = time.monotonic()
            self._last_err_t = 0.0

        self._sch.call_soon(lambda: cbs.on_enter(cfg2))

        # keyboard listener thread
        try:
            self._kbd_listener = keyboard.Listener(on_press=self._on_key_press, on_release=self._on_key_release)
            self._kbd_listener.start()
        except Exception as e:
            self._sch.call_soon(lambda: cbs.on_error(f"键盘监听启动失败: {e}"))
            self.stop(reason="kbd_listener_failed")
            return

        # preview thread
        self._preview_thread = threading.Thread(target=self._preview_loop, daemon=True)
        self._preview_thread.start()

    def cancel(self) -> None:
        with self._lock:
            if not self._active:
                return
            cbs = self._cbs
        if cbs is not None:
            self._sch.call_soon(cbs.on_cancel)
        self.stop(reason="canceled")

    def stop(self, *, reason: str) -> None:
        with self._lock:
            if not self._active:
                return
            cbs = self._cbs
            self._active = False
            self._cfg = None
            self._cbs = None
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

        if th is not None:
            try:
                th.join(timeout=0.25)
            except Exception:
                pass

        if cbs is not None:
            self._sch.call_soon(lambda: cbs.on_exit(reason))

    # ---------- keyboard listener callbacks (non-UI threads) ----------
    def _on_key_press(self, key) -> None:
        try:
            with self._lock:
                if not self._active:
                    return
                cfg = self._cfg
                cbs = self._cbs
            if cfg is None or cbs is None:
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

            got = normalize(compose(self._mods, main))
            if got == cfg.confirm_hotkey:
                self._confirm_at_current_mouse(cfg, cbs)
        except Exception:
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

    # ---------- confirm ----------
    def _confirm_at_current_mouse(self, cfg: PickSessionConfig, cbs: PickCallbacks) -> None:
        ctrl = mouse.Controller()
        try:
            x0, y0 = ctrl.position
            x0 = int(x0)
            y0 = int(y0)

            mon_used, inside = self._resolve_monitor(x0, y0, cfg.monitor_requested)

            # mouse avoidance best-effort
            if cfg.mouse_avoid:
                dy = int(cfg.mouse_avoid_offset_y)
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
                        settle = int(cfg.mouse_avoid_settle_ms)
                        if settle > 0:
                            time.sleep(float(settle) / 1000.0)
                    except Exception:
                        pass

            r, g, b = self._cap.get_rgb_scoped_abs(x0, y0, cfg.sample, mon_used, require_inside=False)
            rel_x, rel_y = self._cap.abs_to_rel(x0, y0, mon_used)
            hx = f"#{r:02X}{g:02X}{b:02X}"

            confirmed = PickConfirmed(
                record_type=cfg.record_type,
                record_id=cfg.record_id,
                monitor_requested=cfg.monitor_requested,
                monitor=mon_used,
                inside=bool(inside),
                x=int(rel_x),
                y=int(rel_y),
                vx=int(x0),
                vy=int(y0),
                r=int(r),
                g=int(g),
                b=int(b),
                hex=hx,
            )
            self._sch.call_soon(lambda: cbs.on_confirm(confirmed))
            self.stop(reason="confirmed")

        except Exception as e:
            now = time.monotonic()
            if (now - self._last_err_t) * 1000.0 >= float(cfg.error_throttle_ms):
                self._last_err_t = now
                self._sch.call_soon(lambda: cbs.on_error(f"取色确认失败: {e}"))
        finally:
            try:
                self._cap.close_current_thread()
            except Exception:
                pass

    # ---------- preview loop ----------
    def _preview_loop(self) -> None:
        ctrl = mouse.Controller()
        try:
            while True:
                with self._lock:
                    if (not self._active) or self._stop_evt.is_set():
                        break
                    cfg = self._cfg
                    cbs = self._cbs
                    start_t = self._start_t
                if cfg is None or cbs is None:
                    time.sleep(0.02)
                    continue

                now = time.monotonic()
                if (now - start_t) * 1000.0 < float(cfg.delay_ms):
                    time.sleep(0.01)
                    continue

                try:
                    abs_x, abs_y = ctrl.position
                    abs_x = int(abs_x)
                    abs_y = int(abs_y)

                    mon_used, inside = self._resolve_monitor(abs_x, abs_y, cfg.monitor_requested)
                    r, g, b = self._cap.get_rgb_scoped_abs(abs_x, abs_y, cfg.sample, mon_used, require_inside=False)
                    rel_x, rel_y = self._cap.abs_to_rel(abs_x, abs_y, mon_used)
                    hx = f"#{r:02X}{g:02X}{b:02X}"

                    preview = PickPreview(
                        record_type=cfg.record_type,
                        record_id=cfg.record_id,
                        monitor_requested=cfg.monitor_requested,
                        monitor=mon_used,
                        inside=bool(inside),
                        x=int(rel_x),
                        y=int(rel_y),
                        vx=int(abs_x),
                        vy=int(abs_y),
                        r=int(r),
                        g=int(g),
                        b=int(b),
                        hex=hx,
                    )
                    self._sch.call_soon(lambda: cbs.on_preview(preview))

                except Exception as e:
                    now2 = time.monotonic()
                    if (now2 - self._last_err_t) * 1000.0 >= float(cfg.error_throttle_ms):
                        self._last_err_t = now2
                        self._sch.call_soon(lambda: cbs.on_error(f"取色预览异常: {e}"))

                time.sleep(max(0.005, float(cfg.preview_throttle_ms) / 1000.0))
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