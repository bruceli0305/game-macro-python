from __future__ import annotations

from typing import Callable

from core.event_bus import EventBus, Event
from core.event_types import EventType
from core.input.global_hotkeys import GlobalHotkeyService, HotkeyConfig


class HotkeysController:
    def __init__(self, *, bus: EventBus, config_provider: Callable[[], HotkeyConfig]) -> None:
        self._bus = bus
        self._svc = GlobalHotkeyService(bus=bus, config_provider=config_provider)

        self._bus.subscribe(EventType.HOTKEYS_CHANGED, self._on_hotkeys_changed)

    def start(self) -> None:
        self._svc.start()

    def stop(self) -> None:
        self._svc.stop()

    def _on_hotkeys_changed(self, _ev: Event) -> None:
        self._svc.start()