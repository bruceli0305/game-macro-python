# core/events/utils.py
"""
DEPRECATED.

This project uses STRICT typed event payloads (dataclasses).
Do not add "dict compatibility" parsing helpers here.

If you see imports from core.events.utils in other modules, remove them and
use `isinstance(ev.payload, XxxPayload)` directly.
"""